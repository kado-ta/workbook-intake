#!/bin/bash
# Probe hook for checking how Claude Code runs plugin hooks. It is not a guard:
# it lets some xlide calls through without any checks. Do not install the probe
# for normal use.
#
# PreToolUse (xlide tools): log the input and decide by the tool's short name.
# PostToolUse (AskUserQuestion): log the input and return a marker string as
# additionalContext.

# Tools picked from the xlide-mcp 1.2.4 inventory (see the research document).
T_READ="xlide_list_sheets" # takes file_path; allowed
T_DENY="xlide_manage_conditional_format" # denied by the probe
T_SLOW="xlide_list_modules" # sleeps past the hook timeout of 5 seconds
T_FAIL="xlide_project_info" # exits 1 without output

py="$(/usr/bin/xcode-select -p 2>/dev/null)/usr/bin/python3"
log="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}/probe.log"
input=$(cat)

sandbox_exit=0
/usr/bin/sandbox-exec -n no-network /usr/bin/true >/dev/null 2>&1 || sandbox_exit=$?

{
  printf '=== %s pid=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$"
  printf 'CLAUDE_PLUGIN_ROOT=%s\n' "${CLAUDE_PLUGIN_ROOT-<unset>}"
  printf 'CLAUDE_PLUGIN_DATA=%s\n' "${CLAUDE_PLUGIN_DATA-<unset>}"
  printf 'WORKBOOK_INTAKE_DIR=%s\n' "${WORKBOOK_INTAKE_DIR-<unset>}"
  printf 'sandbox_exec_exit=%s\n' "$sandbox_exit"
  printf 'input=%s\n' "$input"
} >>"$log"

# Print one top-level string field of the hook input.
field() {
  printf '%s' "$input" | "$py" -I -c '
import json, sys
try:
    value = json.load(sys.stdin).get(sys.argv[1], "")
except Exception:
    value = ""
print(value if isinstance(value, str) else "")
' "$1"
}

decide() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s","permissionDecisionReason":"probe: %s"}}\n' "$1" "$2"
}

event=$(field hook_event_name)
tool=$(field tool_name)
short="${tool##*__}"
printf 'event=%s tool=%s\n' "$event" "$tool" >>"$log"

case "$event" in
PostToolUse)
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"probe-additional-context"}}'
  ;;
PreToolUse)
  case "$short" in
  xlide_doctor | "$T_READ") decide allow "$short allowed" ;;
  "$T_DENY") decide deny "$short denied" ;;
  "$T_SLOW")
    sleep 10
    decide allow "$short allowed after sleeping"
    ;;
  "$T_FAIL") exit 1 ;;
  *) decide deny "$short is not part of the probe" ;;
  esac
  ;;
esac
exit 0
