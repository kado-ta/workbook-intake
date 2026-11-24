#!/bin/bash
# Run the xlide guard with the Command Line Tools python3. Every path prints one
# PreToolUse decision and exits 0; anything unexpected is a deny.
deny() {
  printf '%s' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "workbook-intake: '"$1"'. See the README (Troubleshooting)."}}'
  exit 0
}
dev="$(/usr/bin/xcode-select -p 2>/dev/null)" || deny python_missing
py="$dev/usr/bin/python3"
[ -x "$py" ] || deny python_missing
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || deny internal_error
out="$("$py" -I -B "$here/guard_xlide.py")" || deny internal_error
case "$out" in
  *'"permissionDecision"'*) printf '%s' "$out" ;;
  *) deny internal_error ;;
esac
exit 0
