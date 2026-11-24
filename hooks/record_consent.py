"""PostToolUse hook: record the person's input consent and warning acknowledgement."""
import json
import os
import sys

# Run with -I, which does not put the script's directory on sys.path.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import intake_common as ic  # noqa: E402

TOOL_NAME = "AskUserQuestion"
# A question that carries this marker but not an exact prefix is an altered one of ours.
OWN_MARKER = "workbook-intake:"


def selected_answer(hook_input, question):
    """The label the person chose, read only from tool_response (never from tool_input)."""
    if not isinstance(hook_input, dict):
        return None
    response = hook_input.get("tool_response")
    if not isinstance(response, dict):
        return None
    answers = response.get("answers")
    if not isinstance(answers, dict):
        return None
    answer = answers.get(question)
    return answer if isinstance(answer, str) else None


def _our_question(hook_input):
    """Return (question, kind) for this plugin's single question, else None."""
    if not isinstance(hook_input, dict) or hook_input.get("tool_name") != TOOL_NAME:
        return None
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    questions = tool_input.get("questions")
    if not isinstance(questions, list) or len(questions) != 1 \
            or not isinstance(questions[0], dict):
        return None
    question = questions[0].get("question")
    if not isinstance(question, str):
        return None
    if question.startswith(ic.CONSENT_QUESTION_PREFIX):
        return question, "consent"
    if question.startswith(ic.WARNINGS_QUESTION_PREFIX):
        return question, "warnings"
    if question.startswith(OWN_MARKER):
        return question, "altered"
    return None


def _joined(items):
    return ",".join(items) if items else "none"


def _consent_not_recorded(reason):
    return "workbook-intake: consent=not_recorded; reason=" + reason


def _ack_not_recorded(reason):
    return "workbook-intake: warnings_ack=not_recorded; reason=" + reason


def _handle_consent(hook_input, question):
    path = question[len(ic.CONSENT_QUESTION_PREFIX):]
    if "\n" in path or hook_input["tool_input"]["questions"] != ic.expected_questions(path):
        return _consent_not_recorded("question_mismatch")
    if selected_answer(hook_input, question) != ic.CONFIRM_LABEL:
        return _consent_not_recorded("not_confirmed")
    session_id = hook_input.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _consent_not_recorded("bad_input")
    real, reason = ic.resolve_in_intake(path)
    if real is None:
        return _consent_not_recorded(reason)
    if not os.environ.get("CLAUDE_PLUGIN_DATA"):
        return _consent_not_recorded("consent_store_unavailable")
    check = ic.run_checker(real)
    if not ic.record_consent(session_id, ic.file_key(real), ic.file_sha256(real), check):
        return _consent_not_recorded("consent_store_unavailable")
    return ("workbook-intake: consent=recorded; check=%s; failures=%s; warnings=%s"
            % (check["status"], _joined(check["failures"]), _joined(check["warnings"])))


def _handle_warnings(hook_input, question):
    rest = question[len(ic.WARNINGS_QUESTION_PREFIX):]
    index = rest.find(ic.WARNINGS_LIST_PREFIX)
    if index < 0:
        return _ack_not_recorded("question_mismatch")
    path = rest[:index]
    session_id = hook_input.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _ack_not_recorded("bad_input")
    real, reason = ic.resolve_in_intake(path)
    if real is None:
        return _ack_not_recorded(reason)
    if not os.environ.get("CLAUDE_PLUGIN_DATA"):
        return _ack_not_recorded("consent_store_unavailable")
    key, digest = ic.file_key(real), ic.file_sha256(real)
    consent = ic.find_consent(session_id, key, digest)
    if consent is None:
        return _ack_not_recorded("no_consent")
    warnings = consent.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        return _ack_not_recorded("question_mismatch")
    expected = ic.expected_warnings_questions(path, warnings)
    if hook_input["tool_input"]["questions"] != expected:
        return _ack_not_recorded("question_mismatch")
    if selected_answer(hook_input, question) != ic.CONTINUE_LABEL:
        return _ack_not_recorded("not_confirmed")
    if not ic.record_warnings_ack(session_id, key, digest, warnings):
        return _ack_not_recorded("consent_store_unavailable")
    return "workbook-intake: warnings_ack=recorded"


def handle(hook_input):
    """Return the fixed-vocabulary text for the conversation, or None if not our question."""
    ours = _our_question(hook_input)
    if ours is None:
        return None
    question, kind = ours
    if kind == "altered":
        return _consent_not_recorded("question_mismatch")
    if kind == "consent":
        return _handle_consent(hook_input, question)
    return _handle_warnings(hook_input, question)


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except (ValueError, RecursionError, OSError, UnicodeDecodeError):
        return 0
    try:
        text = handle(hook_input)
    except Exception:  # noqa: BLE001 - the hook must never crash the session
        ours = _our_question(hook_input)
        if ours is None:
            return 0
        text = (_ack_not_recorded("internal_error") if ours[1] == "warnings"
                else _consent_not_recorded("internal_error"))
    if text is not None:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
