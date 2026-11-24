"""Shared helpers for the workbook-intake hooks (standard library only, Python 3.9)."""
import json
import os
import selectors
import subprocess
import sys
import time

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
