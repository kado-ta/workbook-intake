# Security policy

This is a personal project, maintained in private time (see [Maintenance](README.md#maintenance)). Replies and fixes are not promised.

## Report a vulnerability

Report it privately through GitHub: open the **Security** tab of this repository and choose **Report a vulnerability**. Do not open a public issue or pull request for a vulnerability.

Include:

- What the problem lets someone do, and the steps to reproduce it.
- The plugin version (`version` in `.claude-plugin/plugin.json`) or the commit SHA you installed.
- The Claude Code version and the macOS version.
- Whether the [required settings](README.md#required-settings) were in place.

Use a workbook made for the report. Do not attach a real workbook or any personal or confidential data.

## In scope

The code and documentation in this repository: the hooks, the structural check and its Seatbelt profile, the skill, the agent, the plugin manifests and the settings the README requires. For example:

- xlide reads a file in the intake folder that you did not confirm, or that failed the check.
- Something other than the analyst subagent can call xlide, or a tool the hook blocks can be called.
- The hook lets xlide read a file outside the intake folder.
- The check's Seatbelt profile lets it write files, use the network or run programs.
- With the required settings in place, Claude's Bash or Read tool can read the intake folder.

## Out of scope

- The risks and limits described in the README under Notes on use and [Limitations](README.md#limitations). They are known and accepted. A report that shows one of them is worse than described is welcome.
- Environments without the required settings, or where hooks are turned off.
- Vulnerabilities in xlide-mcp or the libraries it uses. Report them to [xlide-mcp](https://github.com/WilliamSmithEdward/xlide_mcp) or to the library's project.
- Vulnerabilities in Claude Code. Report them to Anthropic.

## Supported versions

Only the latest version on the `main` branch.
