---
status: in-progress
created: 2026-11-25
---

# workbook-intake 実装計画

> [!IMPORTANT]
> エージェント向け: この計画は、superpowers:subagent-driven-development（推奨）か superpowers:executing-plans で、Task ごとに実行する。手順はチェックボックス（`- [ ]`）で進み具合を記録する。Task 1 と Task 11 は人の操作が要るので、メインの会話で行う。

**Goal:** 受け取り用フォルダの Excel を、検査と入力の確認を通したものだけ xlide-mcp で解析させる Claude Code プラグインを作る。

**Architecture:** プラグイン 1 つに、xlide の MCP サーバーの定義、解析用のサブエージェント、手順のスキル、2 つのフック（xlide の呼び出しを判定する PreToolUse と、入力の確認の承認を記録する PostToolUse）、検査のスクリプトとその Seatbelt を入れる。フックの判定は Python で書き、bash の入口から Command Line Tools の python3 で動かす。検査はフックの中で `sandbox-exec` の下で動かし、終了コードだけを使う。

**Tech Stack:** bash 3.2（macOS の `/bin/bash`）、Python 3.9（Command Line Tools の python3、標準ライブラリだけ）、Seatbelt（`sandbox-exec`）、uv（`uvx`）、GitHub Actions、shellcheck。

**Spec:** [design.md](design.md)（Crit で承認済み、2026-11-25）。実行する人は、この計画と設計の両方を読む。

<a name="related"></a>

## 関連

- 設計: [design.md](design.md)
- 公式ドキュメントで確かめたこと（2026-11-25）: `plugin.json` の必須は `name` だけ。`marketplace.json` のプラグインの `source` に `"./"` を書ける。フックの `onFailure` は `"continue"` か `"block"` で、v2.1.295 以降。PreToolUse の command フックは、時間切れでも `onFailure: "block"` でなければ呼び出しを止めない。`${CLAUDE_PLUGIN_DATA}` は `~/.claude/plugins/data/<id>/` で、アンインストールで消える。プラグインの `.mcp.json` は `${VAR:-default}` を展開するが、`~` の展開は記載がない。AskUserQuestion の入力の `answers` は「Claude は設定しない。フックが `updatedInput` で入れる」もの。`claude plugin validate <path> [--strict]` がある。

<a name="prerequisites"></a>

## 前提

