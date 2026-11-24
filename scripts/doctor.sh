#!/bin/bash
# Checks the requirements of the workbook-intake plugin and prints one line per item:
#   ok <item>  or  missing <item>
# Exit code 1 if anything is missing. Runs only when the analyze skill starts it.

missing=0

report() {
  # $1 = item, $2 = 0 when satisfied
  if [ "$2" -eq 0 ]; then
    echo "ok $1"
  else
    echo "missing $1"
    missing=1
  fi
}

# Same rule as intake_dir() in hooks/intake_common.py: env value if set and non-empty,
# else ~/workbook-intake; a leading "~" is expanded; trailing slashes are dropped.
intake="${WORKBOOK_INTAKE_DIR:-$HOME/workbook-intake}"
case "$intake" in
  \~) intake="$HOME" ;;
  \~/*) intake="$HOME/${intake#??}" ;;
esac
while [ "${#intake}" -gt 1 ] && [ "${intake%/}" != "$intake" ]; do
  intake="${intake%/}"
done

if [ "$(uname -s)" = "Darwin" ]; then report macos 0; else report macos 1; fi

if command -v uvx >/dev/null 2>&1; then report uvx 0; else report uvx 1; fi

clt="$(xcode-select -p 2>/dev/null)"
if [ -n "$clt" ] && [ -x "$clt/usr/bin/python3" ]; then report python3 0; else report python3 1; fi

if [ -x /usr/bin/sandbox-exec ]; then report sandbox_exec 0; else report sandbox_exec 1; fi

# Under the recommended sandbox settings Bash cannot list the intake folder. If it can,
# the settings are missing (or the sandbox is off). A missing folder cannot be listed
# either; the hooks outside the sandbox check that it exists.
if ls -A "$intake" >/dev/null 2>&1; then
  report intake_dir_protected 1
else
  report intake_dir_protected 0
fi

# The real path of the intake folder, for the skill to build file paths from. Only
# metadata is needed, so this works under the recommended sandbox settings.
if [ -d "$intake" ]; then
  folder="$(realpath "$intake" 2>/dev/null)"
  if [ -n "$folder" ]; then
    echo "folder $folder"
  fi
fi

if [ "$missing" -ne 0 ]; then
  echo "See README: Requirements"
  exit 1
fi
exit 0
