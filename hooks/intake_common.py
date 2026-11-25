"""Shared helpers for the workbook-intake hooks (standard library only, Python 3.9)."""
import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
import unicodedata

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CHECK_TIMEOUT_SECONDS = 20
MAX_OUTPUT_BYTES = 64 * 1024
SANDBOX_EXEC = "/usr/bin/sandbox-exec"

# The checker runs under a profile that lets it read only itself and the target, so it
# cannot share code with the hooks. These values are repeated there and kept equal by
# tests/test_sandbox_profile.py.
SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam", ".xlsb")
MAX_FILE_BYTES = 100 * 1024 * 1024

FAILURE_CODES = (
    "unsupported_extension",
    "file_too_large",
    "encrypted",
    "not_zip",
    "too_many_parts",
    "unsafe_part_name",
    "uncompressed_too_large",
    "compression_ratio_too_high",
    "xml_dtd",
)

WARNING_CODES = (
    "vba_project",
    "external_link",
    "data_connection",
    "external_relationship",
    "power_query",
    "embedded_object",
    "activex",
    "hidden_sheet",
    "very_hidden_sheet",
    "invisible_characters",
    "instruction_like_text",
    "very_long_string",
    "strings_not_checked",
)


def _result(status, failures=(), warnings=()):
    return {"status": status, "failures": list(failures), "warnings": list(warnings)}


def _parse_output(returncode, stdout):
    """Return a result dict, or the error result if anything is outside the vocabulary."""
    if returncode not in (0, 1):
        return _result("error")
    try:
        data = json.loads(stdout[:MAX_OUTPUT_BYTES].decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _result("error")
    if not isinstance(data, dict):
        return _result("error")
    status = "pass" if returncode == 0 else "fail"
    if data.get("result") != status:
        return _result("error")
    failures = data.get("failures")
    warnings = data.get("warnings")
    if not isinstance(failures, list) or not isinstance(warnings, list):
        return _result("error")
    # A passing result has no failures; a failing one has at least one.
    if bool(failures) != (returncode == 1):
        return _result("error")
    if not all(isinstance(f, str) and f in FAILURE_CODES for f in failures):
        return _result("error")
    if not all(isinstance(w, str) and w in WARNING_CODES for w in warnings):
        return _result("error")
    return _result(status, failures, warnings)


def run_checker(real_path, timeout=CHECK_TIMEOUT_SECONDS):
    """Run the checker on real_path under the Seatbelt profile.

    Only the exit code and values from the fixed vocabularies are used; anything else
    is reported as "error".
    """
    if not os.path.exists(SANDBOX_EXEC):
        return _result("sandbox_missing")
    python_home = os.path.realpath(sys.base_prefix)
    try:
        # A user-writable python would let the profile's exec allowance be widened.
        if os.stat(python_home).st_uid != 0:
            return _result("error")
    except OSError:
        return _result("error")
    python_exe = os.path.realpath(os.path.join(sys.base_prefix, "bin", "python3"))
    script = os.path.realpath(os.path.join(PLUGIN_ROOT, "scripts", "check_workbook.py"))
    profile = os.path.realpath(os.path.join(PLUGIN_ROOT, "scripts", "check_workbook.sb"))
    cmd = [
        SANDBOX_EXEC, "-f", profile,
        "-D", "PYTHON_HOME=" + python_home,
        "-D", "SELF=" + script,
        "-D", "TARGET=" + real_path,
        python_exe, "-I", "-B", script, real_path,
    ]
    try:
        outcome, returncode, stdout = _run_bounded(cmd, timeout)
    except FileNotFoundError:
        return _result("sandbox_missing")
    except (OSError, ValueError):
        return _result("error")
    if outcome != "ok":
        return _result(outcome)
    return _parse_output(returncode, stdout)


def _run_bounded(cmd, timeout):
    """Run cmd, reading at most MAX_OUTPUT_BYTES of stdout before the deadline.

    Returns (outcome, returncode, stdout) where outcome is "ok", "timeout" or "error"
    (more output than the cap). The child is killed in the last two cases.
    """
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env={},
    )
    chunks = []
    total = 0
    outcome = "ok"
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            open_pipe = True
            while open_pipe:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    outcome = "timeout"
                    break
                if not sel.select(remaining):
                    continue
                data = os.read(proc.stdout.fileno(), 65536)
                if not data:
                    open_pipe = False
                    break
                total += len(data)
                if total > MAX_OUTPUT_BYTES:
                    outcome = "error"
                    break
                chunks.append(data)
        if outcome == "ok":
            try:
                proc.wait(timeout=max(deadline - time.monotonic(), 0.001))
            except subprocess.TimeoutExpired:
                outcome = "timeout"
    finally:
        if outcome != "ok" or proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
    if outcome != "ok":
        return outcome, None, b""
    return "ok", proc.returncode, b"".join(chunks)


# Fixed texts. The skill repeats them verbatim; tests keep the two in step.
CONSENT_HEADER = "Input check"
CONSENT_QUESTION_PREFIX = (
    "workbook-intake: Before analysis, confirm that this file contains no personal or "
    "confidential information. You use the results at your own risk.\n"
    "解析の前に、このファイルに個人情報や機密情報が含まれていないことを確認してください。"
    "結果は自己責任で使ってください。\n"
    "File / ファイル: "
)
CONFIRM_LABEL = "Confirmed / 確認した"
CONFIRM_DESCRIPTION = (
    "I confirmed the input contains no personal or confidential information. "
    "/ 入力に個人情報や機密情報が含まれていないことを確認した。"
)
CANCEL_LABEL = "Cancel / やめる"
CANCEL_DESCRIPTION = "Do not analyze this file. / このファイルは解析しない。"

