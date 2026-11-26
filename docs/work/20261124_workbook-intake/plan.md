---
status: in-progress
created: 2026-11-25
---

# workbook-intake 実装計画

> [!IMPORTANT]
> エージェント向け: この計画は、superpowers:subagent-driven-development（推奨）か superpowers:executing-plans で、Task ごとに実行する。手順はチェックボックス（`- [ ]`）で進み具合を記録する。Task 1 と Task 11 は人の操作が要るので、メインの会話で行う。

**Goal:** 受け取り用フォルダの Excel を、検査と入力の確認を通したものだけ xlide-mcp で解析させる Claude Code プラグインを作る。

**Architecture:** プラグイン 1 つに、xlide の MCP サーバーの定義、解析用のサブエージェント、手順のスキル、2 つのフック（xlide の呼び出しを判定する PreToolUse と、入力の確認・警告の確認の承認と検査の結果を記録する PostToolUse）、検査のスクリプトとその Seatbelt を入れる。フックの判定は Python で書き、bash の入口から Command Line Tools の python3 で動かす。検査は 2 つのフックの中で `sandbox-exec` の下で動かし、終了コードと、出力のうち固定の語彙に一致する値だけを使う。受け取り用フォルダは Claude Code の sandbox から読めなくし（推奨設定）、`doctor.sh` が設定漏れで止まる。

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
- 版の固定（設計のとおり）: `xlide-mcp==1.2.4`、`pyopenvba==6.6.0`、`pyofficeeditor==0.4.1`、`pyvbaanalysis==3.0.3`、`mcp==2.3.0`。xlide の Python は 3.15（`uvx --python 3.15`。2026-11-26 に足した。[Task 23](#task-23)）。
- 名前: プラグインとマーケットプレイスは `workbook-intake`、MCP サーバーは `xlide`、ツール名の接頭辞は `mcp__plugin_workbook-intake_xlide__`、サブエージェントは `excel-analyst`（呼び出し元の名前は `workbook-intake:excel-analyst`）、スキルは `analyze`。
- 受け取り用フォルダの既定は `~/workbook-intake`。
- 時間: フックの timeout は 30 秒、検査の上限は 20 秒（フックの中で決める）。
- 検査の閾値: ファイル 100 MB、部品 10,000、展開の合計 256 MB（2026-11-25 に 1 GB から下げた。[Task 17](#task-17)）、1 部品の圧縮率 100 倍。
- 検査とフックの出力（標準出力、拒否の理由、会話に返す文、JSON）には、固定の語彙・件数・真偽だけを入れる。ファイル由来の文字列（シート名、セルの文字列、部品の名前、ファイル名、パス）を入れない。フックは、検査の出力のうち、固定の語彙に一致する値だけを使う（知らない値があれば、検査できないとみなす）。
- 検査は、2 つのフックが sandbox の外から Seatbelt の中で動かす。スキル（Claude Code の Bash）からは動かさない。推奨設定では、Bash から受け取り用フォルダを読めない（設計の[直接の読み込みを止める](design.md#direct-read)）。
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
- 文字列の検査は、設計が挙げた部品に限らず、`customXml/` を除くすべての XML の部品で行う。部品の名前は関係（`.rels`）で変えられるので、決まった名前だけを見ると、名前を変えるだけで検査を外せるため。シートの状態は、`_rels/.rels` の `officeDocument` の先の部品から読む。（2026-11-25: この行の決め方は、xlide の読み方と食い違うと分かったので、[Task 14](#task-14) で、部品を中身で選び、シートの状態をすべての部品で数える形に変える。）
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
| `docs/work/20261124_workbook-intake/research-xlide-parsing.md` | xlide 1.2.4 と pyofficeeditor 0.4.1 の、zip・XML・関係・パスの読み方（1 回目の `/review` の後に調べた） | 13〜15 |
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
  - 受け取り用フォルダを sandbox から読めなくする settings と、`dangerouslyDisableSandbox` を使えなくする settings の書き方（[Task 10](#task-10) の README）。
  - PostToolUse のフックが会話に文を返す JSON の形（[Task 6](#task-6) の `main`）。

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
- `hooks/probe.sh`: 標準入力の JSON と、`CLAUDE_PLUGIN_ROOT`・`CLAUDE_PLUGIN_DATA`・`WORKBOOK_INTAKE_DIR` の値と、`/usr/bin/sandbox-exec -n no-network /usr/bin/true` の終了コードを、`${CLAUDE_PLUGIN_DATA}/probe.log` に追記する。PreToolUse では、ツール名で次のように振る舞う: `xlide_doctor` → allow を返す。一覧から選んだ `file_path` を取る読み取り用のツール 1 つ（以下 T_read）→ allow。別のツール 1 つ（T_deny）→ deny。もう 1 つ（T_slow）→ 10 秒待つ（timeout 5 を超える）。もう 1 つ（T_fail）→ 何も出さずに終了コード 1。PostToolUse では、`hookSpecificOutput.additionalContext` に目印の文（`probe-additional-context`）を返す（確かめること 15）。
- `agents/excel-analyst.md`: `tools` に、上の 5 つのツールの完全な名前を書く。
- `skills/probe/SKILL.md`: 本文に `${CLAUDE_PLUGIN_ROOT}` を書き、Bash で `echo` させる（確かめること C）。

- [ ] **Step 5: probe を検証する**

Run: `claude plugin validate dev/probe/workbook-intake --strict`
Expected: 終了コード 0。

- [ ] **Step 5b: 受け取り用フォルダを sandbox から読めなくする settings の書き方を確かめる**

公式ドキュメント（settings と sandboxing）で、次を確かめて research に書く（確かめること 12・14）: 受け取り用フォルダの読み込みを拒否する書き方（`sandbox.filesystem` の読み込みの拒否か、`permissions.deny` の `Read(...)` か）、Read の deny の規則が sandbox の Bash にも効くか、`dangerouslyDisableSandbox` を使えなくする書き方（`allowUnsandboxedCommands` など）。書き方が複数あれば、Step 6 で両方を試す。

- [ ] **Step 6: 人が probe のセッションを動かす**

人に、通常のターミナルで次を行うよう頼む。手順は research の付録に、そのまま貼れる形で書いておく。
1. `~/workbook-intake` を作り、個人情報も機密情報もないブックを 1 つ置く。
2. 空の作業用のディレクトリで、`claude plugin marketplace add <リポジトリの絶対パス>/dev/probe/workbook-intake` と `claude plugin install workbook-intake@workbook-intake-probe` を実行し、`claude` を起動する。
3. セッションで、Claude に次を順に頼む: (a) メインの会話から `xlide_doctor` を呼ぶ。(b) excel-analyst に、`xlide_doctor`・T_read（置いたブックの絶対パス）・T_deny・T_slow・T_fail を呼ばせる。(c) AskUserQuestion で質問を 1 つ出させ、人が答える。その直後に、Claude に目印の文（`probe-additional-context`）が見えるかを聞く（確かめること 15）。(d) AskUserQuestion を、`answers` に答えを入れた形で呼ばせる（確かめること A）。(e) probe スキルを起動する。(f) Bash と Write ツールで、`probe.log` のあるディレクトリにファイルを書かせる。
4. その作業用のディレクトリに、同じ uvx のコマンドの xlide を定義した `.mcp.json` を置いて起動し直し、プラグインの xlide のツールが見えるかを確かめる。見えなければ、`.claude/settings.local.json` の `disabledMcpjsonServers` に `xlide` を足して、もう一度確かめる。
5. Step 5b の書き方で、受け取り用フォルダの読み込みの拒否と、`dangerouslyDisableSandbox` を使えなくする設定を `.claude/settings.local.json` に足して起動し直す。Claude に次を順に頼む（確かめること 13・14）: (g) Bash で `ls ~/workbook-intake`、`test -d ~/workbook-intake && echo visible`、`unzip -p <ブックの絶対パス> '[Content_Types].xml'` を実行する。(h) excel-analyst に T_read を呼ばせる。(i) Bash の `ls ~/workbook-intake` を、`dangerouslyDisableSandbox` を付けて実行する。
6. `probe.log` を `tmp/probe/probe.log` に写す（アンインストールで消えるため。ログにはブックのパスが入るので、コミットしない）。

- [ ] **Step 7: 結果を research に書く**

`tmp/probe/probe.log` と、Step 6 のセッションで Claude が返したものを読み、次の表を埋める。設計の項目（1〜15）を先に、足した項目（A〜D）を後に書く。

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
| 12 | 受け取り用フォルダを sandbox から読めなくする settings の書き方。Read の deny の規則が sandbox の Bash にも効くか | 未定 |
| 13 | その設定のもとで、(g) の `ls`・`unzip` が失敗するか。`test -d` は見えるか。(h) で xlide とフックは読めるか | `ls`・`unzip` は失敗する。xlide とフックは読める |
| 14 | `dangerouslyDisableSandbox` を使えなくする書き方と、(i) が止まるか | 未定 |
| 15 | PostToolUse の `additionalContext` がメインの会話に届くか | 届く |
| A | モデルが `answers` を入れて AskUserQuestion を呼んだとき、人への確認が出るか。PostToolUse に何が入るか | 確認が出る。モデルの値で答えを偽れない |
| B | T_slow（時間切れ）と T_fail（終了コード 1）が、`onFailure: "block"` で止まるか | 止まる |
| C | SKILL.md の `${CLAUDE_PLUGIN_ROOT}` が、プラグインの場所に置き換わるか | 置き換わる |
| D | `plugin.json` の `engines` で、Claude Code の最低の版（`onFailure` が使える 2.1.295）を宣言できるか（manifest reference の書式を読み、validate で確かめる） | 未定 |

- [ ] **Step 8: 判定する**

1・3・4・8・9・10・11・13・15・A・B のどれかが想定と違えば、ここで止まり、ユーザーに結果と、設計のどこが成り立たないかを伝える。特に A で答えを偽れる場合は、[入力の確認](design.md#consent)の強制の方法を、13 で Bash から読める場合は、[直接の読み込みを止める](design.md#direct-read)方法を考え直す必要がある。2・5・6・7・12・14・C・D は、結果に合わせて後の Task の書き方を選ぶ（research に、どれを選んだかを書く）。

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
  - `FAILURE_CODES`（不合格の語彙のタプル）: `unsupported_extension`、`file_too_large`、`encrypted`、`not_zip`、`too_many_parts`、`unsafe_part_name`、`uncompressed_too_large`、`compression_ratio_too_high`、`xml_dtd`

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
- Produces: `WARNING_CODES`（警告の語彙のタプル）と `counts`（警告ごとの件数）。`vba_project`、`external_link`、`data_connection`、`external_relationship`、`power_query`、`embedded_object`、`activex`、`hidden_sheet`、`very_hidden_sheet`、`invisible_characters`、`instruction_like_text`、`very_long_string`、`strings_not_checked`
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
- Consumes: Task 3 の `main` の終了コード（0・1・2）と 1 行の JSON、`FAILURE_CODES`・`WARNING_CODES`
- Produces（`hooks/intake_common.py`）:
  - `PLUGIN_ROOT: str`（このファイルの `realpath` の 2 つ上）
  - `CHECK_TIMEOUT_SECONDS = 20`、`FAILURE_CODES`・`WARNING_CODES`（検査と同じ値）
  - `run_checker(real_path: str, timeout: float = CHECK_TIMEOUT_SECONDS) -> dict`: `{"status": "pass" | "fail" | "error" | "timeout" | "sandbox_missing", "failures": [str], "warnings": [str]}`。`failures`・`warnings` は固定の語彙だけ（設計の[検査の Seatbelt](design.md#sandbox-profile)）。

- [ ] **Step 1: 失敗するテストを書く**

すべて macOS だけ。`sandbox-exec -n no-network /usr/bin/true` が失敗する環境では、`WORKBOOK_INTAKE_REQUIRE_SANDBOX=1` なら失敗、なければ skip（理由: Claude の Bash では入れ子にできない）。プロファイルを直接試すテストは、`SELF` に一時的なスクリプトを渡して、そのスクリプトに操作をさせる。

```python
def test_checker_passes_in_sandbox(self):        # run_checker(最小のブック)["status"] == "pass"、warnings == []
def test_checker_fail_maps_to_fail(self):        # DOCTYPE のブック → status "fail"、failures == ["xml_dtd"]
def test_warnings_are_returned(self):            # 非表示のシートのブック → status "pass"、warnings == ["hidden_sheet"]
def test_timeout_maps_to_timeout(self):          # run_checker(path, timeout=0.001)["status"] == "timeout"
def test_profile_denies_write(self):             # 一時ディレクトリへの open(..., "w") が PermissionError
def test_profile_denies_network(self):           # socket.create_connection(("127.0.0.1", 9)) が PermissionError
def test_profile_denies_reading_other_files(self): # TARGET 以外の一時ファイルの読み込みが PermissionError
def test_profile_denies_exec(self):              # subprocess.run(["/bin/echo"]) が PermissionError
# 次の 3 つは sandbox なしで動く（subprocess.run を mock にする・定数を比べる）
def test_unknown_code_is_error(self):            # 出力に語彙にない値 → status "error"、failures・warnings は空
def test_unparsable_output_is_error(self):       # 出力が JSON でない・終了コードと result が食い違う → "error"
def test_constants_match_checker(self):          # SUPPORTED_EXTENSIONS・MAX_FILE_BYTES・FAILURE_CODES・WARNING_CODES が check_workbook と同じ
```

- [ ] **Step 2: テストが失敗するか skip されることを確かめる**

Run（Claude の Bash）: `"$PY" -B -m unittest tests.test_sandbox_profile -v`
Expected: sandbox なしで動く 3 つが import で失敗し、ほかは skip。

- [ ] **Step 3: プロファイルと `run_checker` を書く**

- `check_workbook.sb`: dotfiles の `claude/hooks/check-vault-note.sb` と同じ形。値は `PYTHON_HOME`・`SELF`（`check_workbook.py`）・`TARGET`（検査するファイル）。`(allow default)` の上で、`network*`・`file-write*`（`/dev/null` を除く）・`process-exec*`（`PYTHON_HOME` の下を除く）・`process-fork`・`mach-lookup`・`appleevent-send`・`signal`（同じ sandbox を除く）を拒否。`file-read-data` は既定で拒否し、`/`（literal）・`/System`・`/usr/lib`・`/usr/share`・`/private/var/db/timezone`・`PYTHON_HOME`・`/dev/urandom`・`/dev/null`・`SELF`・`TARGET` だけを許す。
- `intake_common.py` に `SUPPORTED_EXTENSIONS`・`MAX_FILE_BYTES`・`FAILURE_CODES`・`WARNING_CODES` を、検査と同じ値で置く（検査は Seatbelt の中で自分しか読めないので、共有せずに 2 か所に書き、テストで一致を守る）。
- `run_checker`: Python の場所は、フックを動かしている python3 から決める。`python_home = realpath(sys.base_prefix)`、`python_exe = realpath(join(sys.base_prefix, "bin", "python3"))`。コマンドは `/usr/bin/sandbox-exec -f <sb> -D PYTHON_HOME=… -D SELF=… -D TARGET=<real_path> <python_exe> -I -B <SELF> <real_path>`。`stdin`・`stderr` は `DEVNULL`、`stdout` は受け取る（64 KiB で打ち切る）、`env={}`、`timeout` 付き。終了コードが 0 か 1 で、出力が 1 つの JSON で、`result` が終了コードと合い（0 は `pass`、1 は `fail`）、`failures`・`warnings` がすべて語彙の中にあるときだけ、その値を返す。それ以外は `error`（`failures`・`warnings` は空）。`TimeoutExpired` → `timeout`、`/usr/bin/sandbox-exec` がない → `sandbox_missing`。

- [ ] **Step 4: 人が通常のターミナルでテストを動かす**

Run: `cd <リポジトリ> && WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest tests.test_sandbox_profile -v`
Expected: すべて PASS（skip なし）。Claude の Bash では sandbox なしで動く 3 つだけ PASS で、ほかは skip。

- [ ] **Step 5: コミットする**

```bash
git add scripts/check_workbook.sb hooks/intake_common.py tests/test_sandbox_profile.py
git commit -m "feat: run the checker under a no-network, no-write Seatbelt profile"
```

---

<a name="task-6"></a>

### Task 6: 入力の確認と警告の確認の記録

設計の[入力の確認](design.md#consent)のとおり、承認を記録したら同じフックが検査を動かし、結果を承認と一緒に記録して、固定の語彙で会話に返す。警告があれば、2 つ目の固定の質問（警告の確認）の承認も記録する。

**Files:**
- Modify: `hooks/intake_common.py`
- Create: `hooks/record_consent.py`、`hooks/record-consent.sh`、`tests/test_record_consent.py`

**Interfaces:**
- Consumes: Task 5 の `run_checker`、research の 9・10・A（答えの場所）・15（`additionalContext`）と 6（環境変数）
- Produces（`hooks/intake_common.py`）:
  - `intake_dir() -> str`: 展開したパス（`realpath` ではない）。research の 6 で環境変数が使えると分かれば `WORKBOOK_INTAKE_DIR` を読み、なければ `~/workbook-intake`。
  - `resolve_in_intake(path: object) -> tuple[str | None, str]`: 合格なら（`realpath`、`"ok"`）、不合格なら（`None`、理由）。理由の語彙と判定の順: `bad_input`（文字列でない）→ `path_not_absolute` → `intake_dir_invalid`（ない、ディレクトリでない、シンボリックリンク）→ `outside_intake`（`realpath` が受け取り用フォルダの `realpath` の真下でない。フォルダ自身も外とみなす）→ `not_regular_file` → `unsupported_extension`（小文字にして比べる）→ `file_too_large`（`MAX_FILE_BYTES` を超える）
  - `file_key(real_path: str) -> str`: `unicodedata.normalize("NFC", real_path)`
  - `file_sha256(real_path: str) -> str`
  - 固定の文: `CONSENT_HEADER`・`CONSENT_QUESTION_PREFIX`・`CONFIRM_LABEL`・`CONFIRM_DESCRIPTION`・`CANCEL_LABEL`・`CANCEL_DESCRIPTION`、`WARNINGS_HEADER`・`WARNINGS_QUESTION_PREFIX`・`WARNINGS_LIST_PREFIX`・`CONTINUE_LABEL`・`CONTINUE_DESCRIPTION`・`STOP_LABEL`・`STOP_DESCRIPTION`（下の Step 3）
  - `consent_question(path: str) -> str`: `CONSENT_QUESTION_PREFIX + path`
  - `expected_questions(path: str) -> list[dict]`: 入力の確認として、AskUserQuestion の `questions` に期待する値
  - `warnings_question(path: str, warnings: list[str]) -> str`: `WARNINGS_QUESTION_PREFIX + path + WARNINGS_LIST_PREFIX + ", ".join(warnings)`
  - `expected_warnings_questions(path: str, warnings: list[str]) -> list[dict]`: 警告の確認として期待する値
  - 記録: `${CLAUDE_PLUGIN_DATA}/consents/<session_id の SHA-256>.jsonl` に 1 行 1 件。ディレクトリは 0700。`CLAUDE_PLUGIN_DATA` がなければ、記録しない・承認なしとする。壊れた行は読み飛ばす。
    - `record_consent(session_id: str, key: str, sha256: str, check: dict) -> bool`: `{"kind": "consent", "path": key, "sha256": …, "status": …, "failures": […], "warnings": […]}`（`check` は `run_checker` の戻り値）
    - `find_consent(session_id: str, key: str, sha256: str) -> dict | None`: 最後に記録した入力の確認
    - `record_warnings_ack(session_id: str, key: str, sha256: str, warnings: list[str]) -> bool`: `{"kind": "warnings_ack", "path": key, "sha256": …, "warnings": […]}`
    - `has_warnings_ack(session_id: str, key: str, sha256: str, warnings: list[str]) -> bool`
- Produces（`hooks/record_consent.py`）:
  - `selected_answer(hook_input: dict, question: str) -> str | None`
  - `handle(hook_input: dict) -> str | None`: 会話に返す文（下の語彙）。質問がこのプラグインのもの（2 つの接頭辞のどちらかで始まる）でなければ `None`。
  - `main() -> int`: 常に 0。`handle` が文を返したときだけ、PostToolUse の JSON（`hookSpecificOutput.additionalContext`。形は research の 15）を 1 つ出す。
  - 会話に返す文（固定の語彙だけ）:
    - `workbook-intake: consent=recorded; check=<status>; failures=<語彙をカンマで>; warnings=<語彙をカンマで>`（空なら `none`）
    - `workbook-intake: consent=not_recorded; reason=<理由>`
    - `workbook-intake: warnings_ack=recorded`、`workbook-intake: warnings_ack=not_recorded; reason=<理由>`
    - 理由の語彙: `bad_input`、`question_mismatch`、`not_confirmed`（答えが `CONFIRM_LABEL`・`CONTINUE_LABEL` でない）、`resolve_in_intake` の理由、`consent_store_unavailable`、`no_consent`（警告の確認で、同じファイル・中身の入力の確認がない）、`internal_error`

- [ ] **Step 1: 失敗するテストを書く**

`HOME` と `CLAUDE_PLUGIN_DATA` を一時ディレクトリにする。記録と文の判定のテストは、`record_consent.handle` をプロセスの中で呼び、`intake_common.run_checker` を mock にする（sandbox なしで動く）。入口のスクリプトを通すテストは `test_wrapper_end_to_end` だけにし、Task 5 と同じ条件で skip する。

```python
def test_records_confirmed_answer(self):             # 固定の文・選択肢そのまま、答え CONFIRM_LABEL → find_consent が記録を返す
def test_returns_check_result(self):                 # run_checker が pass・warnings [vba_project] → 文は "workbook-intake: consent=recorded; check=pass; failures=none; warnings=vba_project"
def test_failed_check_is_recorded_and_reported(self): # run_checker が fail・failures [xml_dtd] → 記録され、文に "check=fail; failures=xml_dtd"
def test_cancel_not_recorded(self):                  # 答え CANCEL_LABEL → 記録されない、reason=not_confirmed
def test_altered_question_not_recorded(self):        # 固定の文の 1 文字違い → 記録されない、reason=question_mismatch
def test_altered_options_not_recorded(self):         # 説明の書き換え・選択肢の追加・multiSelect true・質問 2 つ → どれも記録されない（レビューの重点 4）
def test_path_outside_intake_not_recorded(self):     # 受け取り用フォルダの外 → reason=outside_intake
def test_relative_path_not_recorded(self):           # reason=path_not_absolute
def test_missing_file_reported(self):                # ファイルがない → reason=not_regular_file
def test_other_tool_not_recorded(self):              # tool_name が AskUserQuestion でない → None
def test_other_question_produces_no_output(self):    # このプラグインのものでない質問 → None（ほかのスキルの質問に口を出さない）
def test_malformed_input_not_recorded(self):         # JSON でない・項目の欠け → 記録されず、終了コード 0
def test_missing_plugin_data_not_recorded(self):     # CLAUDE_PLUGIN_DATA なし → reason=consent_store_unavailable
def test_nfd_and_nfc_paths_are_same_file(self):      # macOS だけ。NFD の名前のファイルを NFC のパスで承認 → NFD のパスの file_key で記録あり（レビューの重点 1）
def test_consent_is_per_session(self):               # 別の session_id では記録なし
def test_consent_is_per_content(self):               # 記録の後に中身を変える → 記録なし
def test_warnings_ack_recorded(self):                # 警告 [vba_project] で承認済み → 警告の確認、答え CONTINUE_LABEL → has_warnings_ack が真、文は "workbook-intake: warnings_ack=recorded"
def test_warnings_ack_with_other_warnings_not_recorded(self): # 記録と違う警告の並び → reason=question_mismatch
def test_warnings_ack_without_consent_not_recorded(self): # 入力の確認がない → reason=no_consent
def test_warnings_ack_stop_not_recorded(self):       # 答え STOP_LABEL → reason=not_confirmed
def test_context_has_no_file_derived_strings(self):  # パスとファイル名に目印の文字列を入れ、返す文に含まれないこと
def test_wrapper_end_to_end(self):                   # 入口のスクリプトに JSON を渡し、本物の run_checker で記録と JSON の出力まで通る
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_record_consent -v`
Expected: `record_consent` を import できずに失敗する。

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

WARNINGS_HEADER = "Warnings"
WARNINGS_QUESTION_PREFIX = (
    "workbook-intake: The check reported warnings for this file. Continue the analysis?\n"
    "このファイルの検査で警告が出ました。解析を続けますか。\n"
    "File / ファイル: "
)
WARNINGS_LIST_PREFIX = "\nWarnings / 警告: "
CONTINUE_LABEL = "Continue / 続ける"
CONTINUE_DESCRIPTION = "I reviewed the warnings and continue. / 警告を確かめたうえで続ける。"
STOP_LABEL = "Stop / やめる"
STOP_DESCRIPTION = "Do not analyze this file. / このファイルは解析しない。"
```

`expected_questions(path)` と `expected_warnings_questions(path, warnings)` は、`question`・`header`・`options`（それぞれの 2 つ、`label` と `description` だけ）・`multiSelect: false` の 1 問。`handle` は次のとおり。
- `tool_name` が `AskUserQuestion` でない、`questions` がちょうど 1 問でない、質問が 2 つの接頭辞のどちらでも始まらない → `None`。
- 入力の確認: 接頭辞の後をパスとし（改行があれば `question_mismatch`）、`questions == expected_questions(path)`、`selected_answer` が `CONFIRM_LABEL`、`resolve_in_intake` が `ok` のときだけ、`run_checker` を動かして `record_consent` する。
- 警告の確認: 接頭辞と `WARNINGS_LIST_PREFIX` の間をパスとし、`resolve_in_intake` → `file_sha256` → `find_consent`（なければ `no_consent`）→ `questions == expected_warnings_questions(path, 記録の warnings)` → `selected_answer` が `CONTINUE_LABEL` のときだけ `record_warnings_ack` する。

`selected_answer` は research の 9 で分かった項目から読む（モデルが入力に書いた値で偽れないことは、research の A で確かめ済みであること）。`main` は例外をすべて捕まえ、`internal_error` を返す（このプラグインの質問か分からないときは何も出さない）。`record-consent.sh` は `/usr/bin/xcode-select -p` の先の python3 を `-I -B` で起動するだけにし、なければ何もせずに 0 で終える（記録がないので、xlide の呼び出しはフックが止める）。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest tests.test_record_consent -v && shellcheck hooks/record-consent.sh`
Expected: `test_wrapper_end_to_end` は skip、ほかは PASS。shellcheck の指摘なし。`test_wrapper_end_to_end` は、Task 7 の Step 5 で人が通常のターミナルで動かす。

- [ ] **Step 5: コミットする**

```bash
git add hooks/intake_common.py hooks/record_consent.py hooks/record-consent.sh tests/test_record_consent.py
git commit -m "feat: record input consent, check results and warning acknowledgements"
```

---

<a name="task-7"></a>

### Task 7: xlide の呼び出しの判定

**Files:**
- Create: `hooks/guard_xlide.py`、`hooks/guard-xlide.sh`、`hooks/hooks.json`、`hooks/allowed-tools.txt`、`tests/test_guard_xlide.py`

**Interfaces:**
- Consumes: Task 5 の `run_checker`、Task 6 の `resolve_in_intake`・`file_key`・`file_sha256`・`find_consent`・`has_warnings_ack`・`record_consent`・`record_warnings_ack`、research の 1（`agent_type`）とツールの一覧
- Produces:
  - `hooks/allowed-tools.txt`: 1 行目は `# reviewed-for: xlide-mcp==1.2.4`（どの版のソースで見直したか）。以降は 1 行に `<ツール名> <file|nofile>`（例: `xlide_doctor nofile`）。`file` は `file_path` が必須のツール。`#` で始まる行と空行は読み飛ばす。
  - `TOOL_PREFIX = "mcp__plugin_workbook-intake_xlide__"`、`ANALYST_AGENT_TYPE = "workbook-intake:excel-analyst"`（research の 1 の値）
  - `load_allowlist() -> dict[str, str]`（ツール名 → `"file"` か `"nofile"`）
  - `decide(hook_input: dict) -> tuple[str, str]`: （`"allow"` か `"deny"`、理由の語彙）
  - `main() -> int`: 常に 0。PreToolUse の JSON を 1 つ出す。

- [ ] **Step 1: 失敗するテストを書く**

`HOME`・`CLAUDE_PLUGIN_DATA` を一時ディレクトリにし、承認は Task 6 の `record_consent`・`record_warnings_ack` で直接書く。判定のテストは `decide` をプロセスの中で呼び、`run_checker` を mock にする（sandbox なしで動く）。本物の `run_checker` を通すテスト（`test_allows_consented_checked_file`・`test_check_failure_denied`・`test_check_timeout_denied`）は、Task 5 と同じ条件で skip。拒否の理由は、出力の `permissionDecisionReason` に語彙が入ることで見る。

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
def test_check_failure_denied(self):                       # zip bomb → check_failed、理由に "compression_ratio_too_high"
def test_check_timeout_denied(self):                       # CHECK_TIMEOUT_SECONDS を 0.001 に → check_timeout
def test_checker_error_denied(self):                       # run_checker が status "error"・"sandbox_missing" を返す mock → check_error・sandbox_missing
def test_warnings_without_ack_denied(self):                # run_checker が warnings [vba_project] を返す mock、警告の確認なし → warnings_not_acknowledged、理由に "vba_project"
def test_warnings_with_ack_allowed(self):                  # 同じ警告で record_warnings_ack 済み → allow
def test_ack_for_other_warnings_denied(self):              # 記録した警告と、今の検査の警告が違う → warnings_not_acknowledged
def test_malformed_input_denied(self):                     # JSON でない・空 → bad_input、終了コード 0
def test_internal_error_denied(self):                      # decide が例外を投げる mock → internal_error
def test_wrapper_denies_without_python(self):              # DEVELOPER_DIR を存在しないディレクトリにする → python_missing
def test_reason_has_no_file_derived_strings(self):         # パスとファイル名に目印の文字列を入れ、出力に含まれないこと
def test_hooks_json(self):                                 # matcher・timeout 30・onFailure "block"・command の形
def test_allowlist_reviewed_for_pinned_version(self):      # allowed-tools.txt の reviewed-for の値 == .mcp.json の "--from" の次の値（版を上げて許可リストを見直さないと失敗する）
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide -v`
Expected: `guard_xlide` を import できずに失敗する。

- [ ] **Step 3: 判定を書く**

`decide` の順（設計の[フック](design.md#hook)の 1〜5 に、補足を足したもの）:
1. `tool_name` が `TOOL_PREFIX` で始まらない → `not_plugin_server`
2. 接頭辞を除いた名前が `load_allowlist()` にない → `tool_not_allowed`
3. `agent_type` が `ANALYST_AGENT_TYPE` でない → `wrong_caller`
4. `tool_input` が辞書でない → `bad_input`。`file_path` 以外のキーで、名前に `path`・`file`・`dir`・`folder`・`root` を含む（大文字小文字を問わない）ものがある → `unexpected_path_argument`。`file` 種で `file_path` がない → `missing_file_path`。
5. `file_path` があれば: `resolve_in_intake`（不合格ならその理由）→ `CLAUDE_PLUGIN_DATA` がない → `consent_store_unavailable` → `find_consent(session_id, file_key, file_sha256)` がない → `no_consent` → `run_checker`（`fail` → `check_failed`、`error` → `check_error`、`timeout` → `check_timeout`、`sandbox_missing` → `sandbox_missing`）→ 警告があり、`has_warnings_ack(session_id, file_key, file_sha256, 今の検査の warnings)` でない → `warnings_not_acknowledged`
6. すべて通れば `allow`（理由 `ok`）

出力は `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": …, "permissionDecisionReason": "workbook-intake: <理由>[ (<語彙をカンマで>)]. See the README (Troubleshooting)."}}`。括弧の中は `check_failed` の不合格の語彙と、`warnings_not_acknowledged` の警告の語彙だけ。`main` は例外をすべて捕まえて `internal_error` で拒否する。

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
- Consumes: Task 6 の固定の文と、会話に返す文の語彙、Task 7 の `allowed-tools.txt`・`TOOL_PREFIX`、research の C（スキルからスクリプトの場所を指す方法）
- Produces: `doctor.sh` の出力は 1 行に `ok <項目>` か `missing <項目>`。項目は `macos`・`uvx`・`python3`・`sandbox_exec`・`intake_dir_protected`。足りないものがあれば最後に `See README: Requirements` を出して終了コード 1、なければ 0。`intake_dir_protected` は、Bash から受け取り用フォルダの中を一覧できない（`ls -A` が失敗する）ときに `ok`、一覧できたら `missing`（設計の[前提の確認](design.md#doctor)）。受け取り用フォルダがないときも一覧できないので `ok` になる。あるかどうかは、sandbox の外のフックが確かめる。

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_doctor.py（HOME を一時ディレクトリ、PATH に uvx の偽物を置いたディレクトリを入れる）
def test_all_present_and_protected(self):  # 受け取り用フォルダの権限を 000 にして一覧できなくする → 終了コード 0、"missing" なし（後で権限を戻す）
def test_readable_intake_dir_stops(self):  # 一覧できるフォルダ → "missing intake_dir_protected"、終了コード 1、"See README: Requirements"
def test_uvx_missing(self):                # PATH から外す → "missing uvx"

# tests/test_skill_and_agent.py
def test_agent_tools_match_allowlist(self):   # frontmatter の tools の集合 == {TOOL_PREFIX + 名前 for 名前 in allowed-tools.txt}
def test_agent_has_no_unsupported_fields(self): # hooks・mcpServers・permissionMode を書かない
def test_skill_contains_consent_copy(self):   # 入力の確認と警告の確認の固定の文（CONSENT_* ・CONFIRM_*・CANCEL_*・WARNINGS_*・CONTINUE_*・STOP_*）がそのまま入る
def test_skill_does_not_run_checker_in_bash(self): # SKILL.md に "check_workbook.py" が出てこない（検査はフックだけが動かす）
def test_skill_description_makes_no_safety_claim(self): # description に "safe"・"secure"・"安全" がない
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_doctor tests.test_skill_and_agent -v`
Expected: ファイルがなく失敗する。

- [ ] **Step 3: `doctor.sh`・エージェント・スキルを書く**

- `doctor.sh`: 設計の[前提の確認](design.md#doctor)の項目を見る（`uname -s` が `Darwin`、`command -v uvx`、`$(xcode-select -p)/usr/bin/python3`、`/usr/bin/sandbox-exec`、`ls -A <受け取り用フォルダ>` が失敗する）。受け取り用フォルダは Task 6 の `intake_dir` と同じ決め方にする。
- `agents/excel-analyst.md`: frontmatter は `name: excel-analyst`、`description`、`tools`（許可リストの完全な名前をカンマ区切り）。本文は設計の[サブエージェント](design.md#subagent)の 5 点を、英語で、自分の言葉で書く。
- `skills/analyze/SKILL.md`: frontmatter は `name: analyze` と `description`（Excel のブックの数式・構造・VBA の解析を頼まれたときに起動する書き方。安全と読める語を使わない）。本文は設計の[流れ](design.md#flow)の 0〜3 と[スキル](design.md#skill)のとおり。次を書く。
  - 最初に `doctor.sh` を動かす（プラグインの場所は research の C の方法で書く）。`missing` があれば、README の Requirements を示して止まる。
  - ファイルの名前は人に聞き、`$HOME` から受け取り用フォルダの絶対パスを組み立てる（Bash で一覧しない。一覧できないのが正しい状態）。
  - 入力の確認は、AskUserQuestion に Task 6 の固定の文と選択肢をそのまま渡す（`File / ファイル: ` の後に、ファイルの絶対パス）。
  - フックが返した `workbook-intake: …` の文を読む。`consent=not_recorded` か `check=` が `pass` 以外なら、理由の語彙を人に伝えて止まる。`warnings=` が `none` 以外なら、警告の確認を、Task 6 の固定の文と選択肢で出す（`WARNINGS_LIST_PREFIX` の後に、返された警告の語彙をそのままの順で）。`warnings_ack=recorded` でなければ止まる。
  - xlide のツール（`TOOL_PREFIX` で始まるもの）が見えなければ、README の Troubleshooting を示して止まる。
  - フックに拒否されたら、ファイルを Read・Bash（`unzip`・Python など）・ほかのスキルで読もうとせず、拒否の理由を人に伝えて止まる。

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

設計の [README](design.md#readme) と[更新と保守](design.md#maintenance)の項目を、`README.md` に英語で書く。冒頭（タイトルの直後）に、日本語版へのリンク（`[日本語](README.ja.md)`）を置く。`README.ja.md` は同じ構成の日本語版にし、冒頭に英語版へのリンク（`[English](README.md)`）を置く。日本語の見出しには、ユーザーの Markdown の規則どおり、直前に `<a name="…"></a>` を置く。どちらにも次を書く: research の D の結果（`engines` で宣言できなければ、Claude Code 2.1.295 以上が要ること）。Configuration に、research の 12・14 で確かめた書き方で、受け取り用フォルダの読み込みの拒否（必須。`doctor.sh` が確かめる）、sandbox の外でコマンドを動かす逃げ道を使えなくする設定（推奨）、受け取り用フォルダの書き込みの拒否（推奨）を書く。Usage に、ファイルを受け取り用フォルダに置き、ファイルの名前を示して頼むこと（Claude は一覧できない）。Limitations に、推奨設定がない環境では、スキルを通らない使い方で Bash から読めること（設計の[受け入れるリスク](design.md#risks)）。Troubleshooting に、フックの拒否の理由の語彙（Task 7）、入力の確認のフックが返す文の語彙（Task 6）、`doctor.sh` の項目（Task 8）の意味。Maintenance には、使う人に向けた方針（設計の[更新と保守](design.md#maintenance)）だけを書き、作者の手順は runbook へのリンクにする。Checks に、検査の不合格と警告の語彙（Task 3・4）の意味。

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

入れ方と設定は README のとおり（ローカルのリポジトリをマーケットプレイスとして足し、受け取り用フォルダの読み込みの拒否を設定する）。設計の完了条件のすべての項目を、表にして test-report に書き、項目ごとに、頼んだこと・期待・結果（拒否の理由の語彙など）を記録する。

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

- [x] **Step 1: `/review` を実行し、指摘への対応を決める。直したら、全体のテストを実行し直す。** 1 回目の結果と採否は [test-report のレビュー](test-report.md#review-1)。小さな指摘は `be03451` で直した。検査と xlide の読み方の違いなどは、[Task 13](#task-13)〜[Task 15](#task-15) で直す（ユーザーの判断、2026-11-25）。Task 15 の後に、`/review` をもう一度実行してから Step 2 に進む。2 回目の結果と採否は [test-report のレビュー](test-report.md#review-2)。小さな指摘は `fe3b14c`・`e4ad15b`・`25108c0` で直した。残りは [Task 16](#task-16)〜[Task 19](#task-19) で直す（ユーザーの判断、2026-11-25）。Task 19 の後に、`/review` を 3 回目として実行してから Step 2 に進む。3 回目の結果と採否は [test-report のレビュー](test-report.md#review-3)。小さな指摘は `77dd89c`・`1fb2760` で直した。残りは [Task 20](#task-20)〜[Task 24](#task-24) で直す（ユーザーの判断、2026-11-26）。Task 24 の後に、`/review` を 4 回目として実行してから Step 2 に進む。4 回目の結果と採否は [test-report のレビュー](test-report.md#review-4)。小さな指摘は `5d36800` で直した。残りは [Task 25](#task-25)〜[Task 28](#task-28) で直す（ユーザーの判断、2026-11-26）。Task 28 の後に、`/review` を 5 回目として実行してから Step 2 に進む。5 回目の結果と採否は [test-report のレビュー](test-report.md#review-5)。小さな指摘は `62d094e` で直した。残りは [Task 29](#task-29)〜[Task 32](#task-32) で直す（ユーザーの判断、2026-11-26）。Task 32 の後に、`/review` を 6 回目として実行してから Step 2 に進む。
- [ ] **Step 2: `/security-review` を実行する（外部からの入力と権限の境界に触れるため）。**
- [ ] **Step 3: Codex のレビューを行う（必須。ユーザーの指定）。** 人が通常のターミナルで `codex review` と、challenge（変更前と比べた後退と、壊れる入力を挙げてもらう。プロンプトは Claude が書く）を実行する。結果は、CLAUDE.md の Skill routing の手順で読み、test-report に記録してから採否を整理する。直したら、全体のテストを実行し直す。上限は 5 回。
- [ ] **Step 4: 作業文書を締める。** design.md・plan.md・research・test-report の `status` を `done` にしてコミットする。
- [ ] **Step 5: `/crit-review` でブランチの差分を開き、`approved: true` を待つ。** その後に `cc-safe-push` と `cc-safe-pr create` を使う（許可リストにないリポジトリなら、人にコマンドを示す）。PR を作ったら `gh pr checks` で CI の結果を確かめる。
- [ ] **Step 6: 公開のときの人の作業を伝える。** GitHub の説明文とトピック（`claude-code`・`claude-code-plugin` など）の設定、Dependabot alerts を有効にすること（リポジトリの Settings の Code security）、dotfiles の settings.json の作業（設計の[人の作業](design.md#human-steps)。dotfiles で別に行う）。

---

<a name="review-fixes"></a>

## 1 回目の `/review` の指摘の修正（Task 13〜15）

1 回目の `/review` で、検査と xlide の読み方が食い違い、検査を外せると分かった（[test-report](test-report.md#review-1)）。xlide 1.2.4 の読み方は [research-xlide-parsing.md](research-xlide-parsing.md) に調べた。設計は 2026-11-25 の改訂で直した（[design.md の改訂](design.md#revisions)）。

考え方: 個々の食い違いを塞ぐのではなく、食い違いが起きない範囲だけを通す。

- zip は、4 通りの読み手（pyofficeeditor の `ZipArchive`、pyopenvba の `OpcFile`、Python 3.15 の `zipfile`、検査の Python 3.9 の `zipfile`）が必ず同じエントリを同じバイトで読む形だけを通し、ほかは不合格にする（Task 13）。zip bomb と DTD の不合格は、この前提の上でしか効かない。
- XML の部品は、名前や関係ではなく中身で選ぶ。名前空間を外したローカル名で見る。数えるもの（非表示のシート、外部リンク）は、関係の先を解決して本体を見分けることに頼らず、読んだすべての部品の要素で数える。食い違いうる部品は `strings_not_checked` にする（Task 14）。
- パスは、xlide が開くものと同じ正規形だけを通す（Task 15）。

調査の「[検査に求められること](research-xlide-parsing.md#requirements)」のうち、採らないものと理由（主担当の判断）:

| 求められること | 判断 | 理由 |
| --- | --- | --- |
| expat で読めない部品を不合格にする | 採らない。`strings_not_checked` の警告のまま | 設計では、確かめきれないことを警告で示し、人が決める（`.xlsb` と同じ）。Excel が書く XML は読めるので、まれ。README の警告の説明を「その部品のシートの状態や関係も分からない」に直す |
| XML 宣言が先頭以外にある、ルート要素の後ろに何かある、最初の `<` の前に文字がある部品を拒否する | 採らない。expat が読めないので `strings_not_checked` になる | 上と同じ |
| ルートの officeDocument がちょうど 1 つで、`xl/workbook.xml` に解決される | 採らない | 非表示のシートをすべての部品で数えるので、本体を見分けなくてよい |
| 内部の Target の `\`・`%`・`#`・`//` などを拒否する | 採らない | 関係で部品を選ばなくなるので、Target の解決が食い違っても、読む部品は変わらない |
| シートの状態を、本体の `sheets` の直下の `sheet` だけで数える | 採らない。すべての `sheet` 要素で数える | 多めに数える側に倒す |
| M と VBA のソースも文字列を確かめる | 採らない | `power_query` と `vba_project` の警告が知らせる。範囲が広がりすぎる |

---

<a name="task-13"></a>

### Task 13: 検査（zip の形）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`、`tests/workbook_factory.py`（生のバイト列を組み替える補助）

**Interfaces:**
- Consumes: Task 3 の `check`・`FAILURE_CODES`（語彙は増やさない）
- Produces: `_check_layout(path: str, size: int) -> str | None`。`"not_zip"`・`"unsafe_part_name"`・`None` を返す。`check()` の OLE の判定の後、`zipfile.ZipFile` で開く前に呼び、`None` でなければその語彙で不合格にする。

判定はファイルのバイト列から直接読む（`zipfile` に任せない。Python の版で振る舞いが違うため）。値は [research-xlide-parsing.md の ZIP](research-xlide-parsing.md#zip) による。

| 確かめること | 違えば |
| --- | --- |
| ファイルの最後の 22 バイトが EOCD（`PK\x05\x06`）で、注釈の長さが 0 | `not_zip` |
| EOCD のディスク番号 2 つが 0、このディスクのエントリ数と総エントリ数が等しい | `not_zip` |
| ZIP64 の印がない: 最後の 42 バイト目からの 4 バイトが `PK\x06\x07` でない。EOCD と中央のエントリの大きさ・オフセットに `0xFFFFFFFF`（件数は `0xFFFF`）がない。extra に 0x0001 がない | `not_zip` |
| 中央ディレクトリのオフセット + 大きさ = ファイルの大きさ − 22（前置きのデータがない） | `not_zip` |
| 中央ディレクトリを総エントリ数の分だけ読むと、大きさをちょうど使い切る。各エントリが `PK\x01\x02` で始まり、extra が (id, 長さ) の並びでちょうど埋まる | `not_zip` |
| 中央とローカルの extra に Unicode Path（0x7075）がない | `not_zip` |
| ローカルヘッダーが `PK\x03\x04` で始まり、名前のバイト列・フラグ・圧縮方式が中央と同じ。bit 3 がなければ、CRC と 2 つの大きさも中央と同じ | `not_zip` |
| エントリの範囲（ローカルヘッダー + 名前 + extra + 中央の圧縮後の大きさ + bit 3 ならデータ記述子。記述子は `PK\x07\x08` で始まれば 16 バイト、そうでなければ 12 バイト）を、オフセットの順に並べると、0 から中央ディレクトリのオフセットまで、隙間も重なりもなく並ぶ | `not_zip` |
| 名前: bit 11 があれば UTF-8 として正しく、なければ ASCII だけ。NUL を含まない。空のセグメント（`//`）と `.` のセグメントがない。`/` で終わるなら、2 つの大きさが 0 | `unsafe_part_name` |
| 中身の長さ（Task 13 のレビューで足した）: 格納（方式 0）なら、圧縮後の大きさ = 展開後の大きさ。deflate（方式 8）なら、データの位置から圧縮後の大きさのバイトを展開すると、流れがちょうど終わり（余りなし）、展開した長さが中央の展開後の大きさに等しい。どちらも CRC が中央の値と同じ。展開は展開後の大きさを超えたところで止める | `not_zip` |

今の判定（圧縮方式、`\`・`..`・先頭の `/`・ドライブ名、大文字小文字を無視した重複、暗号化の bit、宣言の大きさの和）は残す。暗号化の bit は今の `encrypted` のままにする（`_check_layout` では見ない）。中身のない `/` で終わるエントリは、警告の走査で今のとおり飛ばす。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_two_central_directories_fail(self):           # Red Team の作り（検査の向きと xlide の向きで別の部品の組）→ "not_zip"
def test_prefixed_data_fails(self):                    # 正しい zip の前に 1 バイト → "not_zip"
def test_archive_comment_fails(self):                  # 注釈 b"x"（EOCD の長さも合わせる）→ "not_zip"
def test_trailing_bytes_after_eocd_fail(self):         # EOCD の後ろに 1 バイト → "not_zip"
def test_gap_between_entries_fails(self):              # 2 つ目のエントリの前に 1 バイト挟み、中央のオフセットを合わせる → "not_zip"
def test_entry_count_mismatch_fails(self):             # EOCD の 2 つのエントリ数を 1 減らす → "not_zip"
def test_local_name_mismatch_fails(self):              # ローカルヘッダーの名前だけを同じ長さの別名にする → "not_zip"
def test_unicode_path_extra_fails(self):               # 中央の extra に 0x7075 → "not_zip"
def test_zip64_records_fail(self):                     # zipfile の force_zip64=True で書いた部品 → "not_zip"
def test_data_descriptor_layout_passes(self):          # シークできない出力に zipfile で書いた（bit 3 と記述子がある）ブック → "pass"
def test_empty_segment_name_fails(self):               # "xl//workbook.xml" → "unsafe_part_name"
def test_dot_segment_name_fails(self):                 # "xl/./a.xml" → "unsafe_part_name"
def test_nul_in_name_fails(self):                      # 名前のバイト列に NUL（生のバイト列で作る）→ "unsafe_part_name"
def test_directory_entry_with_content_fails(self):     # "xl/book.xml/" に中身 → "unsafe_part_name"
def test_empty_directory_entry_passes(self):           # "xl/" で大きさ 0 → "pass"
def test_non_ascii_name_without_utf8_flag_fails(self): # bit 11 を落とした "xl/表.xml" → "unsafe_part_name"
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: 新しいテストのうち、`test_data_descriptor_layout_passes`・`test_empty_directory_entry_passes` 以外が失敗する。既存のテストは通る。

- [ ] **Step 3: `_check_layout` を書き、`check()` から呼ぶ**

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（`sandbox-exec` のテストは skip）。

- [ ] **Step 5: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py tests/workbook_factory.py
git commit -m "fix: reject ZIP layouts that xlide's readers can interpret differently"
```

---

<a name="task-14"></a>

### Task 14: 検査（XML の部品の選び方と読み方）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`

**Interfaces:**
- Consumes: Task 13 の `_check_layout`（zip の形が素直なことを前提にする）、Task 4 の `WARNING_CODES`（語彙は増やさない）
- Produces: なし（`check()` の結果の形は変えない）

読み方（値は [research-xlide-parsing.md の XML](research-xlide-parsing.md#xml) による）:

1. 部品の選び方: `.xlsb` 以外では、すべての部品（中身のない `/` で終わるエントリを除く）について、文字コードを pyofficeeditor と同じ規則で決める。BOM（UTF-8・UTF-16LE・UTF-16BE）があればそれ、なければ先頭 2 バイトが `<\0` なら UTF-16LE、`\0<` なら UTF-16BE、ほかは UTF-8。部品の全体を、その文字コードで厳密に（`codecs.getincrementaldecoder(enc)("strict")` で）復号できて、`<` を含む部品を XML の部品とする。ほかの部品（画像、`vbaProject.bin` など）は読まない。名前（`.xml` など）、関係、`customXml/` かどうかでは選ばない。
2. XML の部品は、`xml.parsers.expat.ParserCreate(encoding=<1 で決めた文字コード>)` で、名前空間の処理なしに読む（宣言の `encoding` に従わない）。`ordered_attributes = True`、`buffer_text = True`。DTD は Task 3 の判定で先に止めている。
3. 部品ごとの件数は、部品ごとの入れ物に数え、1 の判定が済んでから全体に足す（復号に失敗した部品の件数は捨てる）。XML の部品で、expat が読めなければ `strings_not_checked` を 1 つ足す（読めた所までの件数は足す）。`MAX_PARSE_BYTES` を超える XML の部品は、読まずに `strings_not_checked`（今のまま）。
4. 名前は、`:` の後ろのローカル名で見る（`xmlns:Target` のローカル名は `Target`）。同じ要素に、同じローカル名の属性が 2 つ以上あれば、その部品に `strings_not_checked` を 1 つ足す（部品ごとに 1 回）。
5. 数え方:
   - ローカル名 `sheet` の要素の、ローカル名 `state` の最初の属性が `hidden` なら `hidden_sheet`、`veryHidden` なら `very_hidden_sheet`。どの部品でも数える（本体かどうかを見分けない）。
   - ローカル名 `Relationship` の要素は、どの部品でも、ローカル名 `TargetMode` が大文字小文字を無視して `external` なら `external_relationship`、ローカル名 `Type` の末尾で `_REL_TYPE_WARNINGS` を数える。
   - ローカル名 `externalReference` の要素で `external_link` を数える（関係の種類と部品の名前は問わない）。
   - 文字列は、属性の値（`xmlns` の宣言の値を含む）と文字のノード（CDATA の中身を含む。xlide は返さないが、多めに見る）を、今の `_count_string` で調べる。
6. `_count_string` は、値そのものと、`_xHHHH_`（16 進 4 桁）を文字に戻した値の両方で、不可視の文字と指示らしい文言を調べる（1 つの値で数えるのは各 1 回）。
7. 指示らしい文言は、`LONG_STRING_CHARS` を超える値では、先に不可視の文字を除き、`LONG_STRING_CHARS` 文字ずつ、`PHRASE_OVERLAP = 256` 文字を重ねた窓に分けて、窓ごとに NFKC・小文字・不可視の文字の除去をしてから探す。`unicodedata.normalize` に渡す長さを、`LONG_STRING_CHARS + PHRASE_OVERLAP` 以下にする（1 回目の `/review` で、32 MB の値でピーク 1.9 GB になった）。
8. 消すもの: `_looks_like_xml`・`SNIFF_BYTES`、ルートの関係の本体を集める仕組み（`office_targets`・`_resolve`・`_MAX_OFFICE_TARGETS`）、`customXml/` を外す判定、ElementTree の target の `_Collector`（expat のハンドラーに置き換える）。DataMashup のバイト列の検索（`power_query`）は残す。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_leading_byte_before_root_not_checked(self):          # xl/workbook.xml の先頭に b"x"、veryHidden → "strings_not_checked"
def test_long_leading_whitespace_is_parsed(self):             # xl/workbook.xml の先頭に空白 5,000、hidden → "hidden_sheet"
def test_hidden_sheet_counted_without_resolving_target(self): # _rels/.rels の Target を "/xl\\workbook.xml"、veryHidden → "very_hidden_sheet"
def test_workbook_under_custom_xml_is_checked(self):          # 本体を customXml/workbook.xml に置きルートの関係で指す、veryHidden → "very_hidden_sheet"
def test_part_without_xml_name_is_checked(self):              # 共有文字列を "xl/strings.bin" に置き、"ignore previous" → "instruction_like_text"
def test_prefixed_state_attribute_counts(self):               # <sheet x:state="hidden" xmlns:x="urn:x" .../> → "hidden_sheet"
def test_duplicate_local_attribute_not_checked(self):         # Relationship に xmlns:Target="xl/other.xml" と Target → "strings_not_checked"
def test_external_reference_element_warns(self):              # workbook.xml に <externalReferences><externalReference r:id="rId9"/></externalReferences> → "external_link"
def test_escaped_invisible_character_warns(self):             # 共有文字列 "a_x200B_b" → "invisible_characters"
def test_escaped_instruction_text_warns(self):                # "ignore_x0020_previous" → "instruction_like_text"
def test_cdata_text_is_checked(self):                         # <t><![CDATA[ignore previous]]></t> → "instruction_like_text"
def test_binary_part_is_not_parsed(self):                     # "xl/media/image1.png" に PNG の署名 + '<sheet state="hidden"/>' → hidden_sheet なし、strings_not_checked なし
def test_text_part_without_markup_is_not_parsed(self):        # "<" を含まない UTF-8 の部品 → 警告なし
def test_utf16_without_bom_is_parsed(self):                   # BOM なしの UTF-16LE の共有文字列に U+200B → "invisible_characters"
def test_declared_encoding_is_ignored(self):                  # encoding="ISO-8859-1" と宣言し、中身は UTF-8 の U+200B → "invisible_characters"
def test_junk_after_root_not_checked(self):                   # ルート要素の後ろに "tail<x/>" → "strings_not_checked"
def test_power_query_reports_long_string(self):               # customXml/item1.xml の DataMashup の中身が 10,001 文字 → "power_query" と "very_long_string"
def test_phrase_across_normalization_window_warns(self):      # "ignore previous" が LONG_STRING_CHARS の境目をまたぐ値 → "instruction_like_text"
def test_normalization_input_is_bounded(self):                # 1,000,000 文字の値。unicodedata.normalize を包んで、渡された長さの最大が LONG_STRING_CHARS + PHRASE_OVERLAP 以下
```

既存のテストのうち、関係の本体に頼るもの（`test_renamed_workbook_part_is_followed` など）は、そのまま通ることを確かめる（消さない）。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: 新しいテストの多くが失敗する。今の検査でも通りうるもの（`test_binary_part_is_not_parsed`・`test_text_part_without_markup_is_not_parsed`・`test_utf16_without_bom_is_parsed`）は、通ったかどうかを報告に書く。

- [ ] **Step 3: 上の 1〜8 を実装する**

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（`sandbox-exec` のテストは skip）。

- [ ] **Step 5: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py
git commit -m "fix: choose XML parts by content and read them the way xlide does"
```

---

<a name="task-15"></a>

### Task 15: パスの正規形、前提の確認、テストの穴、文書

**Files:**
- Modify: `hooks/intake_common.py`、`hooks/guard_xlide.py`、`hooks/record_consent.py`、`scripts/doctor.sh`、`tests/test_guard_xlide.py`、`tests/test_record_consent.py`、`tests/test_doctor.py`、`README.md`、`README.ja.md`、`skills/analyze/SKILL.md`、`docs/work/20261124_workbook-intake/test-report.md`
- Modify（Task 14 のレビューの後に足した）: `hooks/allowed-tools.txt`、`agents/excel-analyst.md`。`xlide_list_shapes` を許可リストとサブエージェントのツールから外す（ユーザーの判断、2026-11-25。xlide 自身の寛容な読み手を使い、厳密に読む検査と食い違うため）。`tests/test_guard_xlide.py` の許可リストの固定（20 件）を 19 件にし、`xlide_list_shapes` が `tool_not_allowed` になるテストを足す。README・runbook に許可したツールの数や一覧があれば合わせる。

**Interfaces:**
- Produces: `intake_common.canonical_path(path: str) -> bool`。`path == path.strip()`、`Cc`・`Cf`・`Zl`・`Zp` の文字がない、`NFC(os.path.realpath(path)) == NFC(path)` のすべてを満たすとき True。
- `guard_xlide._decide_file`: `resolve_in_intake` が通った後に `canonical_path(file_path)` でなければ `("deny", "path_not_canonical", [])`。
- `record_consent`: `_canonical` を `ic.canonical_path` に置き換える（入力の確認と警告の確認の両方）。NFC で比べるので、今より緩くなるのは正規化の違いだけ。
- `scripts/doctor.sh`: `python3` の項目は、今の確かめに加えて、`"$clt/usr/bin/python3" -I -c 'import os,sys; sys.exit(os.stat(os.path.realpath(sys.base_prefix)).st_uid != 0)'` が 0 で終わること（`run_checker` と同じ規則）。

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_guard_xlide.py
def test_symlink_alias_denied(self):          # 受け取り用フォルダに a.xlsx と b.xlsm、"b.xlsm "（末尾に空白）→ a.xlsx のリンク。a.xlsx に承認と合格の検査 → "path_not_canonical"
def test_trailing_space_file_denied(self):    # 名前の末尾に空白のある通常のファイル（承認あり）→ "path_not_canonical"
# tests/test_record_consent.py
def test_trailing_space_path_not_recorded(self):          # 末尾に空白のある通常のファイル → "consent=not_recorded; reason=path_not_canonical"
def test_warnings_question_without_list_not_acked(self):  # 一覧の部分を除いた警告の質問に CONTINUE_LABEL → "warnings_ack=not_recorded; reason=question_mismatch"、has_warnings_ack は False
# tests/test_doctor.py
def test_python_not_owned_by_root_is_missing(self):  # DEVELOPER_DIR を一時ディレクトリにし、usr/bin/python3 を「exit 1 する bash のスクリプト」にする → "missing python3"
```

既存の `test_consent_matches_across_unicode_normalization`（NFD と NFC）は、そのまま通ることを確かめる。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide tests.test_record_consent tests.test_doctor -v`
Expected: `test_warnings_question_without_list_not_acked` 以外の新しいテストが失敗する（このテストは今のコードでも通る見込みで、テストの穴を埋めるもの）。

- [ ] **Step 3: `canonical_path` を書き、フック 2 つと doctor.sh を直す**

- [ ] **Step 4: 文書を直す**

- `README.md`・`README.ja.md`:
  - 検査の不合格の表: `not_zip` に「読み手によって読み方が変わりうる zip の形（注釈、前置きのデータ、エントリの隙間、ZIP64、名前を付け替える extra）」、`unsafe_part_name` に「NUL・空のセグメント・`.` のセグメント・中身のあるディレクトリ名・文字コードの印と合わない名前」を足す。
  - 警告の表: `strings_not_checked` を「確かめきれなかった部品がある（`.xlsb`、大きすぎるか読めない XML、属性の重なり）。その部品の文字列・シートの状態・関係は分からない」にする。`very_long_string` に「Power Query のブックでも出る」を足す。
  - フックの拒否の表: `path_not_canonical` を足す（入力の確認の表の行と同じ意味）。
  - `doctor.sh` の項目: `python3` に「root の持ち物でない」を足す。
- `skills/analyze/SKILL.md`: フックの拒否の理由の一覧に `path_not_canonical` を足す。

- [ ] **Step 5: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v && shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh && claude plugin validate . --strict`
Expected: すべて PASS、指摘なし、通過。

- [ ] **Step 6: xlide の読み手と読み比べる（メインの会話で行う）**

1 回目の `/review` と調査で xlide と食い違った形（中央ディレクトリが 2 つ、先頭の 1 バイト、`\` の Target、`customXml/` の本体、`xmlns:Target`、`x:state`、`_xHHHH_`）のブックを `tmp/` に作る。検査の結果と、xlide 1.2.4 の uv の環境の python で pyofficeeditor に読ませた結果を並べる。読み比べのスクリプトは `tmp/` に置き、コミットしない。結果を test-report に書く。期待: どの形も、検査で不合格になるか、xlide が読むものと同じ警告か `strings_not_checked` が出る。

- [ ] **Step 7: 全体のテストを、人が通常のターミナルで実行する**

Run（人）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS、skip なし。結果を test-report に書く。

- [ ] **Step 8: コミットする**

```bash
git add hooks/intake_common.py hooks/guard_xlide.py hooks/record_consent.py scripts/doctor.sh tests/test_guard_xlide.py tests/test_record_consent.py tests/test_doctor.py
git commit -m "fix: require canonical paths in the hooks and a root-owned python in doctor"
git add README.md README.ja.md skills/analyze/SKILL.md
git commit -m "docs: describe the stricter ZIP and XML checks and path_not_canonical"
git add docs/work/20261124_workbook-intake/test-report.md
git commit -m "docs: record the parity check against xlide's readers"
```

その後、[Task 12](#task-12) の Step 1 の続き（2 回目の `/review`）に戻る。CI の macOS のジョブで、`xcode-select -p` の先の python が root の持ち物でなく失敗したら、`.github/workflows/ci.yml` の macOS のジョブに `DEVELOPER_DIR: /Library/Developer/CommandLineTools` を足すことを検討する（PR の後に分かる）。

---

<a name="review2-fixes"></a>

## 2 回目の `/review` の指摘の修正（Task 16〜19）

2 回目の `/review` の結果と採否は [test-report](test-report.md#review-2)。ユーザーの判断（2026-11-25）:

- D1: Power Query の部品の中の zip を検査で数え（F2）、展開の合計の上限を 256 MiB に下げる（F1）。VBA の展開（F3）は受け入れるリスクに記録する。
- D2: Seatbelt の 3 つは、人の確かめで再現したものだけを直す。再現したのは、ほかのプロセスの情報だけ。パスの綴りと `/System/Volumes/Data` は再現しなかったので、回帰のテストだけ足す。
- D3: 大きいブックの時間切れは、README に目安を書く。検査の結果の使い回しは、設計の非目標のまま。
- D4: `_check_layout` の未テストの規則にテストを足し、3 つのリスク（`disableAllHooks`、ほかのプラグインのフック、`uvx` の PATH）を記録する。簡素化の提案 2 件は採らない。

設計は 2026-11-25 の 2 つ目の改訂で直した（[design.md の改訂](design.md#revisions)）。語彙は増やさない。

<a name="task-16"></a>

### Task 16: 検査（zip の形の規則のテスト）

**Files:**
- Modify: `tests/test_check_workbook.py`（`LayoutTest`）。組み替えの補助が足りなければ `tests/workbook_factory.py`

**Interfaces:**
- Consumes: Task 13 の `_check_layout` と、`tests/workbook_factory.py` の `build_zip`・`deflated_entries`
- Produces: テストだけ。製品のコードは変えない。

[Task 13](#task-13) の表の規則のうち、テストがないものを 1 つずつ固定する。各テストは、その規則だけを破り、ほかの規則はすべて満たすファイルを作る。

- [ ] **Step 1: テストを書く**

```python
def test_declared_comment_length_without_comment_fails(self):  # 最後の 22 バイトの EOCD の注釈の長さを 5 にする（注釈のバイトは足さない）→ "not_zip"
def test_nonzero_disk_number_fails(self):                      # EOCD のディスク番号を 1 → "not_zip"
def test_nonzero_central_directory_disk_fails(self):           # EOCD の中央ディレクトリのディスク番号を 1 → "not_zip"
def test_disk_and_total_entry_counts_differ_fails(self):       # このディスクのエントリ数だけ 1 減らす（総数は正しい）→ "not_zip"
def test_zip64_locator_signature_fails(self):                  # 最後の中央のエントリに 20 バイトの注釈を付け、その先頭を b"PK\x06\x07" にする（ファイルの最後の 42 バイト目に来る）→ "not_zip"。同じ長さで先頭が違う注釈なら合格（対照）
def test_zip64_extra_in_central_entry_fails(self):             # 中央のエントリの extra に id 0x0001 の塊（長さ 0）→ "not_zip"
def test_unicode_path_extra_in_local_header_fails(self):       # ローカルヘッダーの extra にだけ id 0x7075 の塊 → "not_zip"
def test_extra_block_overrunning_its_field_fails(self):        # 中央の extra に id 0x9999、宣言の長さ 10、中身 2 バイト → "not_zip"。ローカルの extra でも同じ（subTest）
def test_data_descriptor_without_signature_passes(self):       # bit 3 のエントリの後ろに、署名のない 12 バイトのデータ記述子（CRC と 2 つの大きさ）→ 合格
def test_data_descriptor_with_signature_passes(self):          # 同じく、署名付きの 16 バイト → 合格
```

ほかの規則で必ず止まる組み合わせ（EOCD の大きさとオフセットの `0xFFFFFFFF`、件数の `0xFFFF`、中央のエントリの `0xFFFFFFFF`）は、小さなファイルでは 1 つだけを破れないので、テストを足さない（主担当の判断。どれかを消しても、隙間と重なりの規則か、中身の長さの規則で `not_zip` になる）。

- [ ] **Step 2: テストが通ることを確かめ、規則を 1 つずつ外して落ちることを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: すべて PASS。次に、上の各テストについて、対応する `_check_layout` の条件を一時的に外して実行し、そのテストが FAIL になることを確かめる（12 バイトの記述子は、`else 12` を `else 16` に変えて確かめる）。確かめたら元に戻す。結果を報告に書く。

- [ ] **Step 3: コミットする**

```bash
git add tests/test_check_workbook.py tests/workbook_factory.py
git commit -m "test: pin each ZIP layout rule that no test covered"
```

<a name="task-17"></a>

### Task 17: 検査（Power Query の部品の中の zip と、展開の合計の上限）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`、`tests/workbook_factory.py`、`README.md`、`README.ja.md`

**Interfaces:**
- Consumes: Task 13 の `_check_part`（外側の部品の展開と合計）、`MAX_TOTAL_UNCOMPRESSED`・`MAX_RATIO`・`RATIO_GRACE_BYTES`・`READ_CHUNK`・`MAX_PARSE_BYTES`・`_DTD_NEEDLES`
- Produces:
  - `MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024`
  - `_mashup_package(raw: bytes) -> bytes | None`: 外側の部品のバイト列から、pyopenvba が展開する中の zip（DataMashup の最初の節）を取り出す。pyopenvba が取り出しに失敗する入力では `None`。
  - `_check_package(package: bytes, total: int) -> tuple[str | None, int]`: 中の zip の部品を展開して数える。不合格の語彙か `None` と、新しい合計を返す。
  - `check()` は、外側の部品をすべて `_check_part` で確かめた後、`_scan_warnings` の前に、名前が `^customXml/item(\d+)\.xml$`（pyopenvba の `_ITEM_PATTERN` と同じ）に合う部品ごとに、次を行う。部品の展開後の大きさが `MAX_PARSE_BYTES` を超えれば `uncompressed_too_large` で不合格。そうでなければ `zf.read` で読み、`_mashup_package` が返したものを `_check_package` に渡す。合計は外側の部品の続きから数える。

取り出しは、pyopenvba 6.6.0 の `powerquery/workbook.py` の `_is_mashup_part`・`_split_item` と `_mashup.py` の `Mashup.parse` と同じ手順にする（xlide と同じものを取り出すため。違えば、中の zip bomb が検査をすり抜ける）。

1. `b"DataMashup"` も `b"D\x00a\x00t\x00a\x00M\x00a\x00s\x00h\x00u\x00p"` も含まなければ `None`。
2. 先頭の 2 バイトが `b"\xff\xfe"` なら `raw.decode("utf-16")`、そうでなければ `raw.decode("utf-8-sig")`。失敗すれば `None`。
3. `re.search(r"(.*<DataMashup[^>]*>)(.*?)(</DataMashup>.*)", text, re.S)`。合わなければ `None`。pyopenvba のルート要素の確かめ（ElementTree）は行わない（行わなくても、検査が数える部品が増えるだけ）。
4. `base64.b64decode(group(2), validate=False)`。`ValueError` なら `None`。
5. 8 バイトより短ければ `None`。4 バイト目から、4 バイトの長さ（リトルエンディアン）と中身の節を 4 つ読む。どれかが終わりを越えるか、4 つ読んだ後に余りがあれば `None`。最初の節を返す。

数え方（pyopenvba の `Package.parse` より広く数える。pyopenvba が例外で止まる所でも、構造が続く限り先を数える）:

| 確かめること | 違えば |
| --- | --- |
| 位置 0 から、`PK\x03\x04` で始まる限りローカルヘッダーをたどる。30 バイトのヘッダーか、データ（位置 + 30 + 名前の長さ + extra の長さ から、圧縮後の大きさの分）が終わりを越えたら、そこでやめる | （やめるだけ） |
| 方式 0: 圧縮後の大きさを合計に足す。方式 8: データを、宣言の展開後の大きさ + 1 バイトまで展開し（pyopenvba の `max_length` と同じ）、実際に出た長さを合計に足す。展開は `READ_CHUNK` ずつ、合計の上限を超えたところで止める。`zlib.error` なら、そこまでの長さを足して次の部品へ。ほかの方式は数えずに次の部品へ | |
| 合計（外側の部品と中の部品の展開の合計）が `MAX_TOTAL_UNCOMPRESSED` を超えない | `uncompressed_too_large` |
| 中の部品の展開した長さが、`RATIO_GRACE_BYTES` を超え、かつ圧縮後の大きさ（0 なら 1）の `MAX_RATIO` 倍を超えない | `compression_ratio_too_high` |
| 中の部品の中身に `_DTD_NEEDLES` がない | `xml_dtd` |

- [ ] **Step 1: 失敗するテストを書く**

`tests/workbook_factory.py` に、`mashup_item(package: bytes, encoding: str = "utf-16") -> bytes` を足す。Excel と同じ包み（`<?xml version="1.0" encoding="utf-16"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">` + base64 + `</DataMashup>`）を、`encoding` が `"utf-16"` なら BOM 付きの UTF-16LE、`"utf-8"` なら BOM なしの UTF-8 で返す。base64 の中身は、版 0、中の zip の節、権限の節（短い XML）、メタデータの節（短い XML）、空の節の 4 つ。中の zip は、正しいものは `zipfile` で作り、宣言の大きさを偽るものは生のローカルヘッダーで作る。

```python
def test_total_limit_is_256_mib(self):                  # check_workbook.MAX_TOTAL_UNCOMPRESSED == 256 * 1024 ** 2
def test_legit_power_query_passes(self):                # 中の zip に短い Formulas/Section1.m → 合格、warnings に "power_query"
def test_mashup_package_bomb_fails(self):               # customXml/item1.xml（UTF-16、BOM 付き）の中の zip に、0 が 1 MiB の deflate の部品 → "compression_ratio_too_high"
def test_mashup_utf8_wrapper_checked(self):             # 同じ中身を UTF-8 の包みで → "compression_ratio_too_high"
def test_mashup_package_total_fails(self):              # MAX_TOTAL_UNCOMPRESSED を 1 MiB に下げる。外側の部品の合計は上限より小さく、中の部品で超える形にする（中の部品は "a" と "b" の乱数列 1 MiB を deflate。圧縮率はおよそ 8 倍で 100 倍以下）→ "uncompressed_too_large"
def test_mashup_package_dtd_fails(self):                # 中の部品に b"<!DOCTYPE x>" → "xml_dtd"
def test_mashup_declared_size_not_trusted(self):        # 中の部品の宣言の展開後の大きさが 0xFFFFFFFF で、実際は 10 バイトに展開される → 合格
def test_mashup_inflation_stops_after_declared_size(self):  # 宣言 1 KiB、実際の流れは 0 が 1 MiB → 展開は 1 KiB + 1 バイトで止まり、合格
def test_mashup_counted_past_unknown_method(self):      # 方式 12 の部品の後ろに、上の bomb の部品 → "compression_ratio_too_high"
def test_mashup_in_other_name_ignored(self):            # customXml/itemA.xml と customXml/item1.xml.bak に同じ bomb → 合格（pyopenvba は読まない）
def test_mashup_item_over_parse_limit_fails(self):      # MAX_PARSE_BYTES を下げ、customXml/item1.xml の展開後の大きさがそれを超える → "uncompressed_too_large"
def test_mashup_bad_base64_ignored(self):               # base64 の部分が 1 文字（復号できない）→ 合格（pyopenvba も展開しない）
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: `test_total_limit_is_256_mib` と、不合格を期待するテストが FAIL。合格を期待するテストは今のコードでも通る見込み。

- [ ] **Step 3: 上限を下げ、`_mashup_package` と `_check_package` を書き、`check()` から呼ぶ**

- [ ] **Step 4: README を直す**

`README.md`・`README.ja.md` の不合格の表: `uncompressed_too_large` を「展開の合計が 256 MB を超える（Power Query の部品の中の zip を含む）。または、`customXml/item<N>.xml` の部品が 32 MB を超える」、`compression_ratio_too_high` を「1 つの部品（Power Query の部品の中の zip の部品を含む）が 100 倍を超えて圧縮されている」にする。

- [ ] **Step 5: テストが通ることを確かめ、規則を 1 つずつ外して落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（sandbox の中では skip 20）。次に、名前の判定、32 MiB の判定、合計の判定、圧縮率の判定、DTD の判定、「宣言 + 1 バイトで止める」を 1 つずつ外し、対応するテストが FAIL になることを確かめて、元に戻す。

- [ ] **Step 6: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py tests/workbook_factory.py
git commit -m "fix: count the package inside Power Query parts and lower the total limit"
git add README.md README.ja.md
git commit -m "docs: describe the Power Query package check and the 256 MB limit"
```

<a name="task-18"></a>

### Task 18: 検査の Seatbelt（ほかのプロセスの情報）と回帰のテスト

**Files:**
- Modify: `scripts/check_workbook.sb`、`tests/test_sandbox_profile.py`

**Interfaces:**
- Consumes: `tests/test_sandbox_profile.py` の `ProfileTest.attempt`・`assertDenied`、`hooks/intake_common.py` の `run_checker`
- Produces: プロファイルの 3 行。テスト 3 件。

`scripts/check_workbook.sb` の、シグナルの規則の後に足す（人の確かめで、2 つを両方入れたときだけ拒否され、検査が動き続けた。[test-report](test-report.md#review-2)）:

```scheme
; No information about other processes, such as their arguments (sysctl kern.procargs2).
(deny process-info*)
(allow process-info* (target self))
(deny sysctl-read (sysctl-name-prefix "kern.procargs"))
```

- [ ] **Step 1: テストを書く**

```python
# tests/test_sandbox_profile.py の ProfileTest
def test_profile_denies_other_process_arguments(self):   # /bin/sleep 60 を起こし（addCleanup で止める）、ctypes の libc.sysctl で (CTL_KERN=1, KERN_PROCARGS2=49, pid) の大きさを問う。0 以外を返したら PermissionError を上げる本文で assertDenied
def test_profile_denies_reading_through_data_volume(self):  # "/System/Volumes/Data" + self.other の実体のパスを読む → assertDenied
# 同じファイルの、本物の run_checker を使うテストの並び（sandbox-exec が要る。REQUIRE の扱いはほかと同じ）
def test_checker_accepts_other_spellings(self):          # NFD で保存した "データ.xlsx" を NFC のパスで、"Book.xlsx" を "book.xlsx" で run_checker → どちらも "pass"
```

- [ ] **Step 2: プロファイルに 3 行を足す**

- [ ] **Step 3: sandbox の中で実行できる範囲を確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS か skip（新しい 3 件は、`sandbox-exec` を入れ子にできないので skip）。今のプロファイルで 1 件目が失敗し、2・3 件目が通ることは、人の確かめで分かっている。人による実行は [Task 19](#task-19) の Step 3 でまとめて行う。

- [ ] **Step 4: コミットする**

```bash
git add scripts/check_workbook.sb tests/test_sandbox_profile.py
git commit -m "fix: hide other processes' arguments from the checker's sandbox"
```

<a name="task-19"></a>

### Task 19: 文書（時間切れの目安、受け入れるリスク）と、人による実行

**Files:**
- Modify: `README.md`、`README.ja.md`、`docs/work/20261124_workbook-intake/test-report.md`

**Interfaces:**
- Consumes: 設計の[受け入れるリスク](design.md#risks)（2026-11-25 に足した 4 つ）
- Produces: 文書だけ。

- [ ] **Step 1: README を直す（英語と日本語）**

- Troubleshooting の `check_timeout`: 「検査が 20 秒を超えた。XML が合計でおよそ 200 MB 以上のブック（大きなシートが多い 50 MB の `.xlsx` など）でなりやすい。検査は読むたびに行う」。
- Limitations:
  - 「Plugin hooks disabled by managed settings」の行を、「`disableAllHooks` はどのスコープの設定（リポジトリの `.claude/settings.json` を含む）でもフックを止めうる（管理設定のフックを除く。プラグインのフックも止まる見込みで、確かめていない）。止まると、メインの会話から xlide を呼べ、入力の確認も検査も効かない。止まっている環境では使わない」に変える。
  - 「VBA のソースは、xlide が上限なしに展開する。マクロのブック（`vba_project` の警告）は、メモリを多く使うことがある」を足す。
  - 「入力の確認は、AskUserQuestion の画面を人が答えることに頼る。ほかのプラグインのフックや SDK のホストが答えを埋める環境では、人の確認なしに記録されうる」を足す。
  - 「xlide は `uvx` を PATH から探して起動する。PATH の先頭に、sandbox から書ける場所を置かない」を足す（`UV_DEFAULT_INDEX` の行の近く）。

- [ ] **Step 2: テストを確かめる**

Run: `"$PY" -B -m unittest tests.test_readme -v`
Expected: PASS。

- [ ] **Step 3: 全体のテストを、人が通常のターミナルで実行する**

Run（人）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS、skip なし（Task 18 の 3 件を含む）。結果を test-report の「自動のテスト」に書く。1 件目（ほかのプロセスの引数）が落ちたら、主担当が Task 18 を開き直す。

- [ ] **Step 4: コミットする**

```bash
git add README.md README.ja.md
git commit -m "docs: add the timeout hint and the newly accepted limitations"
git add docs/work/20261124_workbook-intake/test-report.md
git commit -m "docs: record the Seatbelt run after the second review fixes"
```

その後、[Task 12](#task-12) の Step 1 の続き（3 回目の `/review`）に戻る。

---

<a name="review3-fixes"></a>

## 3 回目の `/review` の指摘の修正（Task 20〜24）

3 回目の `/review` の結果と採否は [test-report](test-report.md#review-3)。根は 2 つある。検査（Command Line Tools の Python 3.9）と xlide（Python 3.15）の標準ライブラリの違いと、pyofficeeditor の独自の XML の読み手と expat の違い。ユーザーの判断（2026-11-26）:

- D1: Power Query の部品の中の zip は、pyopenvba の止まる所をまねるのをやめ、Excel が書かない形をすべて不合格にする。部品名は版に依らない広い形で選び、base64 を戻した全体も DTD を探す。
- D2: `<!-->` のコメントを `strings_not_checked` にし、pyofficeeditor と expat の構文の読み方の違いをほかにも洗い出す。
- D3: xlide の Python を 3.15 に固定する。
- D4: フックの bash を `-p` で動かし、Power Query の中の文字列は確かめないことを文書に正しく書く。

設計は 2026-11-26 の改訂で直した（[design.md の改訂](design.md#revisions)）。語彙は増やさない。

<a name="task-20"></a>

### Task 20: 調査（pyofficeeditor と expat の、XML の構文の読み方の違い）

**Files:**
- Modify: `docs/work/20261124_workbook-intake/research-xlide-parsing.md`（節を 1 つ足す。アンカーは `xml-syntax`）

**Interfaces:**
- Produces: research の表。[Task 21](#task-21) はこの表の「検査の扱い」を実装する。

pyofficeeditor 0.4.1 の XML の読み手（`pyofficeeditor/_xml.py`。xlide の uv の環境、Python 3.15.2）と、検査の expat（Command Line Tools の Python 3.9.6、`_new_parser` と同じ設定）とで、同じバイト列から読む要素・属性・文字が違う構文を洗い出す。分かっているのは、中身が `>` か `->` で始まるコメント（pyofficeeditor は `<!--` の `<` の位置から `-->` を探すので、その場で閉じる）。

- [ ] **Step 1: `_xml.py` を読み、構文ごとに候補を挙げる**

見る構文: コメント、処理命令、CDATA、DOCTYPE、文字参照と実体参照、属性値（引用符、`<`、`>`、改行、空白の正規化）、要素名と属性名に使える文字、終わりのタグの照合、閉じていない要素、ルート要素の前後、XML 宣言、BOM と文字コード、`_consume_until` のような「探し始めの位置」の扱い。

- [ ] **Step 2: 候補ごとに、2 つの読み手で確かめる**

小さな XML を `$TMPDIR` に作り、xlide の環境の python（`-I` で）で pyofficeeditor に読ませた結果と、検査の expat に読ませた結果を並べる。expat がエラーにする形は、今の検査で `strings_not_checked` になるので、違いとして扱わない。

- [ ] **Step 3: research に表を書く**

| 構文の例 | pyofficeeditor が読むもの | expat が読むもの | 検査の扱い |
| --- | --- | --- | --- |

「検査の扱い」は、expat がエラーなく違うものを読む形は `strings_not_checked`、同じに読む形は「なし」とする。根拠の行（`_xml.py:<行>`）を添える。

- [ ] **Step 4: コミットする**

```bash
git add docs/work/20261124_workbook-intake/research-xlide-parsing.md
git commit -m "docs: research where pyofficeeditor and expat read XML differently"
```

<a name="task-21"></a>

### Task 21: 検査（XML の構文の違い）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`、`README.md`、`README.ja.md`

**Interfaces:**
- Consumes: [Task 20](#task-20) の research の表、Task 14 の `_Collector`・`_new_parser`
- Produces: `_Collector.comment(text: str) -> None`。`text` が `">"` か `"->"` で始まれば `self.unchecked = True`。`_new_parser` は `parser.CommentHandler = collector.comment` を設定する。Task 20 の表で「`strings_not_checked`」とした構文ごとに、同じく `unchecked` にする判定を足す。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_comment_closed_early_by_xlide_hides_sheet(self):   # xl/workbook.xml の <sheets> の中に '<!--><sheet name="Two" sheetId="2" state="hidden" r:id="rId2"/>-->' → warnings に "strings_not_checked"
def test_comment_starting_with_dash_gt_marks_unchecked(self):  # '<!--->...-->' の形 → "strings_not_checked"
def test_ordinary_comment_is_fine(self):                     # '<!-- note -->' → "strings_not_checked" なし
# Task 20 の表で strings_not_checked とした構文ごとに 1 件
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: 1 件目と 2 件目、Task 20 の構文のテストが FAIL。3 件目は PASS。

- [ ] **Step 3: 実装する**

- [ ] **Step 4: README を直す**

`README.md`・`README.ja.md` の `strings_not_checked` の行に、「xlide の読み手と XML の構文の読み方が違う部品（`<!-->` で始まるコメントなど）」を足す。

- [ ] **Step 5: テストが通ることを確かめ、判定を外すと落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（sandbox の中では skip あり）。判定を 1 つずつ外して、対応するテストが FAIL になることを確かめる（写しで行い、本物のファイルは変えない）。

- [ ] **Step 6: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py
git commit -m "fix: mark XML parts that xlide's reader parses differently as unchecked"
git add README.md README.ja.md
git commit -m "docs: list XML syntax that xlide reads differently under strings_not_checked"
```

<a name="task-22"></a>

### Task 22: 検査（Power Query の部品の中の zip を、食い違いのない形で数える）

**Files:**
- Modify: `scripts/check_workbook.py`、`tests/test_check_workbook.py`、`tests/workbook_factory.py`、`README.md`、`README.ja.md`

**Interfaces:**
- Consumes: Task 17 の `_mashup_package`・`_check_package_part`・`_check_package`・`check()` の中の部品のループ
- Produces（名前は変えてよいが、振る舞いはこのとおり）:
  - `_ITEM_PATTERN = re.compile(r"^customXml/item[^/]*\.xml$")`。pyopenvba の `^customXml/item(\d+)\.xml$` を、どの Python の版でも含む広い形。
  - `_mashup_blob(raw: bytes) -> tuple[str | None, bytes | None]`: pyopenvba が DataMashup の要素を見つけない部品（印がない、文字として復号できない、正規表現が合わない）は `(None, None)`。見つけたのに base64 が正規の形でなければ `("not_zip", None)`。そうでなければ `(None, 戻した全体)`。
  - `_mashup_sections(blob: bytes) -> list[bytes] | None`: 版の 4 バイトの後の 4 つの節。長さが合わないか、余りがあれば `None`（呼び出し元は `not_zip`）。
  - `_check_package(package: bytes, total: int) -> tuple[str | None, int]`: 下の表の規則で数える。

取り出しの手順 1〜3（印、文字としての復号、正規表現）は Task 17 のまま。その後の規則:

| 確かめること | 違えば |
| --- | --- |
| 正規表現の 2 つ目の組から、空白（` `・`\t`・`\r`・`\n`）を除いた文字列が `[A-Za-z0-9+/]*={0,2}` に合い、長さが 4 の倍数。合えば `base64.b64decode(..., validate=True)` で戻す | `not_zip` |
| 戻した全体が 8 バイト以上で、4 つの節の長さがちょうど合い、余りがない | `not_zip` |
| 戻した全体に `_DTD_NEEDLES` がない（メタデータと権限の節を含む） | `xml_dtd` |
| 戻した全体の大きさを合計に足しても、`MAX_TOTAL_UNCOMPRESSED` を超えない | `uncompressed_too_large` |
| 中の zip: `PK\x03\x04` で始まる限りたどる。ヘッダーかデータが終わりを越えない。方式は格納か deflate。名前が UTF-8 として正しい。格納なら圧縮後と展開後の大きさが等しい。deflate なら、宣言の展開後の大きさ + 1 バイトまで展開して（`zlib.error` なし）、出た長さが宣言とちょうど等しい | `not_zip` |
| 中の zip の部品の展開: 合計・圧縮率・DTD の規則は Task 17 のまま | `uncompressed_too_large`・`compression_ratio_too_high`・`xml_dtd` |

- [ ] **Step 1: 失敗するテストを書き、期待が変わるテストを直す**

```python
def test_mashup_base64_with_inner_padding_fails(self):      # 正しい包みの base64 の先頭を 'QQ==' に替える（3.9 では途中で止まる形）→ "not_zip"
def test_mashup_base64_with_line_breaks_passes(self):       # 正しい base64 を 76 文字ごとに改行 → 合格（power_query）
def test_mashup_newer_unicode_digit_name_counted(self):     # bomb の部品を 'customXml/item\U00016AC0.xml'（UTF-8 の印付き）に置く → "compression_ratio_too_high"
def test_mashup_metadata_dtd_fails(self):                   # メタデータの節に '<!DOCTYPE x>' → "xml_dtd"
def test_mashup_trailing_bytes_after_sections_fail(self):   # 4 つの節の後ろに 1 バイト → "not_zip"
def test_mashup_truncated_entry_fails(self):                # 中の zip の最後の部品のデータを 1 バイト削る → "not_zip"
def test_mashup_zlib_error_fails(self):                     # 中の部品の deflate のデータを壊す → "not_zip"
def test_mashup_size_mismatch_fails(self):                  # 宣言の展開後の大きさを 1 増やす → "not_zip"
def test_mashup_non_utf8_name_fails(self):                  # 中の部品の名前に b"\xff" → "not_zip"
```

Task 17 のテストのうち、期待が変わるもの（ユーザーの判断 D1 による。理由をテストの注釈に書く）:

- `test_mashup_declared_size_not_trusted`（宣言 0xFFFFFFFF、実際は 10 バイト）→ `not_zip`
- `test_mashup_inflation_stops_after_declared_size`（宣言 1 KiB、実際は 0 が 1 MiB）→ `not_zip`
- `test_mashup_counted_past_unknown_method`（方式 12 の部品の後ろに bomb）→ `not_zip`
- `test_mashup_bad_base64_ignored`（base64 が 1 文字）→ `not_zip`。名前を `test_mashup_bad_base64_fails` に変える
- `test_mashup_in_other_name_ignored`: `customXml/itemA.xml` は広い形に合うので bomb で落ちる。`customXml/item1.xml.bak` だけで「読まない」ことを確かめる形に直す

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_check_workbook -v`
Expected: 新しいテストと、期待を変えたテストが FAIL（改行の base64 のテストは PASS の見込み）。

- [ ] **Step 3: 実装する**

`_check_package_part` の説明は、`zlib.error` で不合格にする形に合わせて書き直す。

- [ ] **Step 4: README と設計を直す**

`README.md`・`README.ja.md`:
- `not_zip` の行に「Power Query の部品の中の zip が壊れている（正規の形でない base64、節や部品の長さの食い違い）」を足す。
- `xml_dtd` の行の「Power Query の部品の中にある zip の部品も探す」を「Power Query の部品の中身（中の zip の部品とメタデータ）も探す」にする。
- 警告の `power_query` の行に「クエリの中の文字列（M のコード、クエリ名、説明）は確かめない」を足す。

- [ ] **Step 5: テストが通ることを確かめ、判定を外すと落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（sandbox の中では skip あり）。上の表の判定を 1 つずつ外して、対応するテストが FAIL になることを確かめる（写しで行う）。

- [ ] **Step 6: コミットする**

```bash
git add scripts/check_workbook.py tests/test_check_workbook.py tests/workbook_factory.py
git commit -m "fix: fail Power Query packages that Excel would not write"
git add README.md README.ja.md
git commit -m "docs: describe the stricter Power Query package check"
```

<a name="task-23"></a>

### Task 23: 定義とフック（xlide の Python 3.15、bash の `-p`）

**Files:**
- Modify: `.mcp.json`、`tests/test_manifests.py`、`hooks/hooks.json`、`tests/test_guard_xlide.py`、`README.md`、`README.ja.md`、`docs/runbooks/maintenance.md`

**Interfaces:**
- `.mcp.json` の `args` は、`"--no-config"` の直後に `"--python", "3.15"` を置く。ほかは変えない。`tests/test_manifests.py` の固定（`XLIDE_ARGS` など）も合わせる。
- `hooks/hooks.json` の 2 つの `command` は `/bin/bash -p "${CLAUDE_PLUGIN_ROOT}/hooks/guard-xlide.sh"` と `/bin/bash -p "${CLAUDE_PLUGIN_ROOT}/hooks/record-consent.sh"`。`tests/test_guard_xlide.py` の `ManifestTest` の固定も合わせる。
- `dev/probe/` は確かめのための別のプラグインなので変えない。

- [ ] **Step 1: 固定のテストを先に直し、失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_manifests tests.test_guard_xlide -v`
Expected: 直した固定のテストが FAIL。

- [ ] **Step 2: `.mcp.json` と `hooks/hooks.json` を直す**

- [ ] **Step 3: 文書を直す**

- `README.md`・`README.ja.md` の Requirements: 「xlide は Python 3.15 で動く。手元になければ、uv が初回の起動で取得する（取得できない環境では xlide のツールが見えない）」。README に uvx の引数やフックのコマンドを写している所があれば合わせる。
- `docs/runbooks/maintenance.md`: xlide の Python の版を上げるときは、依存の版を上げるときと同じ確かめ（読み比べと、検査の写しの見直し）を行う、を足す。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v && claude plugin validate . --strict`
Expected: すべて PASS（sandbox の中では skip あり）、通過。

- [ ] **Step 5: コミットする**

```bash
git add .mcp.json tests/test_manifests.py
git commit -m "fix: pin xlide to Python 3.15"
git add hooks/hooks.json tests/test_guard_xlide.py
git commit -m "fix: start the hook wrappers with bash -p"
git add README.md README.ja.md docs/runbooks/maintenance.md
git commit -m "docs: note the Python 3.15 pin and how to raise it"
```

<a name="task-24"></a>

### Task 24: xlide との読み比べと、人による実行（メインの会話で行う）

- [ ] **Step 1: 3 回目の形を、xlide の読み手と読み比べる**

[Task 15](#task-15) の Step 6 と同じやり方で、`tmp/` にブックを作り、検査の結果と、xlide の環境の python（3.15）で pyofficeeditor と pyopenvba に読ませた結果を並べる。形: `<!-->` の中の非表示のシート、`<!-->` の中の不可視の文字、base64 の途中の `=` の中の zip bomb、Unicode の新しい数字の部品名の中の zip bomb、メタデータの節の DTD、Task 20 の表で `strings_not_checked` とした構文。期待: どの形も、検査で不合格になるか、`strings_not_checked` が出る。結果を test-report に書く。

- [ ] **Step 2: 全体のテストを、人が通常のターミナルで実行する**

Run（人）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS、skip なし。結果を test-report に書く。

- [ ] **Step 3: コミットする**

```bash
git add docs/work/20261124_workbook-intake/test-report.md
git commit -m "docs: record the parity check and Seatbelt run after the third review fixes"
```

その後、[Task 12](#task-12) の Step 1 の続き（4 回目の `/review`）に戻る。

<a name="review4-fixes"></a>

## 4 回目の `/review` の指摘の修正（Task 25〜28）

4 回目の `/review` の結果と採否は [test-report](test-report.md#review-4)。最新の差分で検査をすり抜ける形は見つからなかった。ブランチ全体では、数式の計算が上限なくメモリを使う道が見つかった。ユーザーの判断（2026-11-26）:

- D1: 計算を求める呼び出し（`calculate` が `false` でない引数）をフックで拒否し、`xlide_evaluate_formula` を許可リストとエージェントのツールから外す。
- D2: `--python 3.15` のままにし、マイナー版だけの固定であることと、実際の版を確かめる手順を書く。
- D3: 検査が Command Line Tools の expat 2.2.8 に頼ることを、受け入れるリスクと README の制限に書く。
- D4: テストの不足 3 つ（Excel の形の中の zip、設定どおりの `bash -p`、権限と結び付けの節の DTD）を足す。

設計は 2026-11-26 の 2 つ目の改訂で直した（[design.md の改訂](design.md#revisions)）。検査の語彙は増やさない。フックの拒否の理由に `calculation_not_allowed` を足す。

<a name="task-25"></a>

### Task 25: フック（計算を止める）

**Files:**
- Modify: `hooks/guard_xlide.py`、`hooks/allowed-tools.txt`、`agents/excel-analyst.md`、`tests/test_guard_xlide.py`、`README.md`、`README.ja.md`、`docs/runbooks/maintenance.md`
- 計算の機能に触れていれば Modify: `skills/analyze/SKILL.md`

**Interfaces:**
- `decide_detail` は、パスらしい引数の確かめの後、`file_path` の確かめの前に、`tool_input.get("calculate", False) is not False` なら `("deny", "calculation_not_allowed", [])` を返す。値の型は問わない（`"true"`・`1`・`null` も拒否する。xlide の引数の読み手が型を寄せうるため）。
- `hooks/allowed-tools.txt` から `xlide_evaluate_formula file` の行を消す。`reviewed-for:` は変えない。
- `agents/excel-analyst.md` の `tools` から `mcp__plugin_workbook-intake_xlide__xlide_evaluate_formula` を消す（`tests/test_skill_and_agent.py` の `test_agent_tools_match_allowlist` が、許可リストと同じであることを確かめる）。

- [ ] **Step 1: 計算に届くツールを洗い出す**

xlide-mcp 1.2.4 のソース（xlide の uv の環境の `site-packages/xlide_mcp/`）で、許可リストのツールのうち、pyofficeeditor の計算（`book.calculate`・`sheet.evaluate`・`excel/_calc`）に届くものと、その引数を挙げる。分かっているのは `xlide_read_cells` の `calculate` と `xlide_evaluate_formula`。ほかにも届くツールがあれば、実装の前に止めて主担当に報告する。

- [ ] **Step 2: 失敗するテストを書く**

```python
def test_calculate_denied(self):            # extra={"calculate": v} の v = True, "true", 1, None → "calculation_not_allowed"（承認と検査の前に止まる）
def test_calculate_false_passes_on(self):   # extra={"calculate": False} → 今までどおり（承認と検査が済んでいれば allow）
def test_evaluate_formula_not_allowed(self): # tool="xlide_evaluate_formula" → "tool_not_allowed"
```

`test_allowlist_format` の期待から `evaluate_formula` を外す。

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide tests.test_skill_and_agent -v`
Expected: 上の 3 件と、直した `test_allowlist_format` が FAIL。

- [ ] **Step 4: 実装する**

- [ ] **Step 5: 文書を直す**

- `agents/excel-analyst.md`: `xlide_evaluate_formula` に触れる文を消し、`calculate=true` の注意を「再計算はフックが止めるので使わない。セルの値は Excel が最後に保存した結果」にする。
- `README.md`・`README.ja.md`: Troubleshooting に `calculation_not_allowed`（「計算を求める呼び出し（`calculate=true` など）。xlide の計算エンジンは上限なくメモリを使いうるため」）を足す。使い方の注意の「再計算（`calculate=true`）」の文を、「再計算はできない（フックが止める）。セルの値は Excel が最後に保存した結果」にする。
- `docs/runbooks/maintenance.md`: 許可リストの見直しの 3 点に、4 点目「計算エンジン（`book.calculate`・`sheet.evaluate`）に届くか。届くなら、どの引数か」を足す。

- [ ] **Step 6: テストが通ることを確かめ、判定を外すと落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v && claude plugin validate . --strict`
Expected: すべて PASS（sandbox の中では skip あり）、通過。判定を外すと、Step 2 のテストが FAIL になることを写しで確かめる。

- [ ] **Step 7: コミットする**

```bash
git add hooks/guard_xlide.py hooks/allowed-tools.txt agents/excel-analyst.md tests/test_guard_xlide.py
git commit -m "fix: deny formula calculation in the xlide guard"
git add README.md README.ja.md docs/runbooks/maintenance.md   # skills/analyze/SKILL.md を直したら足す
git commit -m "docs: say that recalculation is blocked and why"
```

<a name="task-26"></a>

### Task 26: テストの不足を足す

**Files:**
- Modify: `tests/test_check_workbook.py`、`tests/test_guard_xlide.py`、`tests/test_record_consent.py`、必要なら `tests/workbook_factory.py`

製品のコードは変えない。どのテストも、今のコードで通り、規則を外した写しで落ちることを確かめる（今のコードで正しく動くことは、4 回目の `/review` で手で確かめた）。

- [ ] **Step 1: テストを書く**

```python
# tests/test_check_workbook.py の PowerQueryPackageTest
def test_mashup_excel_like_package_passes(self):   # zipfile で作る中の zip。部品に 8 バイトの extra field（growth hint、id 0xA220）。customXml/itemProps1.xml（DataMashup の schemaRef）も置く → "pass"、"power_query"
def test_mashup_permissions_dtd_fails(self):       # 権限の節（2 つ目）だけに '<!DOCTYPE x>' → "xml_dtd"
def test_mashup_bindings_dtd_fails(self):          # 結び付けの節（4 つ目）だけに '<!DOCTYPE x>' → "xml_dtd"
# tests/test_guard_xlide.py と tests/test_record_consent.py
def test_configured_command_ignores_bash_env(self):  # hooks/hooks.json の command を読み、${CLAUDE_PLUGIN_ROOT} を置き換え、shlex で分けて動かす。BASH_ENV は印のファイルを作るスクリプト → 印はできない。対照として、同じ入力を -p なしの /bin/bash で動かすと印ができることも確かめる
```

- [ ] **Step 2: 通ることと、規則を外した写しで落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS（sandbox の中では skip あり）。写しで、`_check_package` の `+ xlen` を消すと 1 件目が、DTD を探す範囲を `sections[2]` だけにすると 2・3 件目が、`hooks.json` の `-p` を消すと 4 件目が FAIL になる。

- [ ] **Step 3: コミットする**

```bash
git add tests/
git commit -m "test: pin the Excel-shaped package, the DTD search over every section and bash -p"
```

<a name="task-27"></a>

### Task 27: 文書（Python の固定の範囲、検査の expat）

**Files:**
- Modify: `README.md`、`README.ja.md`、`docs/runbooks/maintenance.md`

- [ ] **Step 1: 手順書に、実際の版を確かめる手順を足す**

`docs/runbooks/maintenance.md` の「版を上げる手順」の前に、新しい版を出す前の確かめを足す。プラグインと同じ `uvx` の引数で xlide の環境の python を動かし、`sys.version`・`pyexpat.EXPAT_VERSION`・`unicodedata.unidata_version` を表示するコマンドを書く（実行して、表示されることを確かめる）。調査のときの値（3.15.2、`expat_2.9.0`、17.0.0）と違えば、「版を上げる手順」の読み比べと検査の写しの見直しを行う。uv は、自分で管理する 3.15 があればそれを、なければ PATH の `python3.15` を使うことも書く。

- [ ] **Step 2: README を直す**

- Requirements の Python 3.15 の行に、「固定するのはマイナー版（3.15）だけ。uv が管理する 3.15 か、PATH の `python3.15` を使う」を足す。
- 制限（Limitations）に、「検査は Command Line Tools の Python 3.9.6 と、その expat 2.2.8 で動く。Seatbelt は、乗っ取られた検査の書き込み・通信・実行を止めるが、判定そのものは守らない。文字コードの厳密な復号、DTD の拒否、1 部品 32 MB の上限で、届く面を狭くしている」を足す。

- [ ] **Step 3: 確かめてコミットする**

Run: `"$PY" -B -m unittest discover -s tests -t . && claude plugin validate . --strict`
Expected: すべて PASS、通過。

```bash
git add README.md README.ja.md docs/runbooks/maintenance.md
git commit -m "docs: describe the Python pin scope and the checker's expat"
```

<a name="task-28"></a>

### Task 28: 人による実行（メインの会話で行う）

- [ ] **Step 1: 全体のテストを、人が通常のターミナルで実行する**

Run（人）: `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`
Expected: すべて PASS、skip なし。結果を test-report に書く。

- [ ] **Step 2: コミットする**

```bash
git add docs/work/20261124_workbook-intake/test-report.md
git commit -m "docs: record the Seatbelt run after the fourth review fixes"
```

その後、[Task 12](#task-12) の Step 1 の続き（5 回目の `/review`）に戻る。

<a name="review5-fixes"></a>

## 5 回目の `/review` の指摘の修正（Task 29〜32）

5 回目の `/review` の結果と採否は [test-report](test-report.md#review-5)。計算エンジンへの道はすべて閉じていた。ほかに、ファイルの中身だけで xlide が多くの時間やメモリを使う形が、残る 17 のツールで見つかった。ユーザーの判断（2026-11-26）:

- D1: 最も重い `xlide_analyze` と、使い道のなくなる `xlide_rules` を外し、`is_regex` が `false` でない呼び出しを拒否する。残りの形は、測った値と一緒に受け入れるリスクと README に書き、runbook に確かめを足す。
- D2: 固定しない下の依存のことを README に書く。
- D3: xlide が読めない `.xltx`・`.xltm` を受け付けない。
- D4: スキルは名前を付けずにエージェントを起動し、README にエージェントのチームを切った前提であることを書く。runbook の、通常のターミナルでのテストの実行は、きれいな複製で行う。

設計は 2026-11-26 の 3 つ目の改訂で直した（[design.md の改訂](design.md#revisions)）。検査の語彙は増やさない。フックの拒否の理由に `regex_not_allowed` を足す。

<a name="task-29"></a>

### Task 29: フック（`xlide_analyze`・`xlide_rules` を外し、正規表現の検索を止める）

**Files:**
- Modify: `hooks/guard_xlide.py`、`hooks/allowed-tools.txt`、`agents/excel-analyst.md`、`tests/test_guard_xlide.py`、`README.md`、`README.ja.md`、`skills/analyze/SKILL.md`、`docs/runbooks/maintenance.md`

**Interfaces:**
- `decide_detail` は、`calculate` の確かめのすぐ後に、`tool_input.get("is_regex", False) is not False` なら `("deny", "regex_not_allowed", [])` を返す。値の型は問わない。
- `hooks/allowed-tools.txt` から `xlide_analyze file` と `xlide_rules nofile` の行を消す。`reviewed-for:` は変えない。
- `agents/excel-analyst.md` の `tools` から 2 つを消し、読む順の 6 番目を「モジュールの一覧 → 手続きの一覧 → 要るモジュールの本文」にする。

- [ ] **Step 1: ほかに届く道がないことを確かめる**

xlide-mcp 1.2.4 のソースで、残る許可リストのツールのうち、pyvbaanalysis の `analyze_project`（条件付きコンパイルの評価）に届くものと、呼び出し元の文字列を正規表現として使う引数を挙げる。分かっているのは `xlide_analyze` と、`xlide_search_modules` の `is_regex`。ほかにあれば、実装の前に止めて主担当に報告する。

- [ ] **Step 2: 失敗するテストを書く**

```python
def test_regex_denied(self):            # extra={"is_regex": v} の v = True, "true", 1, None → "regex_not_allowed"（承認と検査の前に止まる）
def test_regex_false_passes_on(self):   # extra={"is_regex": False} → 今までどおり
def test_analyze_not_allowed(self):     # tool="xlide_analyze" → "tool_not_allowed"
def test_rules_not_allowed(self):       # tool="xlide_rules"（file_path なし）→ "tool_not_allowed"
```

`test_allowlist_format` の期待から `analyze` と `rules` を外す。

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `"$PY" -B -m unittest tests.test_guard_xlide tests.test_skill_and_agent -v`
Expected: 上の 4 件と、直した `test_allowlist_format` が FAIL（`test_regex_false_passes_on` は PASS の見込み）。

- [ ] **Step 4: 実装する**

- [ ] **Step 5: 文書を直す**

- `README.md`・`README.ja.md`: Troubleshooting に `regex_not_allowed`（「正規表現の検索を求める呼び出し（`is_regex=true`）。xlide は渡された正規表現を時間の上限なしに当てるため」）を足す。使い方の注意 4 に、「VBA の静的な解析と正規表現の検索も使えない（フックが止める）」を足す。
- `skills/analyze/SKILL.md`: 拒否の理由の一覧に `regex_not_allowed` を足す（`calculation_not_allowed` の次）。
- `docs/runbooks/maintenance.md`: 許可リストの見直しの 4 点目に、pyvbaanalysis の条件付きコンパイルの評価（`analyze_project`）を足し、1.2.4 で外したツールに `xlide_analyze` を足す。5 点目「1 回の呼び出しの手間が、ファイルの中身に対して線形より速く増えないか（要素ごとに頭から探す、セルごとに導き直す、呼び出し元が渡す正規表現など）」を足す。

- [ ] **Step 6: テストが通ることを確かめ、判定を外すと落ちることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v && claude plugin validate . --strict`
Expected: すべて PASS（sandbox の中では skip あり）、通過。判定を外すと、Step 2 の拒否のテストが FAIL になることを写しで確かめる。

- [ ] **Step 7: コミットする**

1 つ目のコミット（タイトル `fix: remove xlide_analyze and deny regular-expression search`）: `hooks/guard_xlide.py`・`hooks/allowed-tools.txt`・`agents/excel-analyst.md`・`tests/test_guard_xlide.py`。
2 つ目のコミット（タイトル `docs: describe the tools removed for unbounded resource use`）: `README.md`・`README.ja.md`・`skills/analyze/SKILL.md`・`docs/runbooks/maintenance.md`。

<a name="task-30"></a>

### Task 30: 検査とフック（テンプレートを受け付けない）

**Files:**
- Modify: `hooks/intake_common.py`、`scripts/check_workbook.py`、`tests/test_check_workbook.py`、`tests/test_guard_xlide.py`、`tests/test_record_consent.py`（拡張子の期待がある所だけ）、`README.md`、`README.ja.md`

**Interfaces:**
- 2 か所の `SUPPORTED_EXTENSIONS` を `(".xlsx", ".xlsm", ".xlam", ".xlsb")` にする（2 つが同じであることは、既存のテストが確かめる）。

- [ ] **Step 1: 失敗するテストを書く**

```python
# 検査: test_unsupported_extension_fails の名前の組に ".xltx" と ".xltm" を足す → "unsupported_extension"
# フックと承認の記録: .xltx と .xltm のファイル → "unsupported_extension"
```

- [ ] **Step 2: テストが失敗することを確かめ、実装し、通ることを確かめる**

Run: `"$PY" -B -m unittest discover -s tests -t . -v`
Expected: 実装の前は新しい期待が FAIL、実装の後はすべて PASS（sandbox の中では skip あり）。

- [ ] **Step 3: README を直す**

使い方の 1 の拡張子の一覧から `.xltx`・`.xltm` を外し、「テンプレート（`.xltx`・`.xltm`）は、Excel で `.xlsx` か `.xlsm` に保存し直してから置く（xlide がテンプレートを読めないため）」を足す。

- [ ] **Step 4: コミットする**

1 つ目のコミット（タイトル `fix: stop accepting Excel templates, which xlide cannot read`）: `hooks/intake_common.py`・`scripts/check_workbook.py`・`tests/`。
2 つ目のコミット（タイトル `docs: ask for templates to be saved as workbooks first`）: `README.md`・`README.ja.md`。

<a name="task-31"></a>

### Task 31: 文書（残る資源のリスク、エージェントのチーム、下の依存、きれいな複製での実行）

**Files:**
- Modify: `README.md`、`README.ja.md`、`skills/analyze/SKILL.md`、`docs/runbooks/maintenance.md`

- [ ] **Step 1: README の制限（Limitations）に足す**

- 細工したファイルで、xlide が多くの時間やメモリを使いうる。例（[test-report](../work/20261124_workbook-intake/test-report.md#review-5) の測った値）: 長い共有数式を読む、1 行に大量のセルがある、クエリが数千件ある、VBA の行の継続が多い。xlide は sandbox の外で動き、メモリの上限がない。重くなったら Claude Code を止め、xlide のプロセスを終える。最も重い形（計算、VBA の静的な解析、正規表現の検索）はフックが止める。
- エージェントのチーム（実験的な機能、`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`）を切った前提である。有効にすると、ブックを読むエージェントがほかの仲間に直接話しかけられうる。
- `.mcp.json` が固定するのは xlide-mcp と 4 つの依存だけで、ほかの依存は初回の起動のときの最新を取る（下の依存のセキュリティの修正を受け取るため）。保守（Maintenance）の節の「版を固定している」の文にも同じことを書く。

- [ ] **Step 2: スキルを直す**

`skills/analyze/SKILL.md` の `workbook-intake:excel-analyst` を起動する文に、「名前（name）を付けずに起動する。名前を付けると、エージェントのチームの一員として起動しうるため」を足す。

- [ ] **Step 3: runbook を直す**

`docs/runbooks/maintenance.md` の、通常のターミナルで全体のテストを動かすコマンドを、確かめたコミットのきれいな複製で動かす形にする（追跡していないファイルや `__pycache__` を、sandbox の外で読み込ませないため）。手順: `mktemp -d` で空のディレクトリを作る → `git clone -q --no-local <repo>` でそこに複製する → 複製の中で `git checkout -q <確かめたコミット>` → `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v`。1 行のコマンドにして書く。

- [ ] **Step 4: 確かめてコミットする**

Run: `"$PY" -B -m unittest discover -s tests -t . && claude plugin validate . --strict`
Expected: すべて PASS、通過。

コミット（タイトル `docs: record the remaining resource risks, agent teams and unpinned dependencies`）: `README.md`・`README.ja.md`・`skills/analyze/SKILL.md`・`docs/runbooks/maintenance.md`。

<a name="task-32"></a>

### Task 32: 人による実行（メインの会話で行う）

- [ ] **Step 1: 全体のテストを、人がきれいな複製で実行する**

Run（人）: [Task 31](#task-31) の Step 3 で runbook に書いたコマンド（`<repo>` はこのリポジトリ、`<確かめたコミット>` は Task 31 の後の HEAD）
Expected: すべて PASS、skip なし。結果を test-report に書く。

- [ ] **Step 2: コミットする**

コミット（タイトル `docs: record the Seatbelt run after the fifth review fixes`）: `docs/work/20261124_workbook-intake/test-report.md`。

その後、[Task 12](#task-12) の Step 1 の続き（6 回目の `/review`）に戻る。
