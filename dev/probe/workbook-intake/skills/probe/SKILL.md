---
name: probe
description: Verification probe for the workbook-intake plugin. Use only when the user explicitly asks to run the workbook-intake probe skill.
disable-model-invocation: true
---

# workbook-intake probe skill

This skill checks whether Claude Code replaces the plugin root variable in a skill's text.

1. Report the next line exactly as you see it, without changing it:

   PLUGIN_ROOT_IN_SKILL_TEXT=${CLAUDE_PLUGIN_ROOT}

2. Run this command with Bash and report its output:

   ```sh
   echo "PLUGIN_ROOT_IN_BASH_ENV=${CLAUDE_PLUGIN_ROOT-<unset>}"
   ```
