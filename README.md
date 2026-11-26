# workbook-intake

[日本語](README.ja.md)

A Claude Code plugin that runs a structural check on Excel workbooks received from outside before Claude analyzes them with xlide-mcp.

This is a personal project, not affiliated with xlide-mcp or NVIDIA SkillSpector.
Use it at your own risk. It does not guarantee safety.

> [!WARNING]
> The checks reduce some risks. They do not make a workbook safe to open or send anywhere. Read [Limitations](#limitations) before use.

## What it does

- xlide is limited to one intake folder (`~/workbook-intake` by default).
- Before xlide reads a file, you are asked to confirm that it contains no personal or confidential information. A hook records your answer; the model does not choose it.
- A hook then runs a structural check of the file inside a macOS Seatbelt sandbox (no network, no writes) and tells you the result in a fixed vocabulary.
- Only a read-only subagent can call xlide, and only its read-only tools. A hook blocks every other call.

The plugin contains no xlide code. xlide-mcp is fetched from PyPI at run time with pinned versions.

## Notes on use

Files you let Claude read are sent to Anthropic as model input, and may also stay on your machine.

1. Everything inside a file can be read: comments, defined names, VBA, Power Query, external link paths. Hidden sheets and protection do not hide anything. A file with personal data (names, addresses, dates of birth, income, loans) sends that data as it is.
2. Conversation logs are kept in plain text on your machine (`~/.claude/projects/<project>/*.jsonl`, 30 days by default; see `cleanupPeriodDays`).
3. A file from a customer or partner can contain text that tries to steer Claude (prompt injection). xlide runs read-only and the analyzing subagent has no Bash or Web tools. The main conversation, which receives the summary, still has its own tools and can be steered.
4. Cell values are the results Excel saved last. Recalculation (`calculate=true`) uses a different calculation engine and may differ from Excel. Claude can also misread. Check figures you pass on against Excel.
5. Whether you may send a file to Anthropic depends on your organization's rules and contracts. The plugin only asks you and records the answer. It cannot judge the content.

<a name="requirements"></a>

## Requirements

- macOS (the check uses Seatbelt, `sandbox-exec`).
- Command Line Tools (`xcode-select --install`), for `python3`.
- [uv](https://docs.astral.sh/uv/) (`uvx`).
- Claude Code 2.1.295 or later, because the hooks use `onFailure`. `plugin.json` declares this in `engines`, but Claude Code reads `engines` only from 2.1.323, so older versions do not enforce it. Pinning a marketplace by commit SHA (see Install) needs 2.1.324 or later.
- xlide runs on Python 3.15. If it is not on the machine, uv fetches it on the first start (where it cannot be fetched, the xlide tools are not visible).
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

Required (both). They stop Claude's Bash and Read tool from reading the intake folder. xlide and the hooks run outside the sandbox and can still read it. In a probe, `denyRead` alone still let the Read tool read, so both are needed. The skill stops when Bash can list the folder.

```json
{
  "sandbox": {
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

If a project defines its own `xlide` server with the same `uvx` command, Claude Code uses one of them only, and the plugin's is dropped as a duplicate (observed with Claude Code 2.1.331). Disable the project's with `"disabledMcpjsonServers": ["xlide"]`.

To use another intake folder, set `WORKBOOK_INTAKE_DIR` in the environment that starts Claude Code, and change both deny settings to the same folder.

<a name="usage"></a>

## Usage

1. Put the file in the intake folder (`.xlsx`, `.xlsm`, `.xltx`, `.xltm`, `.xlam`, `.xlsb`; up to 100 MB).
2. Ask Claude to analyze it by file name, for example "Analyze `sales.xlsx` with /workbook-intake:analyze". Claude cannot list the folder, so name the file.
3. The skill shows two fixed questions: the input confirmation, and, only if the check reported warnings, a warning confirmation. Answering "Confirmed" or "Continue" is recorded by a hook. The record is valid for this session and this file content only.
4. The read-only subagent `workbook-intake:excel-analyst` reads the workbook with xlide and returns a summary.

Google Sheets: not read directly. Download as `.xlsx` and put it in the intake folder (Apps Script is not included; Google-specific functions may not behave as in Excel). The claude.ai Google Sheets connector is outside this plugin's protection.

<a name="checks"></a>

## Checks

The check is a Python script run under Seatbelt. It prints only fixed codes, never text from the file.

Failure codes (the file is not read):

| Code | Meaning |
| --- | --- |
| `unsupported_extension` | Extension is not one of the supported ones |
| `file_too_large` | Over 100 MB |
| `encrypted` | Password-protected package |
| `not_zip` | Cannot be opened as a zip, or the ZIP layout could be read differently by different readers (an archive comment, prefix data, gaps or overlaps between entries, ZIP64 records, local headers that disagree with the central directory, a Unicode Path extra, flag bits 5 or 6, part data whose length or CRC differs from the central directory), or the zip inside a Power Query part is broken (non-canonical base64, section or part lengths that do not add up) |
| `too_many_parts` | More than 10,000 parts |
| `unsafe_part_name` | A part name has `..` or an absolute path, `\`, a drive letter (such as `C:`), NUL, an empty segment, a `.` segment, a directory name with content, or a name that disagrees with the UTF-8 flag, or two names differ only in letter case |
| `uncompressed_too_large` | Expands to more than 256 MB in total (including the zip inside a Power Query part), or a part named `customXml/item*.xml` (such as `item1.xml` or `itemProps1.xml`) is over 32 MB |
| `compression_ratio_too_high` | One part (including a part of the zip inside a Power Query part) compresses by more than 100 times |
| `xml_dtd` | A part has `<!DOCTYPE` or `<!ENTITY`. Every part is searched, not only XML, and so is the content of a Power Query part (the parts of the zip inside it and its metadata), so an SVG image or a macro that writes HTML can cause it |

Warning codes (you must confirm before the analysis continues):

| Code | Meaning |
| --- | --- |
| `vba_project` | Contains a VBA project |
| `external_link` | Links to external workbooks |
| `data_connection` | Contains data connections |
| `external_relationship` | A relationship points outside the file |
| `power_query` | Contains Power Query (DataMashup). Strings inside the queries (M code, query names, descriptions) are not checked |
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
- `disableAllHooks` can turn off hooks from a settings file at any scope, including the repository's `.claude/settings.json` (hooks from managed settings are exempt). Plugin hooks are expected to be turned off too (inferred, not verified). When they are off, the main conversation can call xlide, and neither the input confirmation nor the check runs. Do not use the plugin in such an environment.
- xlide expands VBA source with no size limit. A workbook with macros (the `vba_project` warning) can use a lot of memory.
- The input confirmation relies on a person answering the AskUserQuestion screen. In an environment where another plugin's hook or an SDK host fills in the answer, an approval can be recorded without a person confirming it.
- Tool names carry the prefix `mcp__plugin_workbook-intake_xlide__` (for example `mcp__plugin_workbook-intake_xlide__xlide_doctor`). A matcher that names only the server (`mcp__xlide__.*`) does not match them.
- xlide is visible to the main conversation too, because plugin subagents cannot declare their own MCP servers. Calls from the main conversation are blocked by the hook.
- A hook's allow only skips a prompt. Deny and ask rules in your settings still apply.
- Display tricks in a file name (look-alike characters, special spaces, combining marks) cannot be fully prevented. They need a real file of that name in the intake folder.
- `.xls` is not supported. xlide reads `.xlsb` sheets only on Windows (on macOS its sheet tool rejects `.xlsb`).
- The approval record lives in the plugin data directory. In an environment where a sandboxed command can write there, an approval can be forged.
- If the plugin cache is writable from a sandboxed session, the hooks could be modified. If your GitHub account is taken over, a bad update could be published; pinning by SHA with auto-update off helps you use only versions you have reviewed, but it does not prevent this.
- The environment can change where uv fetches from (for example `UV_DEFAULT_INDEX`).
- xlide finds `uvx` through PATH. Do not put a directory that a sandboxed command can write to at the front of PATH.
- macOS only. Windows live tools of xlide are not used.
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
| `intake_dir_invalid` | The intake folder is missing, a symlink, or `/` |
| `outside_intake` | The file is outside the intake folder |
| `not_regular_file` | Not a regular file |
| `unsupported_extension` | Extension not supported |
| `file_too_large` | Over 100 MB |
| `path_not_canonical` | The path is not its own real path, or has surrounding whitespace or control characters |
| `file_changed` | The file changed while it was being checked |
| `consent_store_unavailable` | The record cannot be written (plugin data directory missing) |
| `no_consent` | No input confirmation was recorded for this file content |
| `internal_error` | Unexpected hook error |

Guard hook denials (`workbook-intake: <reason>`, with failure or warning codes in parentheses when relevant):

| Reason | Meaning |
| --- | --- |
| `not_plugin_server` | The tool is not from this plugin's xlide (for example the project's own xlide) |
| `tool_not_allowed` | The tool is not on the allowlist (`hooks/allowed-tools.txt`) |
| `wrong_caller` | The caller is not `workbook-intake:excel-analyst` |
| `unexpected_path_argument` | A path-like argument other than `file_path` |
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

`doctor.sh` items: `macos` (not macOS), `uvx` (uv not on PATH), `python3` (Command Line Tools missing, or its installation is not owned by root), `sandbox_exec` (`/usr/bin/sandbox-exec` missing), `intake_dir_protected` (Bash can list the intake folder: the required settings are missing or the sandbox is off). If the xlide tools are not visible, uv may be missing, the first-run download failed, or a project's own `xlide` dropped the plugin's (see [Configuration](#configuration)).

<a name="maintenance"></a>

## Maintenance

The author maintains this in private time, as time allows. Regular updates are not promised, and replies to issues and pull requests are not promised either.

- Versions are pinned (xlide-mcp 1.2.4 and four dependencies). Security fixes to them do not arrive until the author bumps the pins.
- Pin the marketplace by commit SHA and keep auto-update off. Read the diff before you move the SHA.
- If you need fixes sooner, fork the repository and bump the pins yourself (MIT).
- The author's steps are in [docs/runbooks/maintenance.md](docs/runbooks/maintenance.md) (Japanese).

<a name="license"></a>

## License

MIT. See [LICENSE](LICENSE).

Thanks to the author of [xlide-mcp](https://github.com/WilliamSmithEdward/xlide_mcp) and to the authors of the libraries it is built on. They are MIT-licensed. They are not included in this repository; `uvx` fetches them from PyPI when the server starts.