WARNINGS_HEADER = "Warnings"
WARNINGS_QUESTION_PREFIX = (
    "workbook-intake: The check reported warnings for this file. Continue the analysis?\n"
    "このファイルの検査で警告が出ました。解析を続けますか。\n"
    "File / ファイル: "
)
WARNINGS_LIST_PREFIX = "\nWarnings / 警告: "
CONTINUE_LABEL = "Continue / 続ける"
CONTINUE_DESCRIPTION = "I reviewed the warnings and continue. / 警告を確かめたうえで続ける。"
STOP_LABEL = "Stop / やめる"
STOP_DESCRIPTION = "Do not analyze this file. / このファイルは解析しない。"


def intake_dir():
    """The intake folder, with "~" expanded (not resolved)."""
    configured = os.environ.get("WORKBOOK_INTAKE_DIR")
    if not configured:
        configured = "~/workbook-intake"
    expanded = os.path.expanduser(configured)
    # A trailing slash would make islink() follow a symlink.
    return expanded.rstrip("/") or expanded


def resolve_in_intake(path):
    """Return (realpath, "ok") for a usable file inside the intake folder, else (None, reason)."""
    if not isinstance(path, str) or not path or "\0" in path:
        return None, "bad_input"
    if not os.path.isabs(path):
        return None, "path_not_absolute"
    folder = intake_dir()
    if not os.path.isabs(folder) or folder == "/" \
            or os.path.islink(folder) or not os.path.isdir(folder) \
            or os.path.realpath(folder) == "/":
        return None, "intake_dir_invalid"
    try:
        real = os.path.realpath(path)
        root = os.path.realpath(folder)
        if not real.startswith(root.rstrip(os.sep) + os.sep):
            return None, "outside_intake"
        if not os.path.isfile(real):
            return None, "not_regular_file"
        if not real.lower().endswith(SUPPORTED_EXTENSIONS):
            return None, "unsupported_extension"
        if os.path.getsize(real) > MAX_FILE_BYTES:
            return None, "file_too_large"
    except (OSError, ValueError):
        return None, "not_regular_file"
    return real, "ok"


def canonical_path(path):
    """True if the path is its own realpath (compared as NFC) with no stray characters.

    xlide strips the path and resolves it itself, so surrounding whitespace, control
    characters or a symlink would let the guard check one file while xlide opens another.
    """
    if path != path.strip():
        return False
    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in path):
        return False
    return (unicodedata.normalize("NFC", os.path.realpath(path))
            == unicodedata.normalize("NFC", path))


def strictly_equal(a, b):
    """JSON-like equality that does not treat 0 as False or 1 as True."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(strictly_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strictly_equal(x, y) for x, y in zip(a, b))
    return a == b


def file_key(real_path):
    return unicodedata.normalize("NFC", real_path)


def file_sha256(real_path):
    digest = hashlib.sha256()
    with open(real_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def consent_question(path):
    return CONSENT_QUESTION_PREFIX + path


def _question(question, header, options):
    return {
        "question": question,
        "header": header,
        "options": [{"label": label, "description": desc} for label, desc in options],
        "multiSelect": False,
    }


def expected_questions(path):
    return [_question(consent_question(path), CONSENT_HEADER, (
        (CONFIRM_LABEL, CONFIRM_DESCRIPTION), (CANCEL_LABEL, CANCEL_DESCRIPTION)))]


def warnings_question(path, warnings):
    return WARNINGS_QUESTION_PREFIX + path + WARNINGS_LIST_PREFIX + ", ".join(warnings)


def expected_warnings_questions(path, warnings):
    return [_question(warnings_question(path, warnings), WARNINGS_HEADER, (
        (CONTINUE_LABEL, CONTINUE_DESCRIPTION), (STOP_LABEL, STOP_DESCRIPTION)))]


def _store_file(session_id, create):
    """Path of the session's record file, or None if the store is unavailable."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data or not isinstance(session_id, str) or not session_id:
        return None
    directory = os.path.join(data, "consents")
    if create:
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            os.chmod(directory, 0o700)
        except OSError:
            return None
    name = hashlib.sha256(session_id.encode("utf-8", "surrogatepass")).hexdigest() + ".jsonl"
    return os.path.join(directory, name)


def _append(session_id, record):
    path = _store_file(session_id, True)
    if path is None:
        return False
    line = (json.dumps(record, ensure_ascii=True) + "\n").encode("ascii")
    try:
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError:
        return False
    return True


def _records(session_id):
    path = _store_file(session_id, False)
    if path is None:
        return []
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return []
    records = []
    for line in raw.split(b"\n"):
        try:
            rec = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def record_consent(session_id, key, sha256, check):
    return _append(session_id, {
        "kind": "consent", "path": key, "sha256": sha256, "status": check["status"],
        "failures": list(check["failures"]), "warnings": list(check["warnings"]),
    })


def find_consent(session_id, key, sha256):
    found = None
    for rec in _records(session_id):
        if rec.get("kind") == "consent" and rec.get("path") == key \
                and rec.get("sha256") == sha256:
            found = rec
    return found


def record_warnings_ack(session_id, key, sha256, warnings):
    return _append(session_id, {
        "kind": "warnings_ack", "path": key, "sha256": sha256, "warnings": list(warnings),
    })


def has_warnings_ack(session_id, key, sha256, warnings):
    for rec in _records(session_id):
        if rec.get("kind") == "warnings_ack" and rec.get("path") == key \
                and rec.get("sha256") == sha256 and rec.get("warnings") == list(warnings):
            return True
    return False
