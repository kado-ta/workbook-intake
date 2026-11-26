# workbook-intake

[日本語](README.ja.md)

A Claude Code plugin that runs a structural check on Excel workbooks received from outside before Claude analyzes them with xlide-mcp.

This is a personal project, not affiliated with xlide-mcp or NVIDIA SkillSpector.
Use it at your own risk. It does not guarantee safety.

> [!WARNING]
> The checks reduce some risks. They do not make a workbook safe to open or send anywhere. Read [Limitations](#limitations) before use.

## What it does

- xlide is limited to one intake folder (`~/workbook-intake` by default; to change it, see [Configuration](#configuration)).
- Before xlide reads a file, you are asked to confirm that it contains no personal or confidential information. A hook records your answer; the model does not choose it.
- A hook then runs a structural check of the file inside a macOS Seatbelt sandbox (no network, no writes) and tells you the result in a fixed vocabulary.
- Only a read-only subagent can call xlide, and only its read-only tools. A hook blocks every other call.

The plugin contains no xlide code. xlide-mcp is fetched from PyPI at run time with pinned versions.

## Notes on use

Files you let Claude read are sent to Anthropic as model input, and may also stay on your machine.

1. Everything inside a file can be read: comments, defined names, VBA, Power Query, external link paths. Hidden sheets and protection do not hide anything. A file with personal data (names, addresses, dates of birth, income, loans) sends that data as it is.
2. Conversation logs are kept in plain text on your machine (`~/.claude/projects/<project>/*.jsonl`, 30 days by default; see `cleanupPeriodDays`).
3. A file from a customer or partner can contain text that tries to steer Claude (prompt injection). xlide runs read-only and the analyzing subagent has no Bash or Web tools. The main conversation, which receives the summary, still has its own tools and can be steered.
4. Cell values are the results Excel saved last. Recalculation, formula evaluation, cell error checks, static analysis of VBA and regular-expression search are not available (the hook blocks them). Claude can also misread. Check figures you pass on against Excel.
5. Whether you may send a file to Anthropic depends on your organization's rules and contracts. The plugin only asks you and records the answer. It cannot judge the content.
6. Your confirmations are recorded in `${CLAUDE_PLUGIN_DATA}/consents/` (`~/.claude/plugins/data/<id>/consents/`, where `<id>` is the plugin identifier with every character other than a letter, digit, `_` or `-` replaced by `-`), one `<SHA-256 of the session ID>.jsonl` file per session, in plain text. Each line holds the real path of the file you were asked about (the path can contain a business partner's name) and its SHA-256. A line for an input confirmation also holds the check status and the failure and warning codes; a line for a warning confirmation also holds the warning codes. Nothing in the plugin deletes these files. Claude Code deletes the folder when you uninstall the plugin from the last place it is installed, unless you use `--keep-data` (it also stays in a few other cases; see [plugin uninstall](https://code.claude.com/docs/en/plugins/cli-reference.md#plugin-uninstall)). To delete them earlier, remove the `consents` folder while no Claude Code session is using the plugin. A missing folder is created again on the next confirmation, and the next analysis asks you to confirm the file again.
7. Only the file in the intake folder is protected. A copy outside the folder (a download location, an email attachment) and a hard link to the file are not protected: Claude can read them through other paths. Move the file into the folder instead of copying it.

<a name="requirements"></a>

## Requirements

- macOS (the check uses Seatbelt, `sandbox-exec`).
- Command Line Tools (`xcode-select --install`), for `python3`.
- [uv](https://docs.astral.sh/uv/) (`uvx`).
- Claude Code 2.1.295 or later, because the hooks use `onFailure`. `plugin.json` declares this in `engines`, but Claude Code reads `engines` only from 2.1.323, so older versions do not enforce it. Pinning a marketplace by commit SHA (see Install) needs 2.1.324 or later.
- xlide runs on Python 3.15. If it is not on the machine, uv fetches it on the first start (where it cannot be fetched, the xlide tools are not visible). Only the minor version (3.15) is pinned: uv uses a 3.15 that it manages itself, or else the `python3.15` on your PATH.
- First run: `uvx` downloads a Python and the pinned packages, so it needs a network and takes a while.

`scripts/doctor.sh` checks the requirements when the skill starts. It prints `ok <item>` or `missing <item>` for `macos`, `uvx`, `python3`, `sandbox_exec` and `intake_dir_protected`, and then `folder <path>`.

<a name="install"></a>

## Install

Install from GitHub, not from a local working copy. A local directory used as a marketplace makes the plugin run in place from that folder, and a sandboxed session there could modify it.

Quick way:

```sh
claude plugin marketplace add kado-ta/workbook-intake
claude plugin install workbook-intake@workbook-intake
```

Recommended: pin the marketplace to a commit you reviewed, and keep auto-update off. In your user settings (`~/.claude/settings.json`), set `ref` to the full 40-character commit SHA (marketplace sources accept a SHA in `ref`; Claude Code 2.1.324 or later):

```json
{
  "extraKnownMarketplaces": {
    "workbook-intake": {
      "source": {
        "source": "github",
        "repo": "kado-ta/workbook-intake",
        "ref": "<full commit SHA you reviewed>"
      },
      "autoUpdate": false
    }
  }
}
```

Then run `claude plugin install workbook-intake@workbook-intake`. See [plugin marketplace sources](https://code.claude.com/docs/en/plugins/marketplace-reference.md#marketplace-sources).

<a name="configuration"></a>

## Configuration

Create the intake folder: `mkdir -p ~/workbook-intake`.

Settings cannot be shipped by a plugin, so you set them yourself in `~/.claude/settings.json`.

Required (both). Add them to your existing settings; do not replace what is there. The sandbox is off by default, so `"enabled": true` is part of the requirement. They stop Claude's Bash and Read tool from reading the intake folder. xlide and the hooks run outside the sandbox and can still read it. In a probe, `denyRead` alone still let the Read tool read, so both are needed. The skill stops unless the sandbox refuses Bash's read of the folder.

```json
{
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/workbook-intake"]
    }
  },
  "permissions": {
    "deny": ["Read(~/workbook-intake/**)"]
  }
}
```

Recommended:

- `"sandbox": {"allowUnsandboxedCommands": false}`: according to the Claude Code documentation, Claude Code then ignores requests to run a command outside the sandbox. I could not isolate its effect in my own check.
- `"sandbox": {"failIfUnavailable": true}`: according to the documentation, Claude Code refuses to start when the sandbox is unavailable, instead of running unsandboxed.
- `"sandbox": {"filesystem": {"denyWrite": ["~/workbook-intake"]}}`: keeps sandboxed commands from writing to the folder, which matters for sessions started from `~`.

I wrote the `failIfUnavailable` and `denyWrite` forms from the documented key names, not from a tested example. These sandbox keys are listed in the [settings reference](https://code.claude.com/docs/en/settings-reference.md) (`sandbox.filesystem.denyRead`, `sandbox.filesystem.denyWrite`, `sandbox.failIfUnavailable`, `sandbox.allowUnsandboxedCommands`) and in [sandboxing](https://code.claude.com/docs/en/sandboxing.md).

If a project defines its own `xlide` server with the same `uvx` command, Claude Code uses one of them only, and the plugin's is dropped as a duplicate (observed with Claude Code 2.1.331). Disable the project's with `"disabledMcpjsonServers": ["xlide"]`. While the plugin is enabled, the hook denies every call to xlide that does not come from the analyst subagent, including calls to a project's own xlide server.

To use another intake folder, set `WORKBOOK_INTAKE_DIR` in the environment that starts Claude Code, and change the two deny settings in the required settings above (`sandbox.filesystem.denyRead` and the `Read(...)` rule in `permissions.deny`) to the same folder (example below). The two write absolute paths differently: `sandbox.filesystem.denyRead` takes `/abs/path`, while a `Read(...)` permission rule needs two leading slashes, `Read(//abs/path/**)` (a single leading slash is relative to the settings file). A path under your home folder can be written `~/...` in both. The folder path cannot contain a colon (`:`), because xlide splits it into several folders; the hooks refuse it as `intake_dir_invalid`.

For example, to use `~/received`:

1. Create the folder, set the variable in the shell that starts Claude Code, and start it (put the `export` line in `~/.zshrc` or similar to use it every time). The hooks, xlide and `doctor.sh` all read the variable as it was when Claude Code started.

```sh
mkdir -p ~/received
export WORKBOOK_INTAKE_DIR=~/received
claude
```

2. In `~/.claude/settings.json`, point the two deny settings of the required settings (the example above) at that folder. Keep your other keys. The required settings then read:

```json
{
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/received"]
    }
  },
  "permissions": {
    "deny": ["Read(~/received/**)"]
  }
}
```

<a name="usage"></a>

## Usage

1. Put the file in the intake folder (`.xlsx`, `.xlsm`, `.xlam`, `.xlsb`; up to 100 MiB). Templates (`.xltx`, `.xltm`) are not accepted because xlide cannot read them: save them as `.xlsx` or `.xlsm` in Excel first, then put the saved file in the folder.
2. Ask Claude to analyze it by file name, for example "Analyze `sales.xlsx` with /workbook-intake:analyze". Claude cannot list the folder, so name the file.
3. The skill shows two fixed questions: the input confirmation, and, only if the check reported warnings, a warning confirmation. Answering "Confirmed" or "Continue" is recorded by a hook. The record is valid for this session and this file content only.
4. The read-only subagent `workbook-intake:excel-analyst` reads the workbook with xlide and returns a summary.

When the skill starts (in step 2, before it asks you anything), it first calls Read once on a file name that does not exist inside the intake folder (`workbook-intake-read-check.xlsx`) and continues only if Claude Code refuses it because of your permission settings, which shows that the `Read(...)` deny rule is set. It then calls `xlide_doctor` once from the main conversation to check that the hook is running. The hook refuses that call with `workbook-intake: wrong_caller`, and that refusal is expected. If a permission prompt for `xlide_doctor` appears, the hook is not running: choose No, not an option that allows the call or stops asking. The skill stops on any outcome other than that refusal: a result, a declined call, or another refusal reason (see [Troubleshooting](#troubleshooting)). At the same point, the skill also stops if its Agent tool has a `name` or `team_name` parameter, which means agent teams are on.

Google Sheets: not read directly. Download as `.xlsx` and put it in the intake folder (Apps Script is not included; Google-specific functions may not behave as in Excel). The claude.ai Google Sheets connector is outside this plugin's protection.

<a name="checks"></a>

## Checks

The check is a Python script run under Seatbelt. It prints only fixed codes, never text from the file.

Failure codes (the file is not read):

| Code | Meaning |
| --- | --- |
| `unsupported_extension` | Extension is not one of the supported ones |
| `file_too_large` | Over 100 MiB |
| `encrypted` | Password-protected package |
| `not_zip` | Cannot be opened as a zip, or the ZIP layout could be read differently by different readers (an archive comment, prefix data, gaps or overlaps between entries, ZIP64 records, local headers that disagree with the central directory, a Unicode Path extra, flag bits 5 or 6, part data whose length or CRC differs from the central directory), or the zip inside a Power Query part is broken (the Base64 text has a character outside the Base64 alphabet, padding in the wrong place, or a length that cannot be decoded; or section or part lengths do not add up) |
| `too_many_parts` | More than 10,000 parts in the outer package. The zip inside a Power Query part has no part-count limit; its size is limited by the total size limit and the compression ratio limit |
| `unsafe_part_name` | A part name has `..` or an absolute path, `\`, a drive letter (such as `C:`), NUL, an empty segment, a `.` segment, a directory name with content, or a name that disagrees with the UTF-8 flag, or two names differ only in letter case |
| `uncompressed_too_large` | Expands to more than 256 MiB in total (including the zip inside a Power Query part), or a part named `customXml/item*.xml` (such as `item1.xml` or `itemProps1.xml`) is over 32 MiB |
| `compression_ratio_too_high` | One part (including a part of the zip inside a Power Query part) compresses by more than 100 times. A part of 100 KiB or less is not subject to this limit |
| `xml_dtd` | A part has `<!DOCTYPE` or `<!ENTITY`. Every part is searched, not only XML, and so is the content of a Power Query part (the parts of the zip inside it and its metadata), so an SVG image or a macro that writes HTML can cause it |

Warning codes (you must confirm before the analysis continues):

| Code | Meaning |
| --- | --- |
| `vba_project` | Contains a VBA project |
| `external_link` | Links to external workbooks |
| `data_connection` | Contains data connections |
| `external_relationship` | A relationship points outside the file |
| `power_query` | A part contains the `DataMashup` marker, which means Power Query. Strings inside the queries (M code, query names, descriptions) are not checked |
| `embedded_object` | Contains embedded objects |
| `activex` | Contains ActiveX controls |
| `hidden_sheet` | A hidden sheet exists |
| `very_hidden_sheet` | A very hidden sheet exists |
| `invisible_characters` | Zero-width, direction-control or tag characters in strings |
| `instruction_like_text` | Wording that looks like instructions to an AI |
| `very_long_string` | A string over 10,000 characters (Power Query workbooks can show it, because the query is stored as one long encoded string) |
| `strings_not_checked` | Some parts could not be fully checked; strings, sheet states and relationships in them are unknown: `.xlsb` (binary), oversized XML parts, XML parts the checker cannot read, two attributes with the same local name on one element, nesting deeper than 256 levels, a part whose first two bytes contain NUL without a byte-order mark, nested text runs inside a paragraph, parts whose XML syntax is read differently by xlide's reader (such as a comment starting with `<!-->`) |

Check statuses: `pass`, `fail`, `error` (output outside the vocabulary or unexpected result), `timeout` (over 20 seconds), `sandbox_missing` (`sandbox-exec` not found).

<a name="limitations"></a>

## Limitations

- The string checks can miss things, and false positives happen. This is not antivirus. Leave virus scanning to your own endpoint protection.
- The file can change between the check and the read. The intake folder is outside the sandbox's write range, but processes outside the sandbox (you, other apps) can still replace files. Use `denyWrite`.
- Without the recommended settings, use outside the skill (other skills, or asking Claude directly to read the file with Bash) can still read the intake folder. `doctor.sh` runs only inside the skill.
- `disableAllHooks` can turn off hooks from a settings file at any scope, including the repository's `.claude/settings.json` (hooks from managed settings are exempt). Plugin hooks are expected to be turned off too (inferred, not verified). The managed setting `allowManagedHooksOnly` also drops the hooks of plugins you installed yourself, while the plugin's xlide server still loads. When they are off, the main conversation can call xlide, and neither the input confirmation nor the check runs. Do not use the plugin in such an environment.
- The check runs on the Command Line Tools Python 3.9.6, with its expat 2.2.8. Seatbelt stops a hijacked check from writing, using the network, or running programs, but it does not protect the verdict itself. Strict decoding of the character encoding, rejection of DTDs, and a 32 MiB limit per part narrow what can reach the parser.
- xlide expands VBA source with no size limit. A workbook with macros (the `vba_project` warning) can use a lot of memory.
- A crafted file can still make xlide use a lot of time or memory through the tools that stay allowed. Examples (measured values are in the [test report](docs/work/20261124_workbook-intake/test-report.md#review-5)): reading a long shared formula, a row with a huge number of cells, thousands of queries, many VBA line continuations. xlide runs outside the sandbox and has no memory limit. If things get heavy, stop Claude Code and end the xlide process from a normal terminal (commands inside the sandbox cannot see it): list the processes with `pgrep -fl 'xlide-mcp.*--read-only'` (uvx and the Python it starts both match) and stop every listed PID with `kill`. The heaviest shapes (calculation, static analysis of VBA, regular-expression search) are blocked by the hook.
- Claude Code's experimental agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) must be off. When they are on, the agent that reads the workbook can message other teammates directly, so the hook blocks every xlide call while the variable has a non-empty value, `0` included (`agent_teams_enabled`). This check sees only the environment passed to the hook process. The start flag `--agent-teams` also enables agent teams, and the hook cannot see it. The skill stops instead when its Agent tool has a `name` or `team_name` parameter, which Claude Code adds only while agent teams are on (found by reading the Claude Code 2.1.332 binary). Do not start Claude Code with that flag.
- `.mcp.json` pins only xlide-mcp and four dependencies. The other dependencies are resolved by uv when it builds the environment, which can happen again on a later start, so a newer version of them can arrive on any start (on purpose, to receive security fixes of the dependencies below).
- The input confirmation relies on a person answering the AskUserQuestion screen. In an environment where another plugin's hook or an SDK host fills in the answer, an approval can be recorded without a person confirming it.
- PreToolUse hooks run in parallel, and another plugin's or your own hook can rewrite the input with `updatedInput`. If one rewrites it after the guard allows the call, xlide can run on input that did not pass the confirmation or the check (xlide itself still refuses paths outside the intake folder). Do not install hooks that rewrite tool input.
- Tool names carry the prefix `mcp__plugin_workbook-intake_xlide__` (for example `mcp__plugin_workbook-intake_xlide__xlide_doctor`). A matcher that names only the server (`mcp__xlide__.*`) does not match them.
- xlide is visible to the main conversation too, because plugin subagents cannot declare their own MCP servers. Calls from the main conversation are blocked by the hook.
- A hook's allow only skips a prompt. Deny and ask rules in your settings still apply.
- Display tricks in a file name (look-alike characters, special spaces, combining marks) cannot be fully prevented. They need a real file of that name in the intake folder.
- `.xls` is not supported. xlide reads `.xlsb` sheets only on Windows (on macOS its sheet tool rejects `.xlsb`).
- The approval record lives in the plugin data directory. In an environment where a sandboxed command can write there, an approval can be forged.
- If the plugin cache is writable from a sandboxed session, the hooks could be modified. If your GitHub account is taken over, a bad update could be published; pinning by SHA with auto-update off helps you use only versions you have reviewed, but it does not prevent this.
- The environment can change where uv fetches from (for example `UV_DEFAULT_INDEX`).
- xlide finds `uvx` through PATH. Do not put a directory that a sandboxed command can write to at the front of PATH.
- xlide runs from uv's cache (`~/.cache/uv`, or `UV_CACHE_DIR`) outside the sandbox. Do not let sandboxed commands write to it: keep it out of the sandbox's write allowances, and add it to `denyWrite` for sessions started from `~`. Code changed there would run with your privileges the next time xlide starts. The same goes for the Python that uv picks for `--python 3.15` (see `uv python find 3.15`), which may live outside the cache.
- macOS only. Windows live tools of xlide are not used.
- The skill checks the Read deny with one file name, `workbook-intake-read-check.xlsx`, so it cannot tell a deny that is narrower than the folder (for example `Read(~/workbook-intake/**/*.xlsx)`) from the right one. Write the rule for the whole folder, as in [Configuration](#configuration).
- Not covered: people who use xlide without this plugin, and the Google Sheets connector.

<a name="troubleshooting"></a>

## Troubleshooting

Consent hook lines (`workbook-intake: consent=...`, `warnings_ack=...`). The line on success is `consent=recorded; check=<status>; failures=...; warnings=...` or `warnings_ack=recorded`. When not recorded, `reason=` is one of:

| Reason | Meaning |
| --- | --- |
| `bad_input` | The hook input or session ID could not be read |
| `question_mismatch` | The question was not the fixed one |
| `not_confirmed` | The answer was not "Confirmed" or "Continue" |
| `path_not_absolute` | The path was not absolute |
| `intake_dir_invalid` | The intake folder is missing, a symlink, `/`, or its path contains a colon |
| `outside_intake` | The file is outside the intake folder |
| `not_regular_file` | Not a regular file |
| `unsupported_extension` | Extension not supported |
| `file_too_large` | Over 100 MiB |
| `path_not_canonical` | The path is not its own real path, or has surrounding whitespace or control characters |
| `file_changed` | The file changed while it was being checked |
| `consent_store_unavailable` | The record cannot be written (plugin data directory missing, or the record could not be written in full) |
| `no_consent` | No input confirmation was recorded for this file content |
| `internal_error` | Unexpected hook error |

Guard hook denials (`workbook-intake: <reason>`, with failure or warning codes in parentheses when relevant):

| Reason | Meaning |
| --- | --- |
| `not_plugin_server` | The tool is not from this plugin's xlide (for example the project's own xlide), or Claude Code did not pass the server origin (an older version) |
| `tool_not_allowed` | The tool is not on the allowlist (`hooks/allowed-tools.txt`) |
| `wrong_caller` | The caller is not `workbook-intake:excel-analyst`. The skill's first check expects this refusal once, from the main conversation |
| `unexpected_path_argument` | A path-like argument other than `file_path` |
| `calculation_not_allowed` | A call that asks for calculation (such as `calculate=true`). xlide's calculation engine can use unbounded memory |
| `regex_not_allowed` | A call that asks for regular-expression search (`is_regex=true`). xlide runs the given regular expression with no time limit |
| `query_too_long` | A search `query` longer than 256 characters. The cost of a case-insensitive search grows with the body length times the query length |
| `agent_teams_enabled` | Agent teams are on (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` has a non-empty value). Turn them off and start Claude Code again |
| `missing_file_path` | The tool needs `file_path` |
| `bad_input` | The hook input could not be read |
| `outside_intake`, `path_not_absolute`, `intake_dir_invalid`, `not_regular_file`, `unsupported_extension`, `file_too_large` | Same as above |
| `path_not_canonical` | Same as above (the guard and xlide could resolve such a path to different files) |
| `consent_store_unavailable`, `no_consent` | Same as above |
| `check_failed` | The check failed (failure codes follow) |
| `check_timeout` | The check took over 20 seconds. This tends to happen with a workbook whose XML totals about 200 MB or more (for example a 50 MB `.xlsx` with many large sheets). The check runs on every read |
| `sandbox_missing` | `sandbox-exec` not found |
| `check_error` | The check result was unusable, or the file changed after the check |
| `warnings_not_acknowledged` | Warnings exist and no warning confirmation was recorded |
| `python_missing` | The Command Line Tools `python3` was not found (every xlide call is denied) |
| `internal_error` | Unexpected hook error |

If a hook denies a call, the skill stops and tells you why. It does not try to read the file another way.

If the skill stops at its first check because `xlide_doctor` returned a result or a permission prompt appeared, the guard hook is not running in this session. Hooks are off when `disableAllHooks` is set in any settings file, or when the managed setting `allowManagedHooksOnly` is on (see [Limitations](#limitations)). Do not use the plugin until the hook runs. If the check was refused with another reason, see the table above. If the skill stops at its Read check, the `Read(...)` deny rule for the intake folder is missing or does not match it: add it as described in [Configuration](#configuration) (for another folder, `Read(//abs/path/**)`). If a permission prompt appeared for that Read, decline it. The skill also stops when Read is turned off for the whole session (for example `--disallowedTools Read`), because the Read check then does not return the refusal of a deny rule. Start Claude Code without turning Read off, and add the deny from [Configuration](#configuration). If the skill stops at its first check because its Agent tool has a `name` or `team_name` parameter, agent teams are on: unset `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` or leave it empty, do not pass `--agent-teams`, and start Claude Code again. The skill also stops if it cannot see its Agent tool's definition; the subagent cannot be started in that session anyway.

`doctor.sh` items: `macos` (not macOS), `uvx` (uv not on PATH), `python3` (Command Line Tools missing, or its installation is not owned by root), `sandbox_exec` (`/usr/bin/sandbox-exec` missing), `intake_dir_protected` (the sandbox did not refuse Bash's listing of the intake folder: the required settings are missing, the sandbox is off, or the folder does not exist). If the xlide tools are not visible, uv may be missing, the first-run download failed, or a project's own `xlide` dropped the plugin's (see [Configuration](#configuration)).

<a name="maintenance"></a>

## Maintenance

The author maintains this in private time, as time allows. Regular updates are not promised, and replies to issues and pull requests are not promised either.

- Versions are pinned (xlide-mcp 1.2.4 and four dependencies). Security fixes to them do not arrive until the author bumps the pins. The other dependencies are not pinned: uv resolves them when it builds the environment, which can happen again on a later start, so their security fixes (and any other new version) can arrive without a bump.
- Pin the marketplace by commit SHA and keep auto-update off. Read the diff before you move the SHA.
- If you need fixes sooner, fork the repository and bump the pins yourself (MIT).
- The author's steps are in [docs/runbooks/maintenance.md](docs/runbooks/maintenance.md) (Japanese).

<a name="license"></a>

## License

MIT. See [LICENSE](LICENSE).

Thanks to the author of [xlide-mcp](https://github.com/WilliamSmithEdward/xlide_mcp) and to the authors of the libraries it is built on. They are MIT-licensed. They are not included in this repository; `uvx` fetches them from PyPI when the server starts.
