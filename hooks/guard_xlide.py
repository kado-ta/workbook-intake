"""PreToolUse hook: decide every xlide tool call (standard library only, Python 3.9)."""
import json
import os
import sys

# Run with -I, which does not put the script's directory on sys.path.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import intake_common as ic  # noqa: E402

TOOL_PREFIX = "mcp__plugin_workbook-intake_xlide__"
ANALYST_AGENT_TYPE = "workbook-intake:excel-analyst"
MCP_SERVER_NAME = "plugin:workbook-intake:xlide"
MCP_SERVER_SOURCE = "plugin"
ALLOWLIST_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "allowed-tools.txt")
PATH_LIKE_WORDS = ("path", "file", "dir", "folder", "root")


def load_allowlist():
    """Map tool name to "file" or "nofile" from allowed-tools.txt."""
    tools = {}
    with open(ALLOWLIST_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, kind = line.split()
            if kind not in ("file", "nofile"):
                raise ValueError("bad allowlist line")
            tools[name] = kind
    return tools


def _check_reason(check):
    """Map a checker result to a (reason, detail codes) pair, or None if it passed."""
    status = check.get("status") if isinstance(check, dict) else None
    if status == "pass":
        warnings = check.get("warnings")
        if check.get("failures") != [] or not isinstance(warnings, list) \
                or not all(isinstance(w, str) and w in ic.WARNING_CODES for w in warnings):
            return "check_error", []
        return None
    if status == "fail":
        codes = [c for c in check.get("failures", []) if c in ic.FAILURE_CODES]
        return "check_failed", codes
    if status == "timeout":
        return "check_timeout", []
    if status == "sandbox_missing":
        return "sandbox_missing", []
    return "check_error", []


def _decide_file(session_id, file_path):
    """Return (decision, reason, detail codes) for a call that names a file."""
    real, reason = ic.resolve_in_intake(file_path)
    if real is None:
        return "deny", reason, []
    if not ic.canonical_path(file_path):
        return "deny", "path_not_canonical", []
    if not os.environ.get("CLAUDE_PLUGIN_DATA"):
        return "deny", "consent_store_unavailable", []
    key, digest = ic.file_key(real), ic.file_sha256(real)
    if ic.find_consent(session_id, key, digest) is None:
        return "deny", "no_consent", []
    check = ic.run_checker(real, ic.CHECK_TIMEOUT_SECONDS)
    bad = _check_reason(check)
    if bad is not None:
        return "deny", bad[0], bad[1]
    if ic.file_sha256(real) != digest:
        return "deny", "check_error", []
    warnings = check["warnings"]
    if warnings and not ic.has_warnings_ack(session_id, key, digest, warnings):
        return "deny", "warnings_not_acknowledged", warnings
    return "allow", "ok", []


def decide_detail(hook_input):
    """Return (decision, reason, detail codes)."""
    if not isinstance(hook_input, dict):
        return "deny", "bad_input", []
    tool_name = hook_input.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.startswith(TOOL_PREFIX):
        return "deny", "not_plugin_server", []
    if "mcp_server" in hook_input:
        server = hook_input["mcp_server"]
        if not isinstance(server, dict) or server.get("name") != MCP_SERVER_NAME \
                or server.get("source") != MCP_SERVER_SOURCE:
            return "deny", "not_plugin_server", []
    kind = load_allowlist().get(tool_name[len(TOOL_PREFIX):])
    if kind is None:
        return "deny", "tool_not_allowed", []
    if hook_input.get("agent_type") != ANALYST_AGENT_TYPE:
        return "deny", "wrong_caller", []
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return "deny", "bad_input", []
    for name in tool_input:
        if name != "file_path" and any(w in name.lower() for w in PATH_LIKE_WORDS):
            return "deny", "unexpected_path_argument", []
    if tool_input.get("calculate", False) is not False:
        return "deny", "calculation_not_allowed", []
    if tool_input.get("is_regex", False) is not False:
        return "deny", "regex_not_allowed", []
    if "file_path" not in tool_input:
        if kind == "file":
            return "deny", "missing_file_path", []
        return "allow", "ok", []
    return _decide_file(hook_input.get("session_id"), tool_input["file_path"])


def decide(hook_input):
    """Return ("allow" or "deny", reason)."""
    decision, reason, _ = decide_detail(hook_input)
    return decision, reason


def _output(decision, reason, detail=()):
    text = "workbook-intake: " + reason
    if detail:
        text += " (" + ",".join(detail) + ")"
    text += ". See the README (Troubleshooting)."
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": text}})


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except (ValueError, RecursionError, OSError, UnicodeDecodeError):
        hook_input = None
    try:
        out = _output(*decide_detail(hook_input))
    except Exception:  # noqa: BLE001 - any failure must end in a deny
        out = _output("deny", "internal_error")
    try:
        sys.stdout.write(out)
        sys.stdout.flush()
    except OSError:
        # Nothing can be delivered; a non-zero exit makes the hook fail closed.
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
