# workbook-intake probe

> [!CAUTION]
> This plugin exists only to check how Claude Code behaves with plugin hooks, subagents and MCP servers.
> Its hooks let xlide calls through without any checks or consent.
> Do not install it for normal analysis.

The probe has the same plugin name (`workbook-intake`) as the real plugin, so that tool names and the subagent's `agent_type` look the same as in real use.
Install it from its own marketplace (`workbook-intake-probe`), run the checks, and uninstall it afterwards.

The hook writes each hook input to `probe.log` in the plugin data directory (`${CLAUDE_PLUGIN_DATA}`).
The log contains file paths, so do not commit it.

The steps and the list of checks are in the first verification record (`docs/work/20261124_workbook-intake/research-plugin-behavior.md`). The maintenance runbook (`docs/runbooks/maintenance.md`) will carry them for later re-checks.

`settings/` holds the extra settings that later sessions pass with `claude --settings`, so that the local settings file written by the install stays untouched.
