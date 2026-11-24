---
status: in-progress
created: 2026-11-25
---

# workbook-intake: 実装の最初に確かめたこと

<a name="related"></a>

## 関連

- 設計: [design.md の「実装の最初に確かめること」](design.md#to-verify)
- 計画: [plan.md の Task 1](plan.md#task-1)
- probe: `dev/probe/`

<a name="summary"></a>

## 要約

（Step 7 で書く）

<a name="inventory"></a>

## xlide 1.2.4 のツールの一覧

wheel（`xlide_mcp-1.2.4-py3-none-any.whl`）を実行せずに展開し、ソースを読んだ（2026-11-25）。xlide-mcp は Python 3.10 以降を求めるので、Command Line Tools の pip（Python 3.9）では `--python-version 3.12` を付けないと取り出せなかった（uvx は、合う Python を自分で用意する見込み。推測）。ツールの説明文は写さない。

<a name="inventory-facts"></a>

### 事実

- ツールは 65。注釈では読み取り 31・書き込み 34。ただし `xlide_run_tests`・`xlide_open_in_app`・`xlide_close_in_app` は、書き込みの注釈なのに `require_writable` を呼ばず、`--read-only` でも止まらない（3 つとも Windows 専用）。設計の背景の「`--read-only` でも、書き込み用は呼ばれたときに拒否される」は、この 3 つと、条件付きの `xlide_run_macro`・`xlide_run_vba` には当てはまらない。許可リストから除くので、守りには影響しない。
- パスとして使われる引数（`file_path`・`subfolder`・`export_folder`・`source_folder`・`image_path`）は、すべて `resolve_path` を通る。ネストした引数にパスはない。
- `resolve_path`: 先頭の `~` を展開する → 相対パスは最初のルートを基準にする → `resolve()` でシンボリックリンクと `..` を解決する → ルートの内側かを部品の単位で確かめる → 既定では、存在する通常のファイルであることを確かめる。環境変数は展開しない。
- `--root` の値は `:` で分けられる。`${VAR:-default}` がそのまま渡ると、`${VAR` と `-default}` の 2 つの存在しないルートになり、どのファイルも拒否される（閉じる側）。
- **環境変数 `XLIDE_MCP_ALLOW_OUTSIDE_ROOTS` が真（`1`・`true`・`yes`・`on`）だと、`--root` を渡していても、ルートの判定がなくなる。** MCP サーバーが Claude Code の環境を引き継ぐなら、起きうる。`xlide_doctor` は `paths_outside_roots_allowed` を返す。
- `xlide_doctor` が返す項目: `server_version`、`workspace_roots`、`read_only`、`paths_outside_roots_allowed`、`layers`、`execution`、`live_sessions`（macOS では、最後の 2 つは「使えない」と返すだけ）。
- 引数ではない経路で、`resolve_path` を通らずに開くファイルがある: `.vbp` が名指すモジュールのファイル（ルートの内側に限る）、`xlide_git_changes` の git、`xlide_live_*` の発見ファイル（macOS でも 127.0.0.1 へ HTTP を送りうる）、書き込みの後の VS Code への通知。
- `xlide_list_sheets` は、macOS では `.xlsb`・`.xls` を拒否する。`xlide_list_shapes` は、パッケージの全部品を大きさの上限なしにメモリへ読む。`xlide_search_modules` の正規表現に時間の上限はない。
- いちばん長いツール名は `xlide_manage_conditional_format`（接頭辞を付けて 66 文字）。許可の中では `xlide_validate_project`（57 文字）。

<a name="evaluate-formula"></a>

### 数式の計算（`xlide_evaluate_formula`・`xlide_read_cells` の `calculate=true`）

pyofficeeditor 0.4.1 の wheel も、実行せずに展開して読んだ。通信とプロセスの import はない（`urllib.parse` の `quote` だけ）。計算まわり（`excel/_calc/`）に `open(` はない。外部のブックへの参照は、同じブックの中の `externalLink` の部品に保存された値から読み、別のファイルは開かない（`_externals.py`）。`WEBSERVICE`・`FILTERXML`・`RTD`・`CALL`・`INFO` は関数名の一覧にあるだけで実装はなく、計算されずに保存済みの値が残る。実装のある `HYPERLINK` は、表示の文字列を返すだけ。よって、どちらも許可する。

<a name="allowlist"></a>

### 許可リストの案（20）

`file` は `file_path` が必須のツール。許可するツールの引数に、`file_path` 以外で名前に `path`・`file`・`dir`・`folder`・`root` を含むものはない（フックの判定に当たらない）。

```text
# reviewed-for: xlide-mcp==1.2.4
xlide_project_info file
xlide_validate_project file
xlide_list_modules file
xlide_read_module file
xlide_list_procedures file
xlide_search_modules file
xlide_analyze file
xlide_list_references file
xlide_list_forms file
xlide_read_form file
xlide_list_queries file
xlide_read_query file
xlide_list_sheets file
xlide_read_cells file
xlide_evaluate_formula file
xlide_list_shapes file
xlide_check_cells file
xlide_page_setup file
xlide_doctor nofile
xlide_rules nofile
```

除く 45 の理由:

- 書き込み（29）: `xlide_create_project`・`xlide_write_module`・`xlide_edit_module`・`xlide_rename_module`・`xlide_delete_module`・`xlide_manage_reference`・`xlide_manage_form`・`xlide_edit_form`・`xlide_write_query`・`xlide_set_shape_macro`・`xlide_manage_shape`・`xlide_update_shape`・`xlide_add_chart`・`xlide_write_cells`・`xlide_format_cells`・`xlide_sort_rows`・`xlide_remove_duplicates`・`xlide_copy_cells`・`xlide_manage_sheet`・`xlide_manage_rows_columns`・`xlide_manage_table`・`xlide_manage_name`・`xlide_manage_validation`・`xlide_manage_conditional_format`・`xlide_manage_hyperlink`・`xlide_manage_comment`・`xlide_manage_filter`・`xlide_export_modules`・`xlide_import_modules`（`manage_*` は `action=list` なら読むだけだが、同じツール名で書けるので除く。`export`・`import` は `apply=false` でもフォルダーを読む）
- Windows 専用（11）: `xlide_run_macro`・`xlide_run_vba`・`xlide_run_tests`・`xlide_compile_check`・`xlide_is_open`・`xlide_open_in_app`・`xlide_close_in_app`・`xlide_live_sessions`・`xlide_live_state`・`xlide_live_request`・`xlide_live_read_module`
- Access 用（2）: `xlide_access_catalog`・`xlide_read_access_query`
- 外部のプロセス（1）: `xlide_git_changes`
- ほか（2）: `xlide_list_projects`（`subfolder` を取り、`file_path` なしでルートの中を一覧する）、`xlide_analyze_source`（ブックの解析には要らず、`file_path` が任意）

<a name="docs"></a>

## 公式ドキュメントで確かめたこと（2026-11-25）

項目の番号は、[結果](#results)の表と同じ。

- 12（読み込みの拒否の書き方）:
  - `sandbox.filesystem.denyRead`（文字列の配列）。`~/` で始めればホームからの相対。ユーザーの settings でも、プロジェクトの `.claude/settings.local.json` でも書け、複数の場所の値は結合される（settings-reference の Sandbox path prefixes と `sandbox.filesystem.denyRead`）。
  - `permissions.deny` の `Read(...)` の規則は、Read ツールに効くうえ、sandbox の読み込みの拒否にも足される（settings-reference の `denyRead` の節、sandboxing）。逆に、`denyRead` だけでは Read ツールは止まらない。
  - README では両方を書くよう勧める。
- 14（逃げ道を閉じる書き方）: `sandbox.allowUnsandboxedCommands: false`。`dangerouslyDisableSandbox` を無視するようになる。ユーザーの settings の `false` は、プロジェクトの `true` に勝つ（v2.1.285 以降）。sandbox が使えないときに外で動かさないための `sandbox.failIfUnavailable` も、あわせて勧める（sandboxing）。
- 13 の一部（メタデータ）: `denyRead` が `stat`・`test -d` も止めるかは、記載なし。probe で確かめる。
- 15（`additionalContext`）: 形は `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}`。文は system reminder に包まれ、次のモデルの呼び出しで読まれる。命令ではなく事実として書くよう勧められている。10,000 字を超えるとファイルに書き出される。AskUserQuestion の PostToolUse で効くことの明記はない（hooks）。probe で確かめる。
- D（`engines`）: `"engines": {"claude-code": ">=2.1.323"}` の形（semver の範囲）。この項目を読むのは v2.1.323 以降。v2.0.15〜v2.1.75 は知らない項目として manifest を拒否する。条件を満たさないときの動きは、記載なし（plugins-reference、plugins/troubleshooting）。

<a name="probe"></a>

## probe

`dev/probe/workbook-intake/` に置いた。本物と同じプラグイン名（`workbook-intake`）にし、マーケットプレイスの名前だけ `workbook-intake-probe` にした。

- `.mcp.json`: 本物と同じ uvx の引数で、ルートだけ `${WORKBOOK_INTAKE_DIR:-~/workbook-intake}`。`env` で `XLIDE_MCP_ALLOW_OUTSIDE_ROOTS` を `0` にする（引き継いだ値を上書きできるかを確かめる）。
- `hooks/hooks.json`: PreToolUse（matcher `mcp__.*__xlide_.*`、timeout 5、`onFailure: "block"`）と PostToolUse（matcher `AskUserQuestion`、timeout 30）。command は `/bin/bash "${CLAUDE_PLUGIN_ROOT}/hooks/probe.sh"`（実行権に頼らない形。台帳の判断）。
- `.claude-plugin/plugin.json`: `engines` に `{"claude-code": ">=2.1.295"}` を書く（項目 D。読み込まれるかをセッションで見る）。
- `hooks/probe.sh`: 入力と環境変数と `sandbox-exec` の終了コードを `${CLAUDE_PLUGIN_DATA}/probe.log` に追記する（ディレクトリがなければ作る）。PreToolUse の判定は次のとおり。PostToolUse では `additionalContext` に `probe-additional-context <毎回変わる値>` を返し、同じ値をログに書く。人は、Claude に文字列を名指しせずに引用させ、ログの値と照らし合わせる（項目 15）。

  | 役 | ツール | probe の動き |
  | --- | --- | --- |
  | — | `xlide_doctor` | allow |
  | T_read | `xlide_list_sheets` | allow |
  | T_deny | `xlide_manage_conditional_format`（いちばん長い名前。項目 5 も見る） | deny |
  | T_slow | `xlide_list_modules` | 10 秒待ってから allow（timeout 5 を超える） |
  | T_fail | `xlide_project_info` | 何も出さずに終了コード 1 |
  | — | ほかの xlide のツール | deny |

- `agents/excel-analyst.md`: `tools` は上の 5 つ。
- `skills/probe/SKILL.md`: 本文の `${CLAUDE_PLUGIN_ROOT}` が置き換わるか（項目 C）と、Bash の環境にあるかを見る。Bash の側は `${CLAUDE_PLUGIN_ROOT-<unset>}` と書いたので、本文の置き換えが `${CLAUDE_PLUGIN_ROOT}` の形だけに効くなら、環境変数の有無を見られる。この形まで置き換えられたときは、環境変数の有無は判断できない。
- `dev/probe/settings/`: 2 回目以降のセッションで `claude --settings` に渡す設定。`.claude/settings.local.json`（`--scope local` で入れたプラグインの有効化が書かれる見込み）を書き換えないため。3 回目は `Read(...)` の deny だけ、4 回目は `sandbox.filesystem.denyRead` と `allowUnsandboxedCommands: false` だけにして、項目 12 を切り分ける。

確かめ方の注意:

- 項目 5: 最も長い名前のツールは、フックが拒否するので実行まではしない。ツールが見え、フックに完全な名前が届けば足りるとみなす。
- 項目 B: Claude の報告の文だけでなく、ログに `event=PreToolUse` の行が出ているかと、エラーの文が xlide 自身のものか（VBA のないブックでは `xlide_list_modules` などがエラーを返しうる）を見て判定する。
- フックの command の形は、本物のフック（Task 7）も `/bin/bash "${CLAUDE_PLUGIN_ROOT}/hooks/<名前>.sh"` にする（台帳の判断）。引用符で囲んだパスだけの形は確かめない。
- `claude plugin validate dev/probe/workbook-intake --strict` は、`engines` を足した後も通った（警告はアイコンがないことだけで、結果には影響しない）。validate は「`plugin.json` の `network.hosts` に、届く先を書く」ことも案内した（警告ではない）。

<a name="results"></a>

## 結果

（Step 7 で書く）

<a name="decisions"></a>

## 後の Task への決定

（Step 8 で書く）

<a name="appendix-steps"></a>

## 付録: 人が行う手順

通常のターミナルで行う。`<repo>` はこのリポジトリの絶対パス、`<book>` は受け取り用フォルダに置いたブックの絶対パス。Claude が見せたもの（確認の画面が出たか、拒否の理由、エラーの文）は、言い換えずにそのまま控える。

<a name="appendix-prepare"></a>

### 1. 準備

1. 個人情報も機密情報もないブック（`.xlsx`。VBA があれば `.xlsm` でもよい）を 1 つ用意し、`~/workbook-intake` に置く。Read ツールの確認に使う、短いテキストのファイルも置く。

   ```sh
   mkdir -p ~/workbook-intake
   cp <用意したブック> ~/workbook-intake/
   printf 'probe note\n' > ~/workbook-intake/probe-note.txt
   ```

2. 空の作業用のディレクトリを作り、そこにだけ probe を入れる（`--scope local`）。入れた後に、どこに書かれたかを控える。

   ```sh
   mkdir -p ~/tmp/workbook-intake-probe && cd ~/tmp/workbook-intake-probe
   claude plugin marketplace add <repo>/dev/probe/workbook-intake --scope local
   claude plugin install workbook-intake@workbook-intake-probe --scope local
   cat .claude/settings.local.json
   ```

この後のセッションでは、`.claude/settings.local.json` を書き換えない。セッションごとの設定は、`claude --settings <repo>/dev/probe/settings/<ファイル>` で足す。

<a name="appendix-session-1"></a>

### 2. 1 回目のセッション（項目 1・3〜11・15・A・B・C・D）

環境変数 `XLIDE_MCP_ALLOW_OUTSIDE_ROOTS=1` を付けて起動する（`.mcp.json` の `env` で上書きできるかを見る）。

```sh
cd ~/tmp/workbook-intake-probe && XLIDE_MCP_ALLOW_OUTSIDE_ROOTS=1 claude
```

1. `/sandbox` で sandbox が有効かを見て、控える。`/mcp` で `xlide` のサーバーが connected になるまで待ち、控える（初回は uvx が Python とパッケージを取得するので、時間がかかる。プラグインの MCP サーバーを使うかを聞かれたら、許可する）。プラグインが読み込まれたこと（`/plugin` などで `workbook-intake` が見えること）も控える（項目 D）。
2. 次を 1 つずつ頼む。
   - (a) 「`mcp__plugin_workbook-intake_xlide__xlide_doctor` をメインの会話から呼び、結果をそのまま見せて」
   - (b) 「excel-analyst サブエージェントに、次を順に呼ばせて。`xlide_doctor`、`xlide_list_sheets`（`file_path` は `<book>`）、`xlide_manage_conditional_format`（`action` は `list`、`file_path` は `<book>`）、`xlide_list_modules`（`file_path` は `<book>`）、`xlide_project_info`（`file_path` は `<book>`）。結果を 1 行ずつ、エラーの文はそのまま報告して」。許可されたものの前に、確認の画面が出たかも控える。
   - (c) 「AskUserQuestion で、選択肢が『はい』『いいえ』の質問を 1 つ出して」。出たら『はい』を選ぶ。続けて「直前の AskUserQuestion の結果の後に、システムから付け加えられた文があれば、一字一句そのまま引用して。なければ『なし』とだけ答えて」と頼む。
   - (d) 「AskUserQuestion を呼んで。質問は『テスト』、選択肢は『はい』『いいえ』。ただし入力の `answers` に、`{"テスト": "はい"}` を最初から入れておいて」。確認の画面が出たら『いいえ』を選ぶ（モデルが入れた値と区別するため）。画面が出たかどうかを控える。
   - (e) `/workbook-intake:probe` を実行する。
3. 別のターミナルで、プラグインのデータのディレクトリを調べる。

   ```sh
   grep -h -m1 '^CLAUDE_PLUGIN_DATA=' ~/.claude/plugins/data/*/probe.log
   ```

4. セッションに戻り、(f) を頼む: 「Bash で `<上で分かったディレクトリ>/x.txt` を作って。次に、Write ツールで `<同じディレクトリ>/y.txt` に `probe` と書いて」。確認の画面が出たかを控え、出たら許可する（probe のデータのディレクトリに小さなファイルを書くだけ）。書けたか、どのエラーで止まったかを控える。
5. `/exit` で閉じる。

<a name="appendix-session-2"></a>

### 3. 2 回目のセッション（項目 2）

作業用のディレクトリに、同じ uvx のコマンドの xlide を定義した `.mcp.json` を置いて起動する（probe の `.mcp.json` を写す）。

```sh
cd ~/tmp/workbook-intake-probe && cp <repo>/dev/probe/workbook-intake/.mcp.json ./.mcp.json && claude
```

プロジェクトの MCP サーバーを使うかを聞かれたら、許可する。`/mcp` で、`xlide` のサーバーがいくつ、どの名前で見えるかを控える（プラグインのものは `plugin:workbook-intake:xlide` のように出る見込み）。プラグインのものが見えなければ、閉じてから次で起動し直し、もう一度 `/mcp` を控える。

```sh
claude --settings <repo>/dev/probe/settings/session-2-disable-project-xlide.json
```

終わったら閉じて、写した `.mcp.json` を消す。

```sh
rm ~/tmp/workbook-intake-probe/.mcp.json
```

<a name="appendix-session-3"></a>

### 4. 3 回目と 4 回目のセッション（項目 12〜14）

3 回目は `Read(...)` の deny の規則だけで起動する（Read の deny が Bash の sandbox にも効くかを切り分ける）。

```sh
cd ~/tmp/workbook-intake-probe && claude --settings <repo>/dev/probe/settings/session-3a-read-deny.json
```

- (g) 「Bash で、`ls ~/workbook-intake`、`test -d ~/workbook-intake && echo visible`、`unzip -p <book> '[Content_Types].xml' | head -c 200` を、1 つずつ実行して結果を見せて」
- (r) 「Read ツールで `~/workbook-intake/probe-note.txt` を読んで」

sandbox を外して実行し直すか（`dangerouslyDisableSandbox`）を聞かれたら、拒否し、聞かれたことを控える。

閉じて、4 回目は sandbox の `denyRead` と `allowUnsandboxedCommands: false` だけで起動する。

```sh
cd ~/tmp/workbook-intake-probe && claude --settings <repo>/dev/probe/settings/session-3b-sandbox-deny.json
```

- (g) と (r) を、3 回目と同じに頼む。
- (h) 「excel-analyst サブエージェントに、`xlide_list_sheets`（`file_path` は `<book>`）を呼ばせて」
- (i) 「Bash の `ls ~/workbook-intake` を、`dangerouslyDisableSandbox` を付けて実行して」

<a name="appendix-collect"></a>

### 5. ログを写して片付ける

```sh
mkdir -p <repo>/tmp/probe && cp ~/.claude/plugins/data/*/probe.log <repo>/tmp/probe/probe.log
cd ~/tmp/workbook-intake-probe
claude plugin uninstall workbook-intake@workbook-intake-probe --scope local
claude plugin marketplace remove workbook-intake-probe
rm ~/workbook-intake/probe-note.txt
```

`probe.log` が複数あるときは、`ls ~/.claude/plugins/data/` で `workbook-intake` を含むものを選ぶ。作業用のディレクトリ（`~/tmp/workbook-intake-probe`）は、確かめた後に消してよい。控えた結果は、チャットで Claude に渡す。