- `main` はローカルにも GitHub にもまだない（空のリポジトリ）。[Task 1](#task-1) の最初に、`.gitignore`・`README.md`・`LICENSE` を `main` の Initial commit にし（ユーザーの指定）、作業ブランチ `docs/20261124_workbook-intake` をその上に載せ直す。以後の作業は作業ブランチで行う。
- Claude の Bash は Seatbelt の中で動き、入れ子の `sandbox-exec` は `sandbox_apply: Operation not permitted` で失敗する（2026-11-25 に確かめた）。`sandbox-exec` を使うテストは、Claude の Bash では飛ばされる。そのテストは、人が通常のターミナルで実行するか、CI（macOS）で実行する。

<a name="global-constraints"></a>

## 全体の制約

各 Task の要件に、暗黙に含まれる。

- 動く環境は macOS だけ。Python は Command Line Tools の python3（手元は 3.9.6）と標準ライブラリだけを使う。`match` 文、実行時に評価される `X | Y` の型、3.10 以降の標準ライブラリの機能を使わない（型注釈は `from __future__ import annotations` を付ければよい）。
- シェルは `/bin/bash` 3.2 で動かす。連想配列、`mapfile`、`${var,,}` を使わない。JSON の解釈は python3 で行い、jq に頼らない（使う人の環境にあるとは限らない）。
- 版の固定（設計のとおり）: `xlide-mcp==1.2.4`、`pyopenvba==6.6.0`、`pyofficeeditor==0.4.1`、`pyvbaanalysis==3.0.3`、`mcp==2.3.0`。
- 名前: プラグインとマーケットプレイスは `workbook-intake`、MCP サーバーは `xlide`、ツール名の接頭辞は `mcp__plugin_workbook-intake_xlide__`、サブエージェントは `excel-analyst`（呼び出し元の名前は `workbook-intake:excel-analyst`）、スキルは `analyze`。
- 受け取り用フォルダの既定は `~/workbook-intake`。
- 時間: フックの timeout は 30 秒、検査の上限は 20 秒（フックの中で決める）。
- 検査の閾値: ファイル 100 MB、部品 10,000、展開の合計 1 GB、1 部品の圧縮率 100 倍。
- 検査とフックの出力（標準出力、拒否の理由、JSON）には、固定の語彙・件数・真偽だけを入れる。ファイル由来の文字列（シート名、セルの文字列、部品の名前、ファイル名、パス）を入れない。
- 公開するファイル（SKILL.md、エージェントの指示、コードのコメント）は英語。README は英語の `README.md` を主とし、日本語版の `README.ja.md` を用意して、`README.md` からリンクする（ユーザーの指定、2026-11-25。設計の「公開するファイルは英語」から変える）。作業文書（`docs/work/`）と保守の runbook（`docs/runbooks/`）は日本語。
- xlide などのコードや長い文章（README、ツールの説明、エージェント向けの指示）をコピーしない。xlide の公式の物、NVIDIA SkillSpector の関連物に見せない。
- リポジトリに、業務の名前と中身、勤務先の情報、ユーザー名を含むパス（ホームディレクトリの絶対パス）を入れない。パスは `~` で書く。
- コミット: Conventional Commits。このリポジトリでは、コミットも PR も、タイトルと本文を英語にする（ユーザーの指定、2026-11-25。`AGENTS.md` に書いた。個人の既定の「本文は日本語」より優先する）。末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- フック（Task 6・7）と `doctor.sh`（Task 8）のテストは、`/usr/bin/xcode-select` の先の python3 を使うので macOS だけで動かす（`unittest.skipUnless(sys.platform == "darwin")`）。検査・定義・README・スキルとエージェントのテストは Linux でも動く。
- テストの実行: `PY="$(xcode-select -p)/usr/bin/python3"` として、全体は `"$PY" -B -m unittest discover -s tests -t . -v`、1 つのファイルは `"$PY" -B -m unittest tests.<module> -v`。`sandbox-exec` を使うテストを人と CI が実行するときは、`WORKBOOK_INTAKE_REQUIRE_SANDBOX=1` を付ける（付けると、`sandbox-exec` が使えないことを失敗として扱う）。

<a name="review-focus"></a>

## レビューの重点

設計が触れていないが、使う人がいちばん出会いそうな入力と、期待される動き。各行のテストは、担当の Task に入れてある。

1. 日本語のファイル名（Finder でコピーすると NFD、モデルが書くパスは NFC になりうる）: 承認したファイルを、同じファイルとして扱う。→ Task 6 `test_nfd_and_nfc_paths_are_same_file`、Task 7 `test_consent_matches_across_unicode_normalization`
2. 大文字の拡張子（`.XLSX`。Windows から届くファイルに多い）: 対象の拡張子として扱う。→ Task 3 `test_uppercase_extension_passes`、Task 7 `test_uppercase_extension_allowed`
3. 100 MB を超えるファイル: フックが SHA-256 を計算する前に拒否する（計算に時間がかかってフックが時間切れになると、呼び出しが止まらないおそれがあるため）。→ Task 7 `test_oversized_file_denied_before_hashing`
4. 固定の文の質問だが、選択肢の説明・数・`multiSelect`・質問の数が違う: 承認を記録しない（人が見る説明を書き換えて、誤った選択をさせる経路を断つ）。→ Task 6 `test_altered_options_not_recorded`
5. 許可リストのツールに、`file_path` 以外のパスらしい引数（`output_path`・`directory` など）がある: 拒否する。→ Task 7 `test_extra_path_argument_denied`

<a name="design-additions"></a>

## 設計への補足

設計で「実装者が決めてよい」とされた範囲で、この計画が決めたこと。設計の目標を変えるものはない。

- フックの判定は Python（`hooks/guard_xlide.py`・`hooks/record_consent.py`）で書き、`hooks/guard-xlide.sh`・`hooks/record-consent.sh` は python3 を探して起動する入口にする。JSON・`realpath`・SHA-256・時間の上限付きの子プロセスを、bash 3.2 と macOS の標準のコマンドだけで書くと誤りやすいため。フックのテストも、bash ではなく Python の `unittest` から入口のスクリプトを動かす形にする（設計の「フックのテスト（bash）」から変える）。
- 文字列の検査は、設計が挙げた部品に限らず、`customXml/` を除くすべての XML の部品で行う。部品の名前は関係（`.rels`）で変えられるので、決まった名前だけを見ると、名前を変えるだけで検査を外せるため。シートの状態は、`_rels/.rels` の `officeDocument` の先の部品から読む。
- 圧縮率の判定は、展開した量が 100 KiB を超えた部品だけに行う（Apache POI の既定と同じ考え方）。XML は小さな部品でも 100 倍を超えることがあり、誤検知になるため。
- `<!DOCTYPE`・`<!ENTITY` は、UTF-8 に加えて UTF-16（LE・BE）の符号でも探す。UTF-16 の XML で、ASCII の検索を外されるため。
- 受け取り用フォルダ自身がシンボリックリンクのときは、フックも拒否する（doctor.sh だけでなく）。
- [Task 1](#task-1) に、設計の一覧にない確認を 4 つ足した（A〜D）。特に A は、入力の確認の強制が成り立つかに関わる。

---

<a name="file-structure"></a>

## ファイルの構成

| ファイル | 役割 | Task |
| --- | --- | --- |
| `.gitignore` | `tmp/`・`__pycache__/`・`.DS_Store`（`main` の Initial commit） | 1 |
| `LICENSE` | MIT（`main` の Initial commit） | 1 |
| `README.md` | 最小の README（`main` の Initial commit）。Task 10 で書き足す | 1・10 |
| `AGENTS.md`・`CLAUDE.md` | このリポジトリの規則（コミットと PR は英語）。`CLAUDE.md` は `@AGENTS.md` の取り込みだけ。plan の承認の前に追加済み | — |
| `docs/work/20261124_workbook-intake/research-plugin-behavior.md` | 実装の最初に確かめた結果と、xlide のツールの一覧 | 1 |
| `dev/probe/` | 確かめるための probe のプラグイン。Claude Code の更新の後にも使う | 1 |
| `.claude-plugin/plugin.json`・`.claude-plugin/marketplace.json` | プラグインとマーケットプレイス | 2 |
| `.mcp.json` | xlide の定義 | 2 |
| `tests/__init__.py`・`tests/test_manifests.py`・`tests/test_repository.py` | 定義の固定値と、リポジトリに入れてはいけないもの | 2 |
| `tests/workbook_factory.py` | テスト用のブックを作る（二進のファイルを追跡しない） | 3 |
| `scripts/check_workbook.py` | 検査。単独で動く（Seatbelt の中では自分と対象のファイルしか読めないので、ほかのモジュールを import しない） | 3・4 |
| `tests/test_check_workbook.py` | 検査のテスト | 3・4 |
| `scripts/check_workbook.sb` | 検査の Seatbelt | 5 |
| `hooks/intake_common.py` | 受け取り用フォルダ、ファイルの判定、固定の文、承認の記録、検査の起動 | 5・6 |
| `tests/test_sandbox_profile.py` | Seatbelt と検査の起動のテスト | 5 |
| `hooks/record_consent.py`・`hooks/record-consent.sh` | 承認の記録 | 6 |
| `tests/test_record_consent.py` | 承認の記録のテスト | 6 |
| `hooks/guard_xlide.py`・`hooks/guard-xlide.sh`・`hooks/hooks.json`・`hooks/allowed-tools.txt` | xlide の呼び出しの判定 | 7 |
| `tests/test_guard_xlide.py` | 判定のテスト | 7 |
| `scripts/doctor.sh`・`tests/test_doctor.py` | 前提の確認 | 8 |
| `agents/excel-analyst.md`・`skills/analyze/SKILL.md`・`tests/test_skill_and_agent.py` | サブエージェントとスキル | 8 |
| `.github/workflows/ci.yml` | CI | 9 |
| `.github/dependabot.yml`・`deps/requirements.txt` | 依存の新しい版と脆弱性の検知（`deps/` は `.mcp.json` の固定の写し） | 9 |
| `README.md`・`README.ja.md`・`tests/test_readme.py` | README（英語が主、日本語版） | 10 |
| `docs/runbooks/maintenance.md` | 保守の runbook（日本語。Claude が読んで作者を案内する） | 10 |
| `docs/work/20261124_workbook-intake/test-report.md` | 実機での確認とレビューの記録 | 11・12 |

---

<a name="task-1"></a>

### Task 1: 実装の最初に確かめる

設計の「[実装の最初に確かめること](design.md#to-verify)」を、使い捨てのプラグイン（probe）で確かめる。結果で、後の Task の書き方が決まる項目がある。設計と違う結果が 1 つでも出たら、Task 2 に進まずに止まり、ユーザーに相談する。

**Files:**
- Create（`main` の Initial commit）: `.gitignore`、`LICENSE`、`README.md`
- Create: `docs/work/20261124_workbook-intake/research-plugin-behavior.md`
- Create: `dev/probe/workbook-intake/` 以下と `dev/probe/README.md`（Claude Code の更新の後に確かめ直すために残す。[Task 10](#task-10) の runbook から使う）
- Create（追跡しない）: `tmp/xlide-wheel/`、`tmp/xlide-src/`、`tmp/probe/probe.log`

**Interfaces:**
- Produces: research に、次を書く。後の Task はこれを読む。
  - 確かめた項目ごとの結果（設計どおりか、違うか）と根拠（ログの該当箇所）。
  - xlide 1.2.4 のツールの一覧: 名前、読み取りか書き込みか、パスらしい引数の名前、`file_path` が必須か。
  - 許可リストの案（`hooks/allowed-tools.txt` の形。[Task 7](#task-7)）。
  - AskUserQuestion の、人が選んだ答えが入る項目の場所（[Task 6](#task-6) の `selected_answer` が読む場所）。
  - 受け取り用フォルダを環境変数で変えられるか（[Task 6](#task-6) の `intake_dir`）。

- [ ] **Step 1: `main` の Initial commit を作る（ユーザーの指定）**

作業ブランチの変更がすべてコミット済みであることを確かめてから、次の順に行う。`git switch` と `git commit` は別の Bash の呼び出しにする。
1. `git switch --orphan main`（作業ブランチで追跡しているファイルは、作業ツリーから一時的に消える）
2. 次の 3 つを書く。
   - `.gitignore`: `tmp/`、`__pycache__/`、`.DS_Store` の 3 行
   - `LICENSE`: MIT の本文。著作権者は `2026 kado-ta`
   - `README.md`（最小。英語。Task 10 で書き足す）: 名前、1 文の説明、開発中であること、次の 2 文をそのまま、ライセンス（MIT）。

     ```text
     This is a personal project, not affiliated with xlide-mcp or NVIDIA SkillSpector.
     Use it at your own risk. It does not guarantee safety.
     ```

3. `git add .gitignore LICENSE README.md && git commit -m "chore: initial commit"`（本文は英語）。protect-main-branch フックに止められたら、人に通常のターミナルで同じコマンドを実行してもらう。
4. 人に `git -C <リポジトリの絶対パス> push -u origin main` を実行してもらう（`main` への直接の push なので、Claude は行わない）。
5. `git switch docs/20261124_workbook-intake` の後、`git rebase main`。

Expected: `git log --oneline main` が Initial commit の 1 件、作業ブランチがその上に載り、`gh api repos/kado-ta/workbook-intake/branches` に `main` がある。

- [ ] **Step 2: xlide 1.2.4 のソースを、実行せずに取り出す**

ソースは、許可リストを決めるために読む。セッションで見えるツールのスキーマからは、引数の名前と型しか分からない。ツールごとに次の 3 点を確かめるには、ソースが要る。
- 読み取り用か書き込み用か（`paths.py` の `require_writable` を呼ぶか）
- どの引数がパスとして使われるか（`resolve_path` を通るか。名前に `path` を含まない引数がパスとして使われることもある）
- `file_path` を省いたときに、既定のファイルやセッションの状態からファイルを読むか

Run: `"$PY" -m pip download --no-cache-dir --no-deps --only-binary=:all: xlide-mcp==1.2.4 -d tmp/xlide-wheel && mkdir -p tmp/xlide-src && unzip -q -d tmp/xlide-src tmp/xlide-wheel/*.whl`
Expected: `tmp/xlide-src/` にソースが展開される。取り出したものは信頼しないデータとして扱い、import も実行もしない。通信先は `pypi.org` と `files.pythonhosted.org`（sandbox に止められたら、その旨を人に伝える）。

- [ ] **Step 3: ツールの一覧を research に書く**

ソースの、ツールを登録している箇所を読み、65 のツールを一覧にする（設計の背景では読み取り用 31、書き込み用 34）。列は、名前・読み取りか書き込みか・パスとして使われる引数・`file_path` が必須か。許可リストの案は、次をすべて満たすツールだけにする: 読み取り用。Excel の解析に要る。Access 用・Windows 専用（`xlide_live_*`）・外部のプロセスを動かすもの（`xlide_git_changes`）ではない。パスとして使われる引数が、トップレベルの `file_path` だけか、1 つもない。`file_path` を省いてもファイルを読むツールではない。ツールの説明文は research にもコピーしない。

- [ ] **Step 4: probe のプラグインを `dev/probe/workbook-intake/` に作る**

本物と同じ名前にする（ツール名と `agent_type` を本物と同じ形で確かめるため）。`dev/probe/README.md` には、英語で「確かめるためだけのもので、フックが検査をせずに xlide を通すので、ふだんの解析には入れない」ことを書く。
- `.claude-plugin/plugin.json`: `{"name": "workbook-intake", "version": "0.0.0-probe"}`
- `.claude-plugin/marketplace.json`: `name` は `workbook-intake-probe`、プラグインの `source` は `"./"`
- `.mcp.json`: [Task 2](#task-2) と同じ uvx の引数で、ルートだけ `"${WORKBOOK_INTAKE_DIR:-~/workbook-intake}"` にする。
- `hooks/hooks.json`: PreToolUse（matcher `mcp__.*__xlide_.*`、timeout 5、`onFailure: "block"`）と PostToolUse（matcher `AskUserQuestion`）。command は `"\"${CLAUDE_PLUGIN_ROOT}/hooks/probe.sh\""` の形（引用符付き）で書き、この形が動くことも確かめる。
- `hooks/probe.sh`: 標準入力の JSON と、`CLAUDE_PLUGIN_ROOT`・`CLAUDE_PLUGIN_DATA`・`WORKBOOK_INTAKE_DIR` の値と、`/usr/bin/sandbox-exec -n no-network /usr/bin/true` の終了コードを、`${CLAUDE_PLUGIN_DATA}/probe.log` に追記する。PreToolUse では、ツール名で次のように振る舞う: `xlide_doctor` → allow を返す。一覧から選んだ `file_path` を取る読み取り用のツール 1 つ（以下 T_read）→ allow。別のツール 1 つ（T_deny）→ deny。もう 1 つ（T_slow）→ 10 秒待つ（timeout 5 を超える）。もう 1 つ（T_fail）→ 何も出さずに終了コード 1。
- `agents/excel-analyst.md`: `tools` に、上の 5 つのツールの完全な名前を書く。
- `skills/probe/SKILL.md`: 本文に `${CLAUDE_PLUGIN_ROOT}` を書き、Bash で `echo` させる（確かめること C）。

- [ ] **Step 5: probe を検証する**

Run: `claude plugin validate dev/probe/workbook-intake --strict`
Expected: 終了コード 0。

- [ ] **Step 6: 人が probe のセッションを動かす**

人に、通常のターミナルで次を行うよう頼む。手順は research の付録に、そのまま貼れる形で書いておく。
1. `~/workbook-intake` を作り、個人情報も機密情報もないブックを 1 つ置く。
2. 空の作業用のディレクトリで、`claude plugin marketplace add <リポジトリの絶対パス>/dev/probe/workbook-intake` と `claude plugin install workbook-intake@workbook-intake-probe` を実行し、`claude` を起動する。
3. セッションで、Claude に次を順に頼む: (a) メインの会話から `xlide_doctor` を呼ぶ。(b) excel-analyst に、`xlide_doctor`・T_read（置いたブックの絶対パス）・T_deny・T_slow・T_fail を呼ばせる。(c) AskUserQuestion で質問を 1 つ出させ、人が答える。(d) AskUserQuestion を、`answers` に答えを入れた形で呼ばせる（確かめること A）。(e) probe スキルを起動する。(f) Bash と Write ツールで、`probe.log` のあるディレクトリにファイルを書かせる。
4. その作業用のディレクトリに、同じ uvx のコマンドの xlide を定義した `.mcp.json` を置いて起動し直し、プラグインの xlide のツールが見えるかを確かめる。見えなければ、`.claude/settings.local.json` の `disabledMcpjsonServers` に `xlide` を足して、もう一度確かめる。
5. `probe.log` を `tmp/probe/probe.log` に写す（アンインストールで消えるため。ログにはブックのパスが入るので、コミットしない）。

- [ ] **Step 7: 結果を research に書く**

`tmp/probe/probe.log` を読み、次の表を埋める。設計の項目（1〜11）を先に、足した項目（A〜D）を後に書く。

| # | 確かめること | 設計の想定 |
| --- | --- | --- |
| 1 | サブエージェントから呼んだときの `agent_type` | `workbook-intake:excel-analyst` |
| 2 | プロジェクトの `.mcp.json` に同じコマンドの xlide があるとき、プラグインの xlide が外されるか。`disabledMcpjsonServers` で戻るか | 外されうる。戻る |
| 3 | `tool_input` に MCP の引数（`file_path`）がそのまま入るか | 入る |
| 4 | allow で確認が出ないか。deny で止まり、理由が出るか | そのとおり |
| 5 | 最も長いツール名で呼べるか（ドキュメントの目安は 128 文字） | 呼べる |
| 6 | `.mcp.json` の `${WORKBOOK_INTAKE_DIR:-~/workbook-intake}` と `~` の展開（`xlide_doctor` のルートで見る） | 未定 |
| 7 | マーケットプレイスの `source: "./"` で入れられるか | 入れられる |
| 8 | フックから `sandbox-exec` を使えるか（終了コード 0） | 使える |
| 9 | PostToolUse の入力に、AskUserQuestion の質問の文と、人が選んだ答えが入るか。どの項目か | 入る |
| 10 | サブエージェントの呼び出しの `session_id` が、メインの会話の AskUserQuestion のものと同じか | 同じ |
| 11 | `${CLAUDE_PLUGIN_DATA}` に、Bash（sandbox）と Write ツールから書けないか | 書けない |
| A | モデルが `answers` を入れて AskUserQuestion を呼んだとき、人への確認が出るか。PostToolUse に何が入るか | 確認が出る。モデルの値で答えを偽れない |
| B | T_slow（時間切れ）と T_fail（終了コード 1）が、`onFailure: "block"` で止まるか | 止まる |
| C | SKILL.md の `${CLAUDE_PLUGIN_ROOT}` が、プラグインの場所に置き換わるか | 置き換わる |
| D | `plugin.json` の `engines` で、Claude Code の最低の版（`onFailure` が使える 2.1.295）を宣言できるか（manifest reference の書式を読み、validate で確かめる） | 未定 |

- [ ] **Step 8: 判定する**

1・3・4・8・9・10・11・A・B のどれかが想定と違えば、ここで止まり、ユーザーに結果と、設計のどこが成り立たないかを伝える。特に A で答えを偽れる場合は、[入力の確認](design.md#consent)の強制の方法を考え直す必要がある。2・5・6・7・C・D は、結果に合わせて後の Task の書き方を選ぶ（research に、どれを選んだかを書く）。

- [ ] **Step 9: 人に probe を片付けてもらう**

`claude plugin uninstall workbook-intake@workbook-intake-probe`、`claude plugin marketplace remove workbook-intake-probe`、作業用のディレクトリの削除。

- [ ] **Step 10: コミットする**

```bash
git add dev/probe docs/work/20261124_workbook-intake/research-plugin-behavior.md
git commit -m "docs: record plugin behavior checks for workbook-intake"
```

---

<a name="task-2"></a>

### Task 2: プラグインの定義

**Files:**
- Create: `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`.mcp.json`
- Create: `tests/__init__.py`（空）、`tests/test_manifests.py`、`tests/test_repository.py`

**Interfaces:**
- Consumes: research の 6（展開）・7（`source`）・D（`engines`）
- Produces: `XLIDE_ARGS`（下の Step 3 の引数の並び。テストが固定する）

- [ ] **Step 1: 失敗するテストを書く**

```python
class ManifestTest(unittest.TestCase):
    def test_plugin_json(self):
        p = load_json(".claude-plugin/plugin.json")
        self.assertEqual(p["name"], "workbook-intake")
        self.assertEqual(p["license"], "MIT")

    def test_marketplace_json(self):
        m = load_json(".claude-plugin/marketplace.json")
        self.assertEqual(m["name"], "workbook-intake")
        self.assertEqual([(x["name"], x["source"]) for x in m["plugins"]], [("workbook-intake", "./")])

    def test_mcp_json_pins_versions_and_read_only(self):
        s = load_json(".mcp.json")["mcpServers"]
        self.assertEqual(list(s), ["xlide"])
        self.assertEqual(s["xlide"]["command"], "uvx")
        self.assertEqual(s["xlide"]["args"], XLIDE_ARGS)

    def test_probe_pins_match_plugin(self):
        # dev/probe/workbook-intake/.mcp.json の args が、"--root" の次の値を除いて XLIDE_ARGS と同じ

class RepositoryTest(unittest.TestCase):
    def test_no_user_home_paths_in_tracked_files(self):
        # git ls-files の全ファイルが re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/") に一致しないこと
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_manifests tests.test_repository -v`
Expected: `test_plugin_json` などが FileNotFoundError で失敗し、`test_no_user_home_paths_in_tracked_files` は通る。

- [ ] **Step 3: 定義を書く**

- `plugin.json`: `name`・`version`（`0.1.0`）・`description`・`author.name`（`kado-ta`）・`license`（`MIT`）・`repository`（`https://github.com/kado-ta/workbook-intake`）。research の D で書けると分かれば、`engines` で 2.1.295 以上を宣言する。書けなければ、README の必要なものに書く（[Task 10](#task-10)）。
- `marketplace.json`: `name`・`owner.name`（`kado-ta`）・`plugins`（`name`、`source: "./"`、`description`）。
- `.mcp.json` の `xlide` の `args`（`XLIDE_ARGS`）。ルートは research の 6 の結果で、展開されるなら `${WORKBOOK_INTAKE_DIR:-~/workbook-intake}`、されないなら `~/workbook-intake`（`~` は xlide が展開する）。

```json
["--no-config",
 "--from", "xlide-mcp==1.2.4",
 "--with", "pyopenvba==6.6.0",
 "--with", "pyofficeeditor==0.4.1",
 "--with", "pyvbaanalysis==3.0.3",
 "--with", "mcp==2.3.0",
 "xlide-mcp", "--root", "<research の 6 で決めた値>", "--read-only"]
```

- [ ] **Step 4: テストと validate が通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_manifests tests.test_repository -v && claude plugin validate . --strict`
Expected: すべて PASS、validate は終了コード 0。

- [ ] **Step 5: コミットする**

```bash
git add .claude-plugin .mcp.json tests/__init__.py tests/test_manifests.py tests/test_repository.py
git commit -m "feat: add plugin manifests and pinned xlide server"
```

---

<a name="task-3"></a>

### Task 3: 検査（不合格の判定）

**Files:**
- Create: `tests/workbook_factory.py`、`scripts/check_workbook.py`、`tests/test_check_workbook.py`

**Interfaces:**
- Produces（`tests/workbook_factory.py`）:
  - `minimal_parts() -> dict[str, bytes]`: 開ける最小の `.xlsx`（`[Content_Types].xml`、`_rels/.rels`、`xl/workbook.xml`、`xl/_rels/workbook.xml.rels`、`xl/worksheets/sheet1.xml`、`xl/sharedStrings.xml`）
  - `write_workbook(path: str, parts: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> str`
- Produces（`scripts/check_workbook.py`）:
  - 定数: `SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam", ".xlsb")`、`MAX_FILE_BYTES = 100 * 1024 * 1024`、`MAX_PARTS = 10_000`、`MAX_TOTAL_UNCOMPRESSED = 1024 ** 3`、`MAX_RATIO = 100`、`RATIO_GRACE_BYTES = 100 * 1024`
  - `check(path: str) -> dict`: `{"result": "pass" | "fail", "failures": [str], "warnings": [str], "counts": {str: int}}`。`failures`・`warnings` は下の語彙の重複のない並び。
  - `main(argv: list[str]) -> int`: 引数が絶対パス 1 つでなければ `{"result": "error", "failures": ["usage"], ...}` で 2。読めなければ `"unreadable"` で 2。それ以外は `check` の JSON を 1 行で出し、合格 0・不合格 1。
  - 不合格の語彙: `unsupported_extension`、`file_too_large`、`encrypted`、`not_zip`、`too_many_parts`、`unsafe_part_name`、`uncompressed_too_large`、`compression_ratio_too_high`、`xml_dtd`

- [ ] **Step 1: 失敗するテストを書く**

閾値の大きいもの（1 GB・10,000）は、`mock.patch.object(check_workbook, "MAX_TOTAL_UNCOMPRESSED", 1024 * 1024)` のように定数を小さくして試す。

```python
def test_minimal_workbook_passes(self):                 # result == "pass", failures == []
def test_uppercase_extension_passes(self):              # "book.XLSX" → "pass"（レビューの重点 2）
def test_unsupported_extension_fails(self):             # ".xls"・".csv"・".docm" → "unsupported_extension"
def test_file_too_large_fails(self):                    # MAX_FILE_BYTES を小さくする → "file_too_large"
def test_not_zip_fails(self):                           # 中身がテキスト → "not_zip"
def test_ole_encrypted_package_fails(self):             # OLE の先頭 8 バイト + UTF-16LE の "EncryptedPackage" → "encrypted"
def test_zip_encryption_flag_fails(self):               # flag_bits の bit 0 を立てた部品 → "encrypted"
def test_too_many_parts_fails(self):                    # MAX_PARTS を小さくする → "too_many_parts"
def test_unsafe_part_names_fail(self):                  # "../x.xml"・"/x.xml"・"xl/../../x.xml"・"C:/x.xml"・"xl\\..\\x.xml" → "unsafe_part_name"
def test_total_uncompressed_limit_fails(self):          # → "uncompressed_too_large"
def test_compression_ratio_fails(self):                 # 2 MB のゼロの部品 → "compression_ratio_too_high"
def test_small_highly_compressed_part_passes(self):     # 50 KiB の繰り返しの XML（100 倍超、RATIO_GRACE_BYTES 未満）→ "pass"
def test_doctype_fails(self):                           # sheet1.xml に "<!DOCTYPE" → "xml_dtd"
def test_entity_fails(self):                            # "<!ENTITY" → "xml_dtd"
def test_doctype_in_utf16_part_fails(self):             # UTF-16LE（BOM 付き）の "<!DOCTYPE" → "xml_dtd"
def test_doctype_split_across_read_chunks_fails(self):  # 読み込みの区切りをまたぐ位置に "<!DOCTYPE" → "xml_dtd"
def test_cli_usage_error(self):                         # 相対パス・引数なし → 終了コード 2、failures == ["usage"]
def test_cli_output_has_no_file_derived_strings(self):  # シート名・部品名・ファイル名に目印の文字列を入れ、標準出力に含まれないこと
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: `check_workbook` を import できずに失敗する。

- [ ] **Step 3: `check(path)` と `main(argv)` を書く**

判定の順: 拡張子（小文字にして比べる）→ 大きさ → 先頭の OLE の署名（`D0 CF 11 E0 A1 B1 1A E1`。`EncryptedPackage` の UTF-16LE を含めば `encrypted`、含まなければ `not_zip`）→ zip として開く → 部品の数 → 部品名 → 部品ごとの展開。不合格が 1 つ出たら、その時点で止めてよい。

部品の展開は、宣言のサイズを信じずに、実際に読んで数える。

```text
for 部品 in 部品の一覧:
    暗号化の bit が立っていれば encrypted
    64 KiB ずつ読む:
        合計と部品の展開量に足す。合計 > MAX_TOTAL_UNCOMPRESSED なら uncompressed_too_large
        部品の展開量 > RATIO_GRACE_BYTES かつ 展開量 > MAX_RATIO * max(compress_size, 1) なら compression_ratio_too_high
        XML の部品（.xml・.rels・.vml）なら、前の塊の末尾（探す語の最長の長さ - 1 バイト）とつないで、
          "<!DOCTYPE" と "<!ENTITY" を UTF-8・UTF-16LE・UTF-16BE の 3 つの符号で探す。あれば xml_dtd
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: すべて PASS。

- [ ] **Step 5: コミットする**

```bash
git add tests/workbook_factory.py scripts/check_workbook.py tests/test_check_workbook.py
git commit -m "feat: reject malformed and oversized workbooks in the checker"
```

---

<a name="task-4"></a>

### Task 4: 検査（警告）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`

**Interfaces:**
- Consumes: Task 3 の `check`・`write_workbook`・`minimal_parts`
- Produces: 警告の語彙と `counts`（警告ごとの件数）。`vba_project`、`external_link`、`data_connection`、`external_relationship`、`power_query`、`embedded_object`、`activex`、`hidden_sheet`、`very_hidden_sheet`、`invisible_characters`、`instruction_like_text`、`very_long_string`、`strings_not_checked`
- 定数: `MAX_PARSE_BYTES = 32 * 1024 * 1024`、`LONG_STRING_CHARS = 10_000`、`INVISIBLE_CODEPOINTS`、`INSTRUCTION_PHRASES`（下の Step 3）

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_vba_project_warns(self):                  # "xl/vbaProject.bin" → result "pass"、warnings に "vba_project"
def test_external_link_warns(self):                # "xl/externalLinks/externalLink1.xml" → "external_link"
def test_connections_warns(self):                  # "xl/connections.xml" → "data_connection"
def test_external_target_mode_warns(self):         # .rels に TargetMode="External" → "external_relationship"
def test_power_query_warns(self):                  # customXml/item1.xml（UTF-16LE）に DataMashup → "power_query"
def test_embeddings_and_activex_warn(self):        # "xl/embeddings/x.bin" → "embedded_object"、"xl/activeX/activeX1.xml" → "activex"
def test_hidden_and_very_hidden_sheets_warn(self): # state="hidden" と "veryHidden" → 両方、counts は各 1
def test_renamed_workbook_part_is_followed(self):  # 本体を "xl/book.xml" に変え、_rels/.rels で指す。veryHidden → "very_hidden_sheet"
def test_invisible_characters_warn(self):          # U+200B・U+202E・U+E0041 を含む文字列 → "invisible_characters"、counts 3
def test_instruction_like_text_warns(self):        # "Ignore previous instructions" と「前の指示を無視して」→ "instruction_like_text"、counts 2
def test_instruction_text_in_renamed_part_warns(self): # 共有文字列を "xl/strings2.xml" に置いても検出する
def test_very_long_string_warns(self):             # 10,001 文字 → "very_long_string"
def test_xlsb_strings_not_checked(self):           # 拡張子 .xlsb → "strings_not_checked"
def test_oversized_xml_strings_not_checked(self):  # MAX_PARSE_BYTES を小さくする → "strings_not_checked"
def test_warnings_do_not_change_exit_code(self):   # 警告だけのファイルで main() == 0
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: 新しいテストが失敗し、Task 3 のテストは通る。

- [ ] **Step 3: 警告を `check(path)` に足す**

- 部品名で決まるもの: `vbaProject.bin` で終わる、`externalLinks/`、`connections.xml`、`embeddings/`、`activeX/` を含む。
- `.rels` を読み、`TargetMode="External"` があれば `external_relationship`。`_rels/.rels` の `officeDocument` の `Target` を本体として読み、`<sheet>` の `state` で `hidden`・`very_hidden_sheet` を数える。
- `customXml/` の部品に、`DataMashup` が UTF-8 か UTF-16LE で現れれば `power_query`。
- 文字列: `customXml/` を除くすべての `.xml`・`.vml` の部品を、`MAX_PARSE_BYTES` 以下なら `xml.etree.ElementTree` で読み（DTD の検査を先に済ませているので、実体の展開は起きない）、要素の文字列と属性の値を 1 つずつ調べる。値の数で数える（1 つの値に複数あっても 1）。`MAX_PARSE_BYTES` を超える部品があれば、その部品は読まずに `strings_not_checked`。`.xlsb` は二進の部品を読まず、`strings_not_checked`（シートの状態も見ない）。
- 指示らしい文言は、値を NFKC にして小文字にしてから、部分一致で探す。一覧（実装者が調整してよい）:

```python
INSTRUCTION_PHRASES = (
    "ignore previous", "ignore all previous", "ignore the above", "disregard previous",
    "system prompt", "you are now", "new instructions", "do not tell the user",
    "前の指示を無視", "以前の指示を無視", "上記の指示を無視", "これまでの指示を無視",
    "システムプロンプト", "あなたは今から",
)
INVISIBLE_CODEPOINTS = (
    set(range(0x200B, 0x2010)) | {0x2060, 0xFEFF, 0x061C}
    | set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
    | set(range(0xE0000, 0xE0080))
)
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: すべて PASS。

- [ ] **Step 5: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py
git commit -m "feat: report macros, external links, hidden sheets and suspicious text"
```

---

<a name="task-5"></a>

### Task 5: 検査の Seatbelt と、検査の起動

**Files:**
- Create: `scripts/check_workbook.sb`、`hooks/intake_common.py`、`tests/test_sandbox_profile.py`

**Interfaces:**
- Consumes: Task 3 の `main` の終了コード（0・1・2）
- Produces（`hooks/intake_common.py`）:
  - `PLUGIN_ROOT: str`（このファイルの `realpath` の 2 つ上）
  - `CHECK_TIMEOUT_SECONDS = 20`
  - `run_checker(real_path: str, timeout: float = CHECK_TIMEOUT_SECONDS) -> str`: `"pass"`・`"fail"`・`"error"`・`"timeout"`・`"sandbox_missing"` のどれか

- [ ] **Step 1: 失敗するテストを書く**

すべて macOS だけ。`sandbox-exec -n no-network /usr/bin/true` が失敗する環境では、`WORKBOOK_INTAKE_REQUIRE_SANDBOX=1` なら失敗、なければ skip（理由: Claude の Bash では入れ子にできない）。プロファイルを直接試すテストは、`SELF` に一時的なスクリプトを渡して、そのスクリプトに操作をさせる。

```python
def test_checker_passes_in_sandbox(self):        # run_checker(最小のブック) == "pass"
def test_checker_fail_maps_to_fail(self):        # DOCTYPE のブック → "fail"
def test_timeout_maps_to_timeout(self):          # run_checker(path, timeout=0.001) == "timeout"
def test_profile_denies_write(self):             # 一時ディレクトリへの open(..., "w") が PermissionError
def test_profile_denies_network(self):           # socket.create_connection(("127.0.0.1", 9)) が PermissionError
def test_profile_denies_reading_other_files(self): # TARGET 以外の一時ファイルの読み込みが PermissionError
def test_profile_denies_exec(self):              # subprocess.run(["/bin/echo"]) が PermissionError
def test_extensions_and_size_match_checker(self): # intake_common の SUPPORTED_EXTENSIONS・MAX_FILE_BYTES が check_workbook と同じ
```

- [ ] **Step 2: テストが失敗するか skip されることを確かめる**

Run（Claude の Bash）: `"$PY" -B -m unittest tests.test_sandbox_profile -v`
Expected: `test_extensions_and_size_match_checker` が import で失敗し、ほかは skip。

- [ ] **Step 3: プロファイルと `run_checker` を書く**

- `check_workbook.sb`: dotfiles の `claude/hooks/check-vault-note.sb` と同じ形。値は `PYTHON_HOME`・`SELF`（`check_workbook.py`）・`TARGET`（検査するファイル）。`(allow default)` の上で、`network*`・`file-write*`（`/dev/null` を除く）・`process-exec*`（`PYTHON_HOME` の下を除く）・`process-fork`・`mach-lookup`・`appleevent-send`・`signal`（同じ sandbox を除く）を拒否。`file-read-data` は既定で拒否し、`/`（literal）・`/System`・`/usr/lib`・`/usr/share`・`/private/var/db/timezone`・`PYTHON_HOME`・`/dev/urandom`・`/dev/null`・`SELF`・`TARGET` だけを許す。
- `intake_common.py` に `SUPPORTED_EXTENSIONS`・`MAX_FILE_BYTES` を、検査と同じ値で置く（検査は Seatbelt の中で自分しか読めないので、共有せずに 2 か所に書き、テストで一致を守る）。
- `run_checker`: Python の場所は、フックを動かしている python3 から決める。`python_home = realpath(sys.base_prefix)`、`python_exe = realpath(join(sys.base_prefix, "bin", "python3"))`。コマンドは `/usr/bin/sandbox-exec -f <sb> -D PYTHON_HOME=… -D SELF=… -D TARGET=<real_path> <python_exe> -I -B <SELF> <real_path>`。`stdin`・`stdout`・`stderr` は `DEVNULL`、`env={}`、`timeout` 付き。終了コード 0 → `pass`、1 → `fail`、ほか → `error`。`TimeoutExpired` → `timeout`、`/usr/bin/sandbox-exec` がない → `sandbox_missing`。

- [ ] **Step 4: 人が通常のターミナルでテストを動かす**

Run: `cd <リポジトリ> && WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest tests.test_sandbox_profile -v`
Expected: すべて PASS（skip なし）。Claude の Bash では `test_extensions_and_size_match_checker` だけ PASS で、ほかは skip。

- [ ] **Step 5: コミットする**

```bash
git add scripts/check_workbook.sb hooks/intake_common.py tests/test_sandbox_profile.py
git commit -m "feat: run the checker under a no-network, no-write Seatbelt profile"
```

---

<a name="task-6"></a>

### Task 6: 入力の確認の記録

**Files:**
- Modify: `hooks/intake_common.py`
- Create: `hooks/record_consent.py`、`hooks/record-consent.sh`、`tests/test_record_consent.py`

**Interfaces:**
- Consumes: research の 9・10・A（答えの場所）と 6（環境変数）
- Produces（`hooks/intake_common.py`）:
  - `intake_dir() -> str`: 展開したパス（`realpath` ではない）。research の 6 で環境変数が使えると分かれば `WORKBOOK_INTAKE_DIR` を読み、なければ `~/workbook-intake`。
  - `resolve_in_intake(path: object) -> tuple[str | None, str]`: 合格なら（`realpath`、`"ok"`）、不合格なら（`None`、理由）。理由の語彙と判定の順: `bad_input`（文字列でない）→ `path_not_absolute` → `intake_dir_invalid`（ない、ディレクトリでない、シンボリックリンク）→ `outside_intake`（`realpath` が受け取り用フォルダの `realpath` の真下でない。フォルダ自身も外とみなす）→ `not_regular_file` → `unsupported_extension`（小文字にして比べる）→ `file_too_large`（`MAX_FILE_BYTES` を超える）
  - `file_key(real_path: str) -> str`: `unicodedata.normalize("NFC", real_path)`
  - `file_sha256(real_path: str) -> str`
  - 固定の文: `CONSENT_HEADER`・`CONSENT_QUESTION_PREFIX`・`CONFIRM_LABEL`・`CONFIRM_DESCRIPTION`・`CANCEL_LABEL`・`CANCEL_DESCRIPTION`（下の Step 3）
  - `consent_question(path: str) -> str`: `CONSENT_QUESTION_PREFIX + path`
  - `expected_questions(path: str) -> list[dict]`: AskUserQuestion の `questions` として期待する値
  - `record_consent(session_id: str, key: str, sha256: str) -> bool`、`has_consent(session_id: str, key: str, sha256: str) -> bool`: 記録は `${CLAUDE_PLUGIN_DATA}/consents/<session_id の SHA-256>.jsonl` に 1 行 1 件（`{"path": key, "sha256": …}`）。ディレクトリは 0700。`CLAUDE_PLUGIN_DATA` がなければ、記録しない・承認なしとする。壊れた行は読み飛ばす。
- Produces（`hooks/record_consent.py`）: `selected_answer(hook_input: dict, question: str) -> str | None`、`main() -> int`（常に 0、何も出力しない）

- [ ] **Step 1: 失敗するテストを書く**

`HOME` と `CLAUDE_PLUGIN_DATA` を一時ディレクトリにして、`hooks/record-consent.sh` に JSON を渡して動かし、記録の有無を `has_consent` で見る。

```python
def test_records_confirmed_answer(self):             # 固定の文・選択肢そのまま、答え CONFIRM_LABEL → 記録される
def test_cancel_not_recorded(self):                  # 答え CANCEL_LABEL → 記録されない
def test_altered_question_not_recorded(self):        # 固定の文の 1 文字違い → 記録されない
def test_altered_options_not_recorded(self):         # 説明の書き換え・選択肢の追加・multiSelect true・質問 2 つ → どれも記録されない（レビューの重点 4）
def test_path_outside_intake_not_recorded(self):     # 受け取り用フォルダの外 → 記録されない
def test_relative_path_not_recorded(self):
def test_other_tool_not_recorded(self):              # tool_name が AskUserQuestion でない
def test_malformed_input_not_recorded(self):         # JSON でない・項目の欠け → 記録されず、終了コード 0、出力なし
def test_missing_plugin_data_not_recorded(self):     # CLAUDE_PLUGIN_DATA なし
def test_nfd_and_nfc_paths_are_same_file(self):      # NFD の名前のファイルを NFC のパスで承認 → NFD のパスの file_key で承認あり（レビューの重点 1）
def test_consent_is_per_session(self):               # 別の session_id では承認なし
def test_consent_is_per_content(self):               # 記録の後に中身を変える → 承認なし
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_record_consent -v`
Expected: 入口のスクリプトがなく失敗する。

- [ ] **Step 3: 固定の文と、記録を書く**

固定の文（スキルと同じ値。[Task 8](#task-8) のテストで一致を守る）:

```python
CONSENT_HEADER = "Input check"
CONSENT_QUESTION_PREFIX = (
    "workbook-intake: Before analysis, confirm that this file contains no personal or "
    "confidential information. You use the results at your own risk.\n"
    "解析の前に、このファイルに個人情報や機密情報が含まれていないことを確認してください。"
    "結果は自己責任で使ってください。\n"
    "File / ファイル: "
)
CONFIRM_LABEL = "Confirmed / 確認した"
CONFIRM_DESCRIPTION = (
    "I confirmed the input contains no personal or confidential information. "
    "/ 入力に個人情報や機密情報が含まれていないことを確認した。"
)
CANCEL_LABEL = "Cancel / やめる"
CANCEL_DESCRIPTION = "Do not analyze this file. / このファイルは解析しない。"
```

`expected_questions(path)` は、`question`・`header`・`options`（上の 2 つ、`label` と `description` だけ）・`multiSelect: false` の 1 問。`record_consent.py` の `main` は、`tool_name` が `AskUserQuestion` で、`questions` がちょうど 1 問で `CONSENT_QUESTION_PREFIX` で始まり、残りのパスに改行がなく、`questions == expected_questions(path)` で、`selected_answer` が `CONFIRM_LABEL` で、`resolve_in_intake` が `ok` のときだけ記録する。`selected_answer` は research の 9 で分かった項目から読む（モデルが入力に書いた値で偽れないことは、research の A で確かめ済みであること）。例外はすべて捕まえ、記録せずに 0 を返す。`record-consent.sh` は `/usr/bin/xcode-select -p` の先の python3 を `-I -B` で起動するだけにし、なければ何もせずに 0 で終える。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_record_consent -v && shellcheck hooks/record-consent.sh`
Expected: すべて PASS、shellcheck の指摘なし。

- [ ] **Step 5: コミットする**

```bash
git add hooks/intake_common.py hooks/record_consent.py hooks/record-consent.sh tests/test_record_consent.py
git commit -m "feat: record per-file input consent from AskUserQuestion"
```

---

<a name="task-7"></a>

### Task 7: xlide の呼び出しの判定

**Files:**
- Create: `hooks/guard_xlide.py`、`hooks/guard-xlide.sh`、`hooks/hooks.json`、`hooks/allowed-tools.txt`、`tests/test_guard_xlide.py`

**Interfaces:**
- Consumes: Task 5 の `run_checker`、Task 6 の `resolve_in_intake`・`file_key`・`file_sha256`・`has_consent`、research の 1（`agent_type`）とツールの一覧
- Produces:
  - `hooks/allowed-tools.txt`: 1 行目は `# reviewed-for: xlide-mcp==1.2.4`（どの版のソースで見直したか）。以降は 1 行に `<ツール名> <file|nofile>`（例: `xlide_doctor nofile`）。`file` は `file_path` が必須のツール。`#` で始まる行と空行は読み飛ばす。
  - `TOOL_PREFIX = "mcp__plugin_workbook-intake_xlide__"`、`ANALYST_AGENT_TYPE = "workbook-intake:excel-analyst"`（research の 1 の値）
  - `load_allowlist() -> dict[str, str]`（ツール名 → `"file"` か `"nofile"`）
  - `decide(hook_input: dict) -> tuple[str, str]`: （`"allow"` か `"deny"`、理由の語彙）
  - `main() -> int`: 常に 0。PreToolUse の JSON を 1 つ出す。

- [ ] **Step 1: 失敗するテストを書く**

`HOME`・`CLAUDE_PLUGIN_DATA` を一時ディレクトリにし、承認は Task 6 の `record_consent` で直接書く。`sandbox-exec` を通す判定のテストは Task 5 と同じ条件で skip。拒否の理由は、出力の `permissionDecisionReason` に語彙が入ることで見る。

```python
def test_allows_consented_checked_file(self):              # allow
def test_denies_non_plugin_xlide(self):                    # "mcp__xlide__xlide_doctor" → not_plugin_server
def test_denies_tool_not_in_allowlist(self):               # 書き込み用のツール → tool_not_allowed
def test_denies_main_conversation(self):                   # agent_type なし・別の値 → wrong_caller
def test_nofile_tool_allowed_for_analyst(self):            # xlide_doctor → allow
def test_extra_path_argument_denied(self):                 # output_path・directory を足す → unexpected_path_argument（レビューの重点 5）
def test_missing_file_path_denied(self):                   # file 種のツールで file_path なし → missing_file_path
def test_non_string_file_path_denied(self):                # 配列・数値 → bad_input
def test_relative_path_denied(self):                       # path_not_absolute
def test_outside_intake_denied(self):                      # outside_intake
def test_symlink_to_outside_denied(self):                  # フォルダの中のシンボリックリンクが外を指す → outside_intake
def test_intake_dir_symlink_denied(self):                  # 受け取り用フォルダ自身がシンボリックリンク → intake_dir_invalid
def test_directory_denied(self):                           # not_regular_file
def test_uppercase_extension_allowed(self):                # "BOOK.XLSX" → allow（レビューの重点 2）
def test_oversized_file_denied_before_hashing(self):       # file_sha256 を呼ばれたら失敗する mock → file_too_large（レビューの重点 3）
def test_no_consent_denied(self):                          # no_consent
def test_changed_content_after_consent_denied(self):       # no_consent
def test_consent_matches_across_unicode_normalization(self): # NFC で承認、NFD のパスで呼ぶ → allow（レビューの重点 1）
def test_check_failure_denied(self):                       # zip bomb → check_failed
def test_check_timeout_denied(self):                       # CHECK_TIMEOUT_SECONDS を 0.001 に → check_timeout
def test_checker_error_denied(self):                       # run_checker が "error"・"sandbox_missing" を返す mock → check_error・sandbox_missing
def test_malformed_input_denied(self):                     # JSON でない・空 → bad_input、終了コード 0
def test_internal_error_denied(self):                      # decide が例外を投げる mock → internal_error
def test_wrapper_denies_without_python(self):              # DEVELOPER_DIR を存在しないディレクトリにする → python_missing
def test_reason_has_no_file_derived_strings(self):         # パスとファイル名に目印の文字列を入れ、出力に含まれないこと
def test_hooks_json(self):                                 # matcher・timeout 30・onFailure "block"・command の形
def test_allowlist_reviewed_for_pinned_version(self):      # allowed-tools.txt の reviewed-for の値 == .mcp.json の "--from" の次の値（版を上げて許可リストを見直さないと失敗する）
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide -v`
Expected: 入口のスクリプトがなく失敗する。

- [ ] **Step 3: 判定を書く**

`decide` の順（設計の[フック](design.md#hook)の 1〜5 に、補足を足したもの）:
1. `tool_name` が `TOOL_PREFIX` で始まらない → `not_plugin_server`
2. 接頭辞を除いた名前が `load_allowlist()` にない → `tool_not_allowed`
3. `agent_type` が `ANALYST_AGENT_TYPE` でない → `wrong_caller`
4. `tool_input` が辞書でない → `bad_input`。`file_path` 以外のキーで、名前に `path`・`file`・`dir`・`folder`・`root` を含む（大文字小文字を問わない）ものがある → `unexpected_path_argument`。`file` 種で `file_path` がない → `missing_file_path`。
5. `file_path` があれば: `resolve_in_intake`（不合格ならその理由）→ `CLAUDE_PLUGIN_DATA` がない → `consent_store_unavailable` → `has_consent(session_id, file_key, file_sha256)` でない → `no_consent` → `run_checker`（`fail` → `check_failed`、`error` → `check_error`、`timeout` → `check_timeout`、`sandbox_missing` → `sandbox_missing`）
6. すべて通れば `allow`（理由 `ok`）

出力は `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": …, "permissionDecisionReason": "workbook-intake: <理由>. See the README (Troubleshooting)."}}`。`main` は例外をすべて捕まえて `internal_error` で拒否する。

`guard-xlide.sh` は、`/usr/bin/xcode-select -p` の先の python3 がなければ `python_missing` の拒否の JSON を出す。あれば `guard_xlide.py` を `-I -B` で動かし、終了コードが 0 でないか出力が空なら、`internal_error` の拒否の JSON を出す。

`hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "mcp__.*__xlide_.*", "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/guard-xlide.sh\"", "timeout": 30, "onFailure": "block"}]}],
    "PostToolUse": [{"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/record-consent.sh\"", "timeout": 30}]}]
  }
}
```

`allowed-tools.txt` は、research の許可リストの案を写す。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide -v && shellcheck hooks/guard-xlide.sh`
Expected: `sandbox-exec` を使わないテストは PASS、使うものは skip。shellcheck の指摘なし。

- [ ] **Step 5: 人が通常のターミナルで全体を動かす**

Run: `cd <リポジトリ> && WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（skip なし）。

- [ ] **Step 6: コミットする**

```bash
git add hooks/guard_xlide.py hooks/guard-xlide.sh hooks/hooks.json hooks/allowed-tools.txt tests/test_guard_xlide.py
git commit -m "feat: guard xlide calls with allowlist, caller, consent and checker"
```

---

<a name="task-8"></a>

### Task 8: 前提の確認、サブエージェント、スキル

**Files:**
- Create: `scripts/doctor.sh`、`tests/test_doctor.py`、`agents/excel-analyst.md`、`skills/analyze/SKILL.md`、`tests/test_skill_and_agent.py`

**Interfaces:**
- Consumes: Task 6 の固定の文、Task 7 の `allowed-tools.txt`・`TOOL_PREFIX`、research の C（スキルからスクリプトの場所を指す方法）
- Produces: `doctor.sh` の出力は 1 行に `ok <項目>` か `missing <項目>`。項目は `macos`・`uvx`・`python3`・`sandbox_exec`・`intake_dir`。足りないものがあれば最後に `See README: Requirements` を出して終了コード 1、なければ 0。受け取り用フォルダがシンボリックリンクなら `missing intake_dir`。

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_doctor.py（HOME を一時ディレクトリ、PATH に uvx の偽物を置いたディレクトリを入れる）
def test_all_present(self):            # 終了コード 0、"missing" なし
def test_intake_dir_missing(self):     # "missing intake_dir"、終了コード 1
def test_intake_dir_symlink(self):     # "missing intake_dir"
def test_uvx_missing(self):            # PATH から外す → "missing uvx"

# tests/test_skill_and_agent.py
def test_agent_tools_match_allowlist(self):   # frontmatter の tools の集合 == {TOOL_PREFIX + 名前 for 名前 in allowed-tools.txt}
def test_agent_has_no_unsupported_fields(self): # hooks・mcpServers・permissionMode を書かない
def test_skill_contains_consent_copy(self):   # CONSENT_HEADER・CONSENT_QUESTION_PREFIX・CONFIRM_LABEL・CONFIRM_DESCRIPTION・CANCEL_LABEL・CANCEL_DESCRIPTION がそのまま入る
def test_skill_description_makes_no_safety_claim(self): # description に "safe"・"secure"・"安全" がない
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_doctor tests.test_skill_and_agent -v`
Expected: ファイルがなく失敗する。

- [ ] **Step 3: `doctor.sh`・エージェント・スキルを書く**

- `doctor.sh`: 設計の[前提の確認](design.md#doctor)の項目を見る（`uname -s` が `Darwin`、`command -v uvx`、`$(xcode-select -p)/usr/bin/python3`、`/usr/bin/sandbox-exec`、受け取り用フォルダがディレクトリでシンボリックリンクでない）。受け取り用フォルダは Task 6 の `intake_dir` と同じ決め方にする。
- `agents/excel-analyst.md`: frontmatter は `name: excel-analyst`、`description`、`tools`（許可リストの完全な名前をカンマ区切り）。本文は設計の[サブエージェント](design.md#subagent)の 5 点を、英語で、自分の言葉で書く。
- `skills/analyze/SKILL.md`: frontmatter は `name: analyze` と `description`（Excel のブックの数式・構造・VBA の解析を頼まれたときに起動する書き方。安全と読める語を使わない）。本文は設計の[流れ](design.md#flow)の 0〜3 と[スキル](design.md#skill)のとおり。入力の確認は、AskUserQuestion に Task 6 の固定の文と選択肢をそのまま渡す（`File / ファイル: ` の後に、ファイルの絶対パス）ように書く。検査の実行は `"$(xcode-select -p)/usr/bin/python3" -I -B <プラグインの場所>/scripts/check_workbook.py <絶対パス>` の形にし、プラグインの場所は research の C の方法で書く。xlide のツール（`TOOL_PREFIX` で始まるもの）が見えなければ、README の Troubleshooting を示して止まる。ファイルの中身を Read や Bash（`unzip` など）で直接読まないことも書く。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_doctor tests.test_skill_and_agent -v && shellcheck scripts/doctor.sh && claude plugin validate . --strict`
Expected: すべて PASS、指摘なし、validate は 0。

- [ ] **Step 5: コミットする**

```bash
git add scripts/doctor.sh tests/test_doctor.py agents skills tests/test_skill_and_agent.py
git commit -m "feat: add excel-analyst agent, analyze skill and doctor script"
```

---

<a name="task-9"></a>

### Task 9: CI と、依存の新しい版の検知

xlide と固定した依存の新しい版と脆弱性は、Dependabot で検知する（ユーザーの指定）。Dependabot は `.mcp.json` の uvx の引数を読めないので、同じ固定を `deps/requirements.txt` に写し、テストで一致を守る。Dependabot が写しの版を上げる PR を出すと、`.mcp.json` と食い違ってテストが落ちる。その PR を、版を上げる作業（[Task 10](#task-10) の runbook）のきっかけにする。

**Files:**
- Create: `.github/workflows/ci.yml`、`.github/dependabot.yml`、`deps/requirements.txt`
- Modify: `tests/test_manifests.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_dependabot_mirror_matches_mcp_json(self):
    # deps/requirements.txt の "name==version" の行の集合 == XLIDE_ARGS の "--from" と "--with" の次の値の集合
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_manifests -v`
Expected: `deps/requirements.txt` がなく失敗する。

- [ ] **Step 3: 写しと Dependabot の設定を書く**

- 先に、GitHub のドキュメントで、Dependabot の `pip` が読むファイルの名前と `directory` の決まりを確かめる。
- `deps/requirements.txt`: 先頭のコメントに、英語で「Dependabot のための `.mcp.json` の固定の写しで、インストールには使わない」と書き、5 つの固定を `name==version` で並べる。
- `.github/dependabot.yml`: `pip`（`directory: "/deps"`、週 1 回、5 つを 1 つの PR にまとめる `groups`）と `github-actions`（`directory: "/"`、週 1 回）。
- 脆弱性の通知（Dependabot alerts）は、リポジトリの設定で人が有効にする（[Task 12](#task-12) の公開のときの人の作業に入れる）。

- [ ] **Step 4: ワークフローを書く**

- 起動: `pull_request` と `push`（`main`）。`permissions: contents: read`。
- 使う Action は、完全なコミットの SHA で固定する（タグの SHA は `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` で調べ、コメントにタグ名を書く）。
- `linux`（`ubuntu-latest`）: `python3 -B -m unittest discover -s tests -t . -v`（macOS だけのテストは skip される）と、`shellcheck hooks/*.sh scripts/*.sh`。
- `macos`（`macos-latest`）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`。

- [ ] **Step 5: 手元で同じコマンドが通ることを確かめる**

Run: `shellcheck hooks/*.sh scripts/*.sh && "$PY" -B -m unittest discover -s tests -t . -v`
Expected: 指摘なし。PASS と skip だけ。CI での実行は、PR を作った後に `gh pr checks` で確かめる（[Task 12](#task-12)）。

- [ ] **Step 6: コミットする**

```bash
git add .github deps tests/test_manifests.py
git commit -m "ci: add CI workflows and Dependabot for pinned xlide dependencies"
```

---

<a name="task-10"></a>

### Task 10: README と保守の runbook

**Files:**
- Modify: `README.md`（Task 1 の最小の README に書き足す）
- Create: `README.ja.md`、`docs/runbooks/maintenance.md`、`tests/test_readme.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_states_no_affiliation(self):        # README.md が "not affiliated with xlide-mcp or NVIDIA SkillSpector" を、README.ja.md が「xlide-mcp とも NVIDIA SkillSpector とも関係のない」を含む
def test_states_own_risk(self):              # README.md が "at your own risk" を、README.ja.md が「自己責任」を含む
def test_has_required_sections(self):        # README.md に見出し "Requirements"・"Install"・"Configuration"・"Usage"・"Checks"・"Limitations"・"Troubleshooting"・"Maintenance"・"License" がある
def test_links_between_languages(self):      # README.md が "README.ja.md" に、README.ja.md が "README.md" にリンクする
def test_japanese_has_same_sections(self):   # "## " の見出しの数が、両方で同じ
def test_maintenance_links_runbook(self):    # 両方が "docs/runbooks/maintenance.md" にリンクする
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_readme -v`
Expected: `README.ja.md` がなく、見出しも足りずに失敗する。

- [ ] **Step 3: README を書く**

設計の [README](design.md#readme) と[更新と保守](design.md#maintenance)の項目を、`README.md` に英語で書く。冒頭（タイトルの直後）に、日本語版へのリンク（`[日本語](README.ja.md)`）を置く。`README.ja.md` は同じ構成の日本語版にし、冒頭に英語版へのリンク（`[English](README.md)`）を置く。日本語の見出しには、ユーザーの Markdown の規則どおり、直前に `<a name="…"></a>` を置く。どちらにも次を書く: research の D の結果（`engines` で宣言できなければ、Claude Code 2.1.295 以上が要ること）。Troubleshooting に、フックの拒否の理由の語彙（Task 7）と、`doctor.sh` の項目（Task 8）の意味。Maintenance には、使う人に向けた方針（設計の[更新と保守](design.md#maintenance)）だけを書き、作者の手順は runbook へのリンクにする。Checks に、検査の不合格と警告の語彙（Task 3・4）の意味。

`docs/runbooks/maintenance.md`（日本語。ユーザーの指定）は、作者が保守するときに、Claude が読んで作者を案内するための文書にする。冒頭に、Claude への指示を書く: 「このファイルを読んだら、どのきっかけかを人に確かめ、該当する節の手順をチェックリストにして 1 つずつ進める。許可リストに足すかどうかなど、守りに関わる判断は人に求める」。次の節を置く。
- きっかけと気づき方: 下の表。
- 版を上げる手順: `.mcp.json`・`deps/requirements.txt`・`dev/probe` の `.mcp.json` の版を上げる → 前の調査と同じ方法で SkillSpector にかける（業務の情報は書かない）→ 許可リストのすべてのツールについて、[Task 1](#task-1) の Step 2 の 3 点を新しい版のソースで確かめ直し、`reviewed-for` を新しい版にする（新しいツールは許可リストに足すまでフックが止めるが、既にあるツールの引数や動きの変化は名前では止まらないので、全ツールを見る）→ 全体のテスト（通常のターミナル、`WORKBOOK_INTAKE_REQUIRE_SANDBOX=1`）→ 実機の確認（設計の完了条件）→ `plugin.json` の版とタグ → 自分の settings の SHA の固定を新しくする。
- Claude Code の前提を確かめ直す手順: `dev/probe` を使い、[Task 1](#task-1) の表の項目を確かめ直す。表には、Task 1 で確かめた値（`agent_type` の値など）を書いておき、それと比べる。違えば使うのをやめ、設計を見直す。
- 保守の作業の記録: 作業ごとに `docs/work/<ID>_<slug>/` を作る（ユーザーの文書の規則）。

| きっかけ | 気づき方 | 対応 |
| --- | --- | --- |
| xlide と固定した依存の新しい版・脆弱性 | Dependabot の PR と alerts（[Task 9](#task-9)） | 版を上げる手順 |
| Claude Code の更新（フック・プラグイン・MCP・権限・AskUserQuestion に関わる変更） | Claude Code の changelog。自動では検知しない | 前提を確かめ直す手順 |
| macOS・Command Line Tools の更新（python3 の版が変わるなど） | CI の macOS のジョブの失敗、`doctor.sh` | 全体のテストを通常のターミナルで。`PYTHON_HOME` と Seatbelt を確かめる |
| uv の更新 | 自動では検知しない | `uvx --no-config` の動きを確かめる |
| GitHub Actions の新しい版 | Dependabot の PR | SHA と変更を確かめて取り込む |
| ほかの人からの Issue・PR | GitHub の通知 | 対応は約束しない（README の方針） |

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_readme tests.test_repository -v`
Expected: PASS。

- [ ] **Step 5: コミットする**

```bash
git add README.md README.ja.md docs/runbooks/maintenance.md tests/test_readme.py
git commit -m "docs: add README and maintenance runbook"
```

---

<a name="task-11"></a>

### Task 11: 実機での確認

設計の[完了条件](design.md#done)を、入れたプラグインで確かめる。人の操作が要る。

**Files:**
- Create: `docs/work/20261124_workbook-intake/test-report.md`

- [ ] **Step 1: 確かめるためのファイルを用意する**

人に、個人情報も機密情報もないブックを 1 つ、`~/workbook-intake` に置いてもらう。zip bomb のファイルは `tests/workbook_factory.py` の関数で、`tmp/` に作ってから受け取り用フォルダに写してもらう。

- [ ] **Step 2: 人がプラグインを入れて、完了条件を 1 つずつ確かめる**

入れ方は README のとおり（ローカルのリポジトリをマーケットプレイスとして足す）。設計の完了条件の 8 項目を、表にして test-report に書き、項目ごとに、頼んだこと・期待・結果（拒否の理由の語彙など）を記録する。

- [ ] **Step 3: 全体のテストの結果を記録する**

Run（人、通常のターミナル）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v && shellcheck hooks/*.sh scripts/*.sh`
Expected: すべて PASS、指摘なし。結果を test-report に書く。

- [ ] **Step 4: コミットする**

```bash
git add docs/work/20261124_workbook-intake/test-report.md
git commit -m "docs: record manual verification of workbook-intake"
```

---

<a name="task-12"></a>

### Task 12: レビューと PR の準備

- [ ] **Step 1: `/review` を実行し、指摘への対応を決める。直したら、全体のテストを実行し直す。**
- [ ] **Step 2: `/security-review` を実行する（外部からの入力と権限の境界に触れるため）。**
- [ ] **Step 3: Codex のレビューを行う（必須。ユーザーの指定）。** 人が通常のターミナルで `codex review` と、challenge（変更前と比べた後退と、壊れる入力を挙げてもらう。プロンプトは Claude が書く）を実行する。結果は、CLAUDE.md の Skill routing の手順で読み、test-report に記録してから採否を整理する。直したら、全体のテストを実行し直す。上限は 5 回。
- [ ] **Step 4: 作業文書を締める。** design.md・plan.md・research・test-report の `status` を `done` にしてコミットする。
- [ ] **Step 5: `/crit-review` でブランチの差分を開き、`approved: true` を待つ。** その後に `cc-safe-push` と `cc-safe-pr create` を使う（許可リストにないリポジトリなら、人にコマンドを示す）。PR を作ったら `gh pr checks` で CI の結果を確かめる。
- [ ] **Step 6: 公開のときの人の作業を伝える。** GitHub の説明文とトピック（`claude-code`・`claude-code-plugin` など）の設定、Dependabot alerts を有効にすること（リポジトリの Settings の Code security）、dotfiles の settings.json の作業（設計の[人の作業](design.md#human-steps)。dotfiles で別に行う）。
