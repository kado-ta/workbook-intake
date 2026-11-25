#!/bin/bash
# Run the consent-recording hook with the Command Line Tools python3. If it is missing,
# record nothing and exit 0 (the PreToolUse guard then blocks the xlide call).
# The hook runs outside Claude's sandbox, so it must not run commands from a PATH
# directory the sandbox can write.
export PATH=/usr/bin:/bin
dev="$(/usr/bin/xcode-select -p 2>/dev/null)" || exit 0
py="$dev/usr/bin/python3"
[ -x "$py" ] || exit 0
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
exec "$py" -I -B "$here/record_consent.py"
