---
status: in-progress
created: 2026-11-25
---

# workbook-intake: 試験の記録

<a name="related"></a>

## 関連

- 設計: [design.md の完了条件](design.md#done)
- 計画: [plan.md の Task 11](plan.md#task-11)・[Task 12](plan.md#task-12)
- 実装の最初の確認: [research-plugin-behavior.md](research-plugin-behavior.md)

<a name="automated"></a>

## 自動のテスト

| いつ | どこで | コマンド | 結果 |
| --- | --- | --- | --- |
| 2026-11-25、`719943d` | 人、通常のターミナル | `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v` | 191 件、すべて OK、skip なし。Seatbelt のプロファイルの確かめ（ネットワーク・書き込み・exec・fork・ほかのファイルの読み込み・リンク・UNIX ソケットの拒否）、本物の検査を使うフックのテスト、承認のフックの入口からの通しのテストを含む |
| 2026-11-25、`d093bcb` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 217 件、OK、skip 20（`sandbox-exec` を入れ子にできないため） |
| 2026-11-25、`d093bcb` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-25、`d093bcb` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-25、`f88e6dd` | 人、通常のターミナル | `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v` | 286 件、すべて OK、skip なし |
| 2026-11-25、`f88e6dd` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 286 件、OK、skip 20 |
| 2026-11-25、`f88e6dd` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-25、`f88e6dd` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`265e864` | 人、通常のターミナル | `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v` | 313 件、すべて OK、skip なし。2 回目の `/review` の修正（[Task 16〜19](plan.md#review2-fixes)）の後。ほかのプロセスの引数を読めないこと、`/System/Volumes/Data` を通して読めないこと、NFD と大文字小文字の違う綴りで検査が通ることの 3 件を含む |
| 2026-11-26、`265e864` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 313 件、OK、skip 23 |
| 2026-11-26、`265e864` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`265e864` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`794058e` | 人、通常のターミナル | `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v` | 328 件、すべて OK、skip なし。3 回目の `/review` の修正（[Task 20〜23](plan.md#review3-fixes)）の後 |
| 2026-11-26、`794058e` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 328 件、OK、skip 23。3 回目の `/review` の修正（[Task 20〜23](plan.md#review3-fixes)）の後 |
| 2026-11-26、`794058e` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`794058e` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`1e9e08c` | 人、通常のターミナル | `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t . -v` | 338 件、すべて OK、skip なし。4 回目の `/review` の修正（[Task 25〜27](plan.md#review4-fixes)）の後。計算の拒否と、設定どおりの `bash -p` のテストを含む |
| 2026-11-26、`1e9e08c` | 人、通常のターミナル | [runbook の Python の版の確かめ](../../runbooks/maintenance.md#preflight)の `uvx ... python -c ...` | `3.15.2 expat_2.9.0 17.0.0`。調査のときの値と同じ |
| 2026-11-26、`1e9e08c` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 338 件、OK、skip 23 |
| 2026-11-26、`1e9e08c` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`1e9e08c` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`6c3d42c` | 人、通常のターミナル（確かめたコミットのきれいな複製） | [runbook のコマンド](../../runbooks/maintenance.md)（`git clone --no-local` → `git checkout 6c3d42c` → `WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 ... unittest discover -s tests -t . -v`） | 344 件、すべて OK、skip なし。5 回目の `/review` の修正（[Task 29〜31](plan.md#review5-fixes)）の後。正規表現の拒否、外したツール、テンプレートの拒否のテストを含む |
| 2026-11-26、`6c3d42c` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 344 件、OK、skip 23 |
| 2026-11-26、`6c3d42c` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`6c3d42c` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`ec6a1ee` | 人、通常のターミナル（確かめたコミットのきれいな複製。完全な SHA で取り出した） | [runbook のコマンド](../../runbooks/maintenance.md) | 349 件、すべて OK、skip なし。6 回目の `/review` の修正（[Task 33](plan.md#task-33)）の後。長い `query`・エージェントのチーム・広げた matcher のテストを含む |
| 2026-11-26、`ec6a1ee` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 349 件、OK、skip 23 |
| 2026-11-26、`ec6a1ee` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`ec6a1ee` | 同上 | `claude plugin validate . --strict` | 通過 |
| 2026-11-26、`2988832` | 人、通常のターミナル（確かめたコミットのきれいな複製。完全な SHA で取り出した） | [runbook のコマンド](../../runbooks/maintenance.md) | 351 件、すべて OK、skip なし。7 回目の `/review` の修正（[Task 35](plan.md#task-35)）の後。スキルの確かめの順序、どのツールでもエージェントのチームを拒否すること、`re.search` での matcher のテストを含む |
| 2026-11-26、`2988832` | Claude Code の Bash（sandbox の中） | `"$(xcode-select -p)/usr/bin/python3" -B -m unittest discover -s tests -t .` | 351 件、OK、skip 23 |
| 2026-11-26、`2988832` | 同上 | `shellcheck hooks/*.sh scripts/*.sh dev/probe/workbook-intake/hooks/*.sh` | 指摘なし |
| 2026-11-26、`2988832` | 同上 | `claude plugin validate . --strict` | 通過 |

`719943d` から `d093bcb` までに、Seatbelt・フック・検査のコードとそのテスト（`hooks/`、`scripts/check_workbook.*`、`tests/test_sandbox_profile.py`、`tests/test_guard_xlide.py`、`tests/test_record_consent.py`、`tests/test_check_workbook.py`）は変わっていない（`git diff --stat` で確かめた）。そのため、`d093bcb` では人による Seatbelt 付きの実行をやり直していない。`f88e6dd` では、1 回目の `/review` を受けて検査とフックを直したので（[Task 13〜15](plan.md#task-13)）、やり直した。CI（Linux と macOS）の結果は、PR を作った後に足す。

<a name="manual"></a>

## 実機での確認

- 環境: macOS 26.7.1、Claude Code 2.1.331、xlide-mcp 1.2.4（uvx が Python 3.15.2 を用意）。プラグインは、作業用のディレクトリに、このリポジトリをマーケットプレイスとして `--scope local` で入れた。
- 推奨設定は `--settings` で足した（`sandbox.filesystem.denyRead: ["~/workbook-intake"]`、`permissions.deny: ["Read(~/workbook-intake/**)"]`、`sandbox.allowUnsandboxedCommands: false`）。
- ブック: 人が Excel で作った `Book2.xlsx` と、テスト用に作った 3 つ（検査に通るもの、非表示のシートがあるもの、zip bomb）。
- 結果は、人の控えと、各セッションの記録（`~/.claude/projects/` の下。コミットしない）から読んだ。

| 完了条件 | 頼んだこと | 期待 | 結果 |
| --- | --- | --- | --- |
| メインの会話から xlide のツールを呼ぶと止まる | `xlide_doctor` をメインの会話から呼ぶ | 拒否 | `workbook-intake: wrong_caller` で拒否 |
| 入力の確認を承認していないファイルは止まる | 承認の前に、excel-analyst に `xlide_list_sheets` を呼ばせる | 拒否 | `no_consent` で拒否 |
| 承認した後は、受け取り用フォルダの中の、検査に通るファイルを読める。読むたびの確認は出ない | スキルで `Book2.xlsx` を解析する | 読める | 入力の確認の後、`consent=recorded; check=pass; failures=none; warnings=none` が返り、excel-analyst が読んで要約した。xlide のツールの許可を求める画面は、人の控えにない |
| 前提が足りない環境では、スキルの最初で止まる | PATH から uvx を外して起動し、解析を頼む | 止まる | `missing uvx` で止まった（xlide のサーバーも接続できなかった） |
| 受け取り用フォルダの外のファイルは止まる | リポジトリの中のブックを excel-analyst に渡す | 拒否 | `outside_intake` で拒否 |
| zip bomb は xlide に届く前に止まる | スキルで zip bomb を解析し、続けて excel-analyst に直接呼ばせる | 止まる | 承認の後に `check=fail; failures=compression_ratio_too_high` でスキルが止まり、直接の呼び出しも `check_failed (compression_ratio_too_high)` で拒否 |
| 許可リストの外のツール（書き込み用）は止まる | `xlide_write_cells` をメインの会話から呼ぶ | 拒否 | `tool_not_allowed` で拒否（引数の不足のエラーより前に止まった） |
| プロジェクトの `.mcp.json` の xlide は止まる | 別名（`xlide-project`）で定義した xlide の `xlide_doctor` を呼ぶ | 拒否 | `not_plugin_server` で拒否。引数が違うので、プラグインの xlide と両方が `/mcp` に出た |
| 推奨設定のもとで、Bash で読もうとすると失敗する | `unzip -l <受け取り用フォルダのブック>` | 失敗 | 終了コード 9（`cannot find or open`）。Claude は別の経路を試さなかった |
| 推奨設定がない環境では、スキルの最初で止まる | 推奨設定なしで解析を頼む | 止まる | `missing intake_dir_protected` で止まり、必須の設定を示した |
| 警告があるファイルは、警告の確認を承認しないと読めない | 非表示のシートのブックで、入力の確認は承認し、警告の確認で「やめる」を選び、excel-analyst に直接呼ばせる | 拒否 | `warnings_ack=not_recorded; reason=not_confirmed` の後、`warnings_not_acknowledged (hidden_sheet)` で拒否。別のセッションで「続ける」を選ぶと読めた |

ほかに分かったこと:

- excel-analyst の `xlide_doctor` は、`read_only: true`、ルートが受け取り用フォルダ 1 件だけ、`paths_outside_roots_allowed: false` を毎回返した。ルートは `doctor.sh` の `folder` の行と一致した。
- excel-analyst は、`xlide_doctor` による事前の確認を、呼ばれ方によって省くことがあった。守りはフック（受け取り用フォルダの判定）と xlide 自身のルートの判定が担うので、事前の確認は念のための層にとどまる。
- サブエージェントが「`xl/workbook.xml` を別の方法で直接読む」ことを提案したが、メインの会話はスキルの決まりを理由に断った。
- テスト用に作った非表示のシートのブックでは、`xlide_read_cells` が xlide のエラーで失敗した（フックの拒否ではない）。表示されているシートが 1 枚もない、スクリプトで作ったブックのためと見ている（推測）。
- 拒否の理由は「README の Troubleshooting を参照」と示すが、Claude は README の場所を知らず、`~/.claude/plugins` を探そうとした。人が止めた。
- uvx が起動できずに xlide の接続に失敗すると、Claude Code はその失敗をしばらく覚えていて、再接続しない（Claude の表示では約 15 分）。
- 同じセッションで、一度「続ける」を選んだファイルは、後で「やめる」を選んでも、前の警告の確認の記録が残る（記録は追記のみのため。設計からの推論で、この確認では試していない）。スキルは「やめる」で止まるので、スキルを通る使い方では読まれない。
- チームが有効なときだけ見えるツール（2026-11-26、[Task 37](plan.md#task-37)）: Claude Code 2.1.332 の本体を、起動せずに固定の文字列（`TeamCreate`、`TeamDelete`、`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`、`"--agent-teams"`、`team_name`）で探した。チームの判定は `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` か `process.argv.includes("--agent-teams")` に、機能の切り替え（`tengu_amber_flint`、既定は有効）を重ねたものだった。`TeamCreate`・`TeamDelete` は、ツールの定義にはなく、警告を省く名前の一覧（`Frame`・`BashOutput` などと並ぶ）にだけあった（UTF-16 でも探した）。調べた範囲（この判定を取り込むモジュールの 53 か所の呼び出し。別名で書き出した先や、環境変数を直接読むほかの箇所はたどっていない）では、この判定で変わるのは、Agent ツールの `name`・`team_name`・`mode` と、ExitPlanMode の `launchSwarm`・`teammateCount` の引数（切れているときはスキーマから外す）、SendMessage の入力の形、添付、TaskCreate・TaskList などの説明の文だった。実際に見たのは、チームが切れている側だけ（サブエージェントとして動いた、このセッションのツールの一覧。後から読み込むツールの一覧を含む）で、`TeamCreate`・`TeamDelete` はなく、Agent ツールに `name` はなかった。チームが有効な側で引数が残ることは、コードを読んで推したもので、動かしては確かめていない。ツールの手がかりは確かめられなかったので、スキルの文を消し、同じ判定で外される Agent ツールの `name`・`team_name` の引数を手がかりにした（ユーザーの判断 D4）。

<a name="reviews"></a>

## レビュー

<a name="review-1"></a>

### /review（1 回目、`53c4d7d`）

gstack の `/review` で、専門のレビュアー 6 つ（Testing、Maintainability、Security、Performance、Simplification、State Machines）、Red Team、Claude の敵対的な確認を出した。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。

検査と xlide（pyofficeeditor 0.4.1）の読み方の違いで、検査を外せることが分かった。どれも、無害な中身のファイルで、検査の結果と xlide 1.2.4 の読み込みの結果を比べて再現した。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 重大 | `scripts/check_workbook.py` | 中央ディレクトリが 2 つある zip で、検査（標準ライブラリの `zipfile`）と xlide が別の部品の組を読む。検査は合格・警告なしで、xlide は非表示のシートを読んだ。zip bomb の不合格も外れる | 直す |
| 重大 | `scripts/check_workbook.py` | 先頭に `<` 以外がある部品（1 バイトでも、4 KB を超える空白でも）を、XML と見なさずに読み飛ばし、`strings_not_checked` も付けない。xlide は最初の `<` の前を飛ばして読む | 直す |
| 重大 | `scripts/check_workbook.py` | 関係の Target の `\` を解決できず、シートの状態を数えない。xlide は `/` に直して読む | 直す |
| 重大 | `scripts/check_workbook.py` | `customXml/` の下の部品を、名前だけで文字列の検査から外す。関係でブックの本体をそこに置ける | 直す |
| 重大 | `hooks/guard_xlide.py` | 正規形でない `file_path` を通す。xlide は前後の空白を取ってから開くので、末尾に空白のあるリンクで、検査したものと別のファイルを読ませられる | 直す |
| 軽微 | `scripts/check_workbook.py` | NFKC を文字列全体に掛ける。32 MB の文字列 1 つで、ピーク 1.9 GB、5.9 秒（測った） | 直す |
| 軽微 | `tests/test_record_consent.py` | 警告の確認の質問に一覧の部分がない場合（`question_mismatch`）のテストがない | 直す |
| 軽微 | `scripts/doctor.sh` | doctor は python3 があれば `ok` と出すが、検査は python が root の持ち物でないと `error` にする | 直す |
| 軽微 | マニフェスト、スキル、README、runbook | 説明文が保証に読める。拒否の理由の一覧の誤り（`file_changed` があり、`python_missing` がない）。xlide の MCP のリソースを確かめる手順がない（1.2.4 は固定の 2 つだけで、ブックの中身は返さない） | 直した（`be03451`） |
| 軽微 | フック、承認の記録、マニフェスト | `DEVELOPER_DIR`、承認を取り消せないこと、古い Claude Code、エージェントの名前 | 直さない。設計の[受け入れるリスク](design.md#risks)に足した |
| 提案 | `hooks/guard_xlide.py`、`hooks/intake_common.py` | `decide()` と `consent_question()` の薄い包みを消す | 直さない（plan でテストの入口に決めている） |

直さないと判断したもの（主担当の判断）:

- 大きなブックで 20 秒を超える（部品ごとの読み込みの上限、二度の展開）: 時間切れは拒否する設計なので、安全の側に倒れる。
- 下の依存を固定していない: 設計の[更新と保守](design.md#maintenance)で決めている。
- 検査の後の差し替え（TOCTOU）: 設計の[受け入れるリスク](design.md#risks)にある。

直すものの方針は、[plan.md の Task 13](plan.md#task-13) に書く。

<a name="parity"></a>

### xlide の読み手との読み比べ（`f88e6dd`）

[Task 15 の Step 6](plan.md#task-15)。1 回目の `/review` と[調査](research-xlide-parsing.md)で、検査と xlide 1.2.4 の読み方が食い違った形ごとに、ブックを 1 つずつ作った。どのブックも、veryHidden のシートか、`ignore previous` という句のどちらか 1 つを隠している。各ブックを、検査（Command Line Tools の python3）と、xlide 1.2.4 の uv の環境の python（`xlide_mcp.cells` の `sheets()` と `read()`）で読んだ。読み比べのスクリプトとブックは `tmp/parity/` に置き、コミットしていない。

| 形 | 検査の結果 | xlide 1.2.4 が読んだもの |
| --- | --- | --- |
| 基準（隠したシートだけ） | 合格、`very_hidden_sheet` | 非表示のシート |
| 中央ディレクトリが 2 つ | 不合格、`not_zip` | 非表示のシート（EOCD の位置どおりに読む、前の中央ディレクトリの組） |
| `xl/workbook.xml` の先頭に 1 バイト | 合格、`strings_not_checked` | 非表示のシート |
| 関係の Target に `\` | 合格、`very_hidden_sheet` | 非表示のシート |
| ブックの本体を `customXml/` に置く | 合格、`very_hidden_sheet` | 非表示のシート |
| 関係に `xmlns:Target` の属性 | 合格、`very_hidden_sheet`・`strings_not_checked` | 非表示のシート（`xl/other.xml` を本体として読む） |
| `x:state="hidden"`（接頭辞付き） | 合格、`hidden_sheet` | 非表示のシート |
| 共有文字列に `_x200B_` | 合格、`invisible_characters` | ゼロ幅スペースを含む文字列 |
| 句をリッチテキストの 2 つの run に分ける | 合格、`instruction_like_text` | 句 |
| `_xHHHH_` を run の境目で分ける | 合格、`instruction_like_text` | 句 |
| `t` の中に子の要素を入れて句を分ける | 合格、`instruction_like_text` | 句 |

- どの形も、期待のとおり、検査で不合格になるか、xlide が読むものに合う警告か `strings_not_checked` が出た。
- シートを隠したブックでは、xlide の `read()` が `ValueError` で失敗した。これらのブックには共有文字列の関係がないためで、読み比べの結論には関わらない。

<a name="review-2"></a>

### /review（2 回目、`b218361`）

ブランチ全体を、gstack の `/review` でもう一度見た。SDD の最終レビューを兼ねる。専門のレビュアー 6 つ（Testing、Maintainability、Security、Performance、Simplification、State Machines）、Red Team、Claude の敵対的なパスを出した。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした（Task 12 の Step 3）。Security と State Machines は指摘なし。QA の確かめ（検査の成功の場合、中央ディレクトリが 2 つの場合、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 重大 | `scripts/check_workbook.py` | Power Query の部品の中の zip を、xlide（pyopenvba の `Package.parse`）はヘッダーの宣言の大きさ（最大 4 GiB）まで展開し、部品の数にも上限がない。検査は外側の zip しか数えない。人に見えるのは、正規のブックと同じ `power_query` の警告だけ（ソースで確かめた） | 直す（[Task 17](plan.md#task-17)） |
| 重大 | `hooks/guard-xlide.sh`、`hooks/record-consent.sh` | `xcode-select` は絶対パスなのに、`dirname` を PATH から探す。PATH の先頭に sandbox から書ける場所があると、そこに置かれたコマンドが sandbox の外で動く（テストで再現した） | 直した（`25108c0`。PATH を `/usr/bin:/bin` に固定） |
| 軽微 | `scripts/check_workbook.py` | 32 MiB を超える XML の部品は `strings_not_checked` だけで通り、xlide は XML の約 31 倍のメモリを使う（31 MB の XML で 1,038 MB を計測） | 直す（[Task 17](plan.md#task-17)。合計の上限を 256 MiB に下げる） |
| 軽微 | `scripts/check_workbook.py` | VBA のソースの圧縮（MS-OVBA）は、xlide が上限なしに展開する（数百倍、推測） | 直さない。設計の[受け入れるリスク](design.md#risks)に足した |
| 軽微 | `scripts/check_workbook.sb` | `(allow default)` のため、ほかのプロセスの引数を `kern.procargs2` で読める（下の確かめで再現） | 直す（[Task 18](plan.md#task-18)） |
| 軽微 | `scripts/check_workbook.py` | `_check_layout` の規則のうち、消してもテストが落ちないものがある（台帳の先送りの行 157） | 直す（[Task 16](plan.md#task-16)） |
| 軽微 | `scripts/check_workbook.py` | XML の読み込みは約 10 MB/秒。XML が合計 310 MB のブック（50.8 MB の `.xlsx`）は 32 秒かかり、`check_timeout` で拒否される。呼び出しのたびに検査し直す | README に目安を書く（[Task 19](plan.md#task-19)）。結果の使い回しは設計の非目標のまま |
| 軽微 | 設計、README | すべてのスコープの `disableAllHooks` でフックが止まりうる。ほかのプラグインのフックが AskUserQuestion の答えを埋めうる。`uvx` を PATH から探す | 設計の[受け入れるリスク](design.md#risks)に足した。README は [Task 19](plan.md#task-19) |
| 軽微 | README、`hooks/intake_common.py`、`scripts/doctor.sh` | `path_not_canonical` の 2 つの行の食い違いと言い過ぎ、`very_long_string` の言い過ぎ、`xml_dtd` がすべての部品に効くこと（SVG の画像や HTML を書き出すマクロでも出る）、doctor が `xcode-select` を PATH から探すこと | 直した（`fe3b14c`、`e4ad15b`） |
| 提案 | `hooks/intake_common.py`、`scripts/check_workbook.py` | 使われない `open_pipe` を消す。`_check_part` の dict を `nonlocal` にする | 直さない（ユーザーの判断） |

Seatbelt に関わる 3 つは、Claude の sandbox の中では `sandbox-exec` を入れ子にできないので、人が通常のターミナルで確かめのスクリプト（`tmp/probe2/probe.py`。コミットしない）を実行した（2026-11-25、`25108c0`）。

| 指摘 | 確かめたこと | 結果 | 判断 |
| --- | --- | --- | --- |
| パスの綴り（Red Team と敵対的なパスの両方） | NFD で保存した `データ.xlsx` を NFC のパスで、`Book.xlsx` を `book.xlsx` で検査する | 4 通りとも `pass`（カーネルが返すパスは入力と違うが、Seatbelt は通した） | 直さない。回帰のテストを足す（[Task 18](plan.md#task-18)） |
| `/System/Volumes/Data` を通した読み込み | 検査の Seatbelt の中から、`/System/Volumes/Data` + 一時ファイルの実体のパスを読む | 拒否された | 直さない。回帰のテストを足す（[Task 18](plan.md#task-18)） |
| ほかのプロセスの情報 | 検査の Seatbelt の中から、別のプロセス（`/bin/sleep`）の `kern.procargs2` を読む | 読めた（引数。環境変数の印は出なかった）。`process-info*` の拒否と `kern.procargs` の `sysctl-read` の拒否を両方入れると拒否され、検査は動き続けた。どちらか片方では読めた | 直す（[Task 18](plan.md#task-18)） |

直さないと判断したもの（主担当の判断）:

- xlide の推移的な依存（28 個）を固定していない: 1 回目と同じく、設計の[更新と保守](design.md#maintenance)で決めている。
- フックの入力に `mcp_server` がないと、ツール名の接頭辞だけで判定する: 古い Claude Code の扱いとして、受け入れるリスクにある。
- doctor が、受け取り用フォルダ・承認の記録・プラグインのキャッシュに書けないことを確かめない: 受け入れるリスクにあり、README で設定を勧めている。
- 不可視の文字の一覧に、異体字セレクタやソフトハイフンがない: 文字列の検査は見逃す前提（受け入れるリスク）。異体字セレクタ U+FE0F は絵文字でふつうに使われるので、警告に足すと誤検知が増える。
- CI の macOS のジョブが、runner の python の持ち主で失敗しうる: PR を作った後に分かる。plan の Task 15 の末尾に、対処を書いてある。

<a name="review-3"></a>

### /review（3 回目、`2d75fc2`）

2 回目の修正（Task 16〜19）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ、Red Team、Claude の敵対的なパスを出し、2 回目の後の差分を重点にした。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。Testing・Performance・Simplification・State Machines は指摘なし。QA の確かめ（小さな正しい Power Query のブックは `pass` と `power_query`、Power Query の中の zip bomb は `compression_ratio_too_high`、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

重大な指摘は、どれもレビュアーが xlide の環境（Python 3.15.2）で、検査を外して xlide に読ませるところまで再現した。base64 と `\d` の違いは、主担当も 2 つの Python で確かめた（3.9.6 は `b64decode("QQ==QQ==")` が `b'A'`、3.15.2 は `b'A\x04\x10'`。`\d` は U+16AC0 に 3.9.6 で合わず、3.15.2 で合う）。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 重大 | `scripts/check_workbook.py` | DataMashup の base64 の途中に `=` を入れると、検査（Python 3.9）は途中で止まって何も数えず、xlide（3.13 以降）は全部を戻して展開する（Security と敵対的なパスの両方） | 直す（[Task 22](plan.md#task-22)） |
| 重大 | `scripts/check_workbook.py` | 部品名の `\d` が合う数字は Unicode の版で違う。Unicode 14 以降の数字の部品名を、検査は読み飛ばし、pyopenvba は読む | 直す（[Task 22](plan.md#task-22)） |
| 重大 | `scripts/check_workbook.py` | DataMashup の中のメタデータの XML を、検査は見ない。pyopenvba は ElementTree で読み、xlide の expat 2.9.0 は内部実体を入力の 100 倍まで展開する（200 KB から 1,500 万文字） | 直す（[Task 22](plan.md#task-22)）。Task 17 の主担当の判断（メタデータは探さない）は誤りだった |
| 重大 | `scripts/check_workbook.py` | `<!-->` で始まるコメントを、pyofficeeditor はその場で閉じて後ろを読み、expat は次の `-->` まで読み飛ばす。非表示のシートや文字列を、警告なしで xlide に読ませられる | 直す（[Task 20](plan.md#task-20) で読み方の違いを洗い出し、[Task 21](plan.md#task-21) で直す） |
| 軽微 | `scripts/check_workbook.py` | pyopenvba の止まる所をまねる方式は、両方の Python の標準ライブラリが同じに動くことに頼る | 直す（[Task 22](plan.md#task-22)。Excel が書かない形をすべて不合格にする） |
| 軽微 | `.mcp.json` | xlide の Python の版を固定していない。調査と読み比べは 3.15.2 で行った | 直す（[Task 23](plan.md#task-23)。`--python 3.15`） |
| 軽微 | `hooks/hooks.json` | bash は、スクリプトの PATH の固定より前に、環境の `BASH_ENV` を読み、環境から渡された関数を取り込む | 直す（[Task 23](plan.md#task-23)。`/bin/bash -p`。bash 3.2 で効くことを主担当が確かめた） |
| 軽微 | 設計、README | 設計は Power Query の部品の文字列を見ると書くが、見ているのは base64 の文字の並びだけ | 文書を直す（[Task 22](plan.md#task-22)。M のコードは確かめない、という 1 回目の判断は変えない） |
| 軽微 | README、テスト | 日本語の言い回し 2 か所、`unsafe_part_name` の行の不足、Seatbelt のテストが EACCES でも拒否と数えうること | 直した（`77dd89c`、`1fb2760`） |

各 Task のレビューで先送りにした軽微な指摘は、主担当が仕分けた。上の表で直したものと、2 回目までに直ったもののほかは、直さない（主担当の判断）。どれも拒否の側に倒れるか、見た目だけか、plan の形のままのテストである。

- 拒否の側に倒れるもの: 中身のない zip は検査を通るが xlide が読めない。deflate した空のディレクトリのエントリは `unsafe_part_name`。暗号化の bit と bit 5・6 の組は `not_zip`。作った 32 MB の部品で 779 MB・9.2 秒。正規表現は作った入力で遅い（時間切れで拒否）。中の zip のエントリの数に上限がない（32 MB の中で数十万、増え方は線形）。
- 見た目と書き方: テストと `.mcp.json` に引数の写しがある。`check()` が `os.path.getsize` を 3 回呼ぶ。中の zip の展開の規則が `_check_part` の写しになっている。長い import の行。
- テストの形: plan の形のままで、規則を 1 つずつは固定していないテスト（`canonical_path` の部分、doctor の uid の規則）。変更の前から通っていたテスト。大文字小文字を区別しない APFS を前提にするテスト。
- CI: ジョブの時間の上限と同時実行の設定がない。Dependabot の github-actions に待ち時間がない。

<a name="parity-3"></a>

### xlide の読み手との読み比べ（3 回目の修正の後、`794058e`）

[Task 24 の Step 1](plan.md#task-24)。3 回目の `/review` で検査を外せた形ごとに、ブックを 1 つずつ作った。各ブックを、検査（Command Line Tools の python3）と、xlide の uv の環境の python 3.15.2（`xlide_mcp.cells` の `sheets()` と `read()`、pyopenvba の Power Query の読み手）で読んだ。ブックを作ったのはサブエージェントで、主担当が 2 つのスクリプトを実行し直して、同じ結果を確かめた。スクリプトとブックは `tmp/parity3/` に置き、コミットしていない。

| 形 | 検査の結果 | xlide（3.15.2）が読んだもの |
| --- | --- | --- |
| `<sheets>` の中の `<!-->` に、非表示のシートを入れる | 合格、`strings_not_checked` | 非表示のシート `Two` |
| 共有文字列の `<t>` の中の `<!-->` に、ゼロ幅スペースを入れる | 合格、`strings_not_checked` | ゼロ幅スペースを含む文字列（後ろの `-->` も文字として読む） |
| 共有文字列の `<t>` の中の `<!--->` に、句を入れる | 合格、`strings_not_checked` | 句（後ろの `-->` も文字として読む） |
| 共有文字列の部品の先頭の `<!-->` に、句を持つ偽の `<sst>` を入れる | 合格、`strings_not_checked` | 偽の `<sst>` の句。後ろの本物の `<sst>` は読まない |
| 正しい base64 の 6 文字目の後ろに `==` を挟み、中の zip に 2 MiB の 0 を入れる | 不合格、`not_zip` | 3.15 は全体を戻し、部品を 2,097,170 バイトに展開する。3.9 は 4 バイトで止まる |
| 同じ中の zip を、部品名 `customXml/item` + U+16AC0 + `.xml` に置く | 不合格、`compression_ratio_too_high` | 3.15 は pyopenvba の名前の規則に合い、部品を 2,097,170 バイトに展開する。3.9 では合わない |
| メタデータの節の XML に、内部実体の DTD を入れる | 不合格、`xml_dtd` | 667 バイトの XML を、250,009 文字に展開する。例外は出ない |

- どの形も、期待のとおり、検査で不合格になるか、`strings_not_checked` が出た。
- base64 を `b64(blob[:1]) + b64(blob[1:])` と 2 つに分けた形は、3.15 でも戻した全体がずれ、pyopenvba が読めなかった（検査は `not_zip`）。xlide が展開するのは、上の表の、`==` を挟んだ形である。
- メタデータの展開は約 375 倍で、3 回目の `/review` で見た 100 倍を超えた。expat の上限は、出力がある量（既定で 8 MiB）を超えてから効くためと見られる（推測）。
- 2 MiB の 0 を入れた 2 つのブックは、展開の後に、pyopenvba がクエリの書式の誤りで止まる。止まる前に展開は終わっている。シートを隠したブックでは、共有文字列の関係がないので、`read()` が `ValueError` で失敗した。読み比べの結論には関わらない。

<a name="review-4"></a>

### /review（4 回目、`6ce9c18`）

3 回目の修正（Task 20〜24）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ（Testing、Maintainability、Security、Performance、Simplification、State Machines）、Red Team、Claude の敵対的なパスを出し、3 回目の後の差分を重点にした。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。Testing のほかの専門のレビュアーは指摘なし。

最新の差分で、検査をすり抜ける形は見つからなかった。敵対的なパスは、正規の base64 に空白を混ぜた 5,021 件の入力と、Power Query の部品の 1,500 件の形を、検査（3.9.6）と pyopenvba（3.15.2）に読ませた。pyopenvba が展開し、検査が合格し、検査の数えた展開量が pyopenvba より少ない、という標本は 0 件だった。`<!-->` の判定も、pyofficeeditor の読み手の違いを尽くしていると確かめた。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 中 | `hooks/allowed-tools.txt`（`xlide_read_cells`・`xlide_evaluate_formula`） | 数式の計算は、検査を通ったまま上限なくメモリを使う。`calculate=true` の `xlide_read_cells` はブック全体を計算し（`xlide_mcp/cells.py:226-227,268`）、`SEQUENCE` は配列を全部作る。約 1 KB のブックの `=SUM(SEQUENCE(2000,2000))` で 351 MB を使い、検査は警告なしで合格にした。xlide は sandbox の外で動き、メモリに上限がない（敵対的なパスと Red Team の両方。主担当がソースで確かめた） | 直す（[Task 25](plan.md#task-25)。計算をフックで止め、`xlide_evaluate_formula` を外す） |
| 軽微 | `.mcp.json` | `--python 3.15` が固定するのはマイナー版だけ。この環境の uvx は mise の 3.15.2（expat 2.9.0）を使っていた。別の 3.15.x に黙って変わりうる。ただし、今の検査の規則はパッチ版に頼らない（敵対的なパスと Red Team） | 文書と手順で扱う（[Task 27](plan.md#task-27)。パッチ版までは固定しない） |
| 軽微 | `scripts/check_workbook.py` | 検査そのものは Command Line Tools の expat 2.2.8（2019 年）に頼る。乗っ取られた検査が「合格」と出力するのは Seatbelt では止まらない。届く既知の脆弱性は見つかっていない | 受け入れるリスクに書く（[Task 27](plan.md#task-27)） |
| 軽微 | `tests/test_check_workbook.py` | 中の zip の部品に extra field がある形と `itemProps1.xml` のテストがない。`+ xlen` を消す変異が全テストを通る（Testing） | テストを足す（[Task 26](plan.md#task-26)） |
| 軽微 | `tests/test_guard_xlide.py` | `bash -p` は文字列で固定しているだけで、設定どおりに動かして `BASH_ENV` を読まないことを確かめるテストがない（Testing） | テストを足す（[Task 26](plan.md#task-26)） |
| 軽微 | `tests/test_check_workbook.py` | 権限と結び付けの節だけに DTD を置いたテストがない。DTD を探す範囲をメタデータの節だけに狭めても落ちない（Task 22 の先送り） | テストを足す（[Task 26](plan.md#task-26)） |
| 軽微 | README | `uncompressed_too_large` の行が、古い部品名（`customXml/item<N>.xml`）のまま。日本語の Requirements の 1 行が普通体 | 直した（`5d36800`） |

QA の確かめ（正しい Power Query のブックは `pass` と `power_query`、base64 の途中に `==` を挟んだ zip bomb は `not_zip`、`<!-->` でシートを隠したブックは `strings_not_checked`、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

各 Task のレビューで先送りにした軽微な指摘のうち、上の表にないものは直さない（主担当の判断）。調査の文書の古い記述（[research-xlide-parsing.md](research-xlide-parsing.md) の 6 節の検査の説明）は、その時点の記録として残す。`total += len(blob)` の位置、`test_manifests.py` の引数の外し方、Task 21 のテストの部品名は、結果を変えない。

<a name="review-5"></a>

### /review（5 回目、`12a9da0`）

4 回目の修正（Task 25〜28）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ、Red Team、Claude の敵対的なパスを出し、4 回目の後の差分と、許可リストに残る 17 のツールを重点にした。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。Testing・Maintainability・Performance は指摘なし。

計算エンジンへの道は、すべて閉じていた（エンジンを作る 3 か所と、そこに届く xlide の 3 つの呼び出しは、どれもフックか許可リストで止まる）。`calculate` を別の名前で渡す道もなかった。ほかに、ファイルの中身だけで xlide が多くの時間やメモリを使う形が見つかった。敵対的なパスは、xlide の環境（Python 3.15.2）で、本物のツールを呼んで測った。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 重大 | `xlide_analyze` | pyvbaanalysis は `#Const` の文字列の連結を長さの上限なく評価し、1 行ごとに長さが倍になる（Security。主担当が 24 行で確かめた）。入れ子の深さの 2 乗のメモリも使い、8,857 バイトの `.xlsm`（警告は `vba_project` だけ）で 11 秒のうちに 3 GB を超えた（敵対的なパス） | 直す（[Task 29](plan.md#task-29)。`xlide_analyze` と `xlide_rules` を外す） |
| 重大 | `xlide_search_modules` | `is_regex=true` のとき、渡された正規表現を時間の上限なしに当てる。式の組み方で照合の時間が指数的に伸び、照合の間は xlide 全体が止まる | 直す（[Task 29](plan.md#task-29)。`regex_not_allowed`） |
| 重大 | `xlide_read_cells` | 共有数式の子をセルごとに親から導き直す。46,716 バイトのブック（警告なし）の 2 万セルで 90 秒・513 MB | 受け入れるリスクに書く（[Task 31](plan.md#task-31)。ユーザーの判断） |
| 重大 | `xlide_read_cells` | 行のセルを頭から探す。重複した `r` を 10 万個置いた 571 KB のブック（警告なし）で、1 セル約 37 ms（CPU だけ） | 同上 |
| 重大 | `xlide_list_queries` | クエリの数の 2 乗の時間がかかる（4,000 件で 31 秒） | 同上 |
| 重大 | `xlide_list_procedures` | 行の継続（`_`）をつなぐ処理が 2 乗の時間になる（20 万行で 3 秒） | 同上 |
| 重大 | runbook、README、design | 上限なく資源を使う道が、計算エンジンと VBA の展開だけのように読める | 直す（[Task 29](plan.md#task-29)・[Task 31](plan.md#task-31)） |
| 軽微 | VBA と CFB | `dir` の記録が同じストリームを何度も指す形、フォームのストレージの循環（ソースを読んだだけ） | 受け入れるリスクに書く（[Task 31](plan.md#task-31)） |
| 軽微 | `hooks/guard_xlide.py` | エージェントのチームが有効なとき、名前を付けて起動したエージェントはチームの一員になり、`SendMessage` が足される。フックは種類の名前でしか見分けない（Red Team。公式ドキュメントによる。入力の形は確かめていない） | 文書とスキルで扱う（[Task 31](plan.md#task-31)） |
| 軽微 | README、フック、検査 | `.xltx`・`.xltm` を受け付けるが、xlide 1.2.4 は読めない（Red Team） | 直す（[Task 30](plan.md#task-30)） |
| 軽微 | README | 下の依存（約 25 個）を固定していないことを書いていない（Red Team） | 文書を直す（[Task 31](plan.md#task-31)） |
| 軽微 | runbook | 通常のターミナルで全体のテストを動かすと、追跡していない `tests/test_*.py` や `__pycache__` も sandbox の外で読み込む（Red Team） | 直す（[Task 31](plan.md#task-31)。きれいな複製で動かす） |
| 軽微 | `skills/analyze/SKILL.md` | 拒否の理由の一覧に `calculation_not_allowed` がない（State Machines） | 直した（`62d094e`） |

重さは、レビューの規則どおりに付けた（直し方が分かっている敵対的なパスの指摘は重大と数える）。`xlide_read_cells` などの形は、xlide が大きなライブラリで、1 つずつ塞いでも尽きない見込みなので、ユーザーの判断で受け入れるリスクにした。害は Mac が重くなることで、情報が漏れるわけではない。Simplification の助言（`BASH_ENV` のテストの重複、DTD の 2 つのテストを 1 つにまとめる）は採らない。

QA の確かめ（正しい Power Query のブックは `pass` と `power_query`、`calculate=true` の呼び出しはファイルの確かめより前に `calculation_not_allowed`、`xlide_check_cells` は `tool_not_allowed`、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

<a name="review-6"></a>

### /review（6 回目、`4bbc3f3`）

5 回目の修正（Task 29〜32）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ、Red Team、Claude の敵対的なパスを出し、5 回目の後の差分を重点にした。受け入れた資源のリスクの形は、挙げ直さないよう伝えた。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。専門のレビュアーは 6 つとも指摘なし。

フックや承認を迂回する道は見つからなかった。`is_regex` を別の名前や型で渡す道もなく（mcp 2.3.0 は別名を作らない）、呼び出し元の正規表現を使うのは `xlide_search_modules` だけで、`analyze_project` に届くツールは許可リストにない。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 重大 | `agents/excel-analyst.md` | `is_regex` を使うなと書いていない。xlide のツールの説明は正規表現を勧めるので、正規表現で検索した時点で解析全体が止まりうる（敵対的なパス） | 直した（`1954697`） |
| 重大 | `hooks/guard_xlide.py` | `xlide_search_modules` の `query` に長さの上限がない。大文字小文字を区別しない検索の手間は、本文の長さと `query` の長さの積で増える（本文 40 万文字・`query` 2,000 文字で 0.55 秒） | 直す（[Task 33](plan.md#task-33)。256 文字まで） |
| 重大 | `hooks/guard_xlide.py` | エージェントのチームを切った前提を、文書だけで守っている。開いたリポジトリの設定でもチームを有効にできる | 直す（[Task 33](plan.md#task-33)。環境変数で拒否） |
| 重大 | README | 固定していない依存を「初回の起動で最新を取る」と書くが、uv は後の起動でも解決し直す（この Mac のキャッシュに、依存が 1 つだけ違う環境が 2 つあった） | 直した（`1954697`） |
| 重大 | runbook、README | 5 点目の「2 つ」の数え方、xlide のプロセスの終え方がない、`<確かめたコミット>` に完全な SHA と書いていない | 直した（`1954697`） |
| 軽微 | README | 別の受け取り用フォルダを使うとき、`Read(...)` の規則の絶対パスは `//` で書くこと（`/` 1 つだと設定ファイルからの相対）を書いていない。書き違えると、Read ツールの拒否が黙って効かない（Red Team。公式ドキュメントによる） | 直した（`1954697`） |
| 軽微 | `hooks/hooks.json` | フックの matcher は、ツール名が `xlide_` で始まる前提に頼る。後の版で前提が崩れると、フックが動かない（Red Team。1.2.4 の 65 のツールはすべて前提を満たす） | 直す（[Task 33](plan.md#task-33)。matcher を広げる） |
| 軽微 | README | uv のキャッシュに sandbox から書けると、xlide のコードを書き換えられる。そのことを書いていない（Red Team） | 直した（`1954697`） |

重さは、レビューの規則どおりに付けた（直し方が分かっている敵対的なパスの指摘は重大と数える）。どれも、今の版で検査や承認を迂回する道ではない。

QA の確かめ（正しいブックは `pass`、`is_regex=true` の検索はファイルの確かめより前に `regex_not_allowed`、同じ中身を `.xltx` と名付けたファイルは `unsupported_extension`、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

<a name="review-7"></a>

### /review（7 回目、`3efdd91`）

6 回目の修正（Task 33・34）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ、Red Team、Claude の敵対的なパスを出し、6 回目の後の差分を重点にした。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。専門のレビュアーは、Testing の確からしさの低い 1 件（文字列でない `query`。xlide の引数は文字列の型なので、付録に回した）のほかは指摘なし。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 中 | `hooks/guard_xlide.py` | Claude Code は、起動の引数 `--agent-teams` でもチームを有効にし、そのとき `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` は入らない。フックはこの起動の仕方を見分けない（敵対的なパスが、入っている Claude Code 2.1.332 の本体で確かめた） | 文書で扱う（[Task 35](plan.md#task-35)。この引数で起動しない、と書く） |
| 中 | README、スキル | 管理設定の `allowManagedHooksOnly` は、自分で入れたプラグインのフックを止めるが、xlide のサーバーは読み込まれる。README は `disableAllHooks` しか書いていなかった（Red Team） | README は直した（`054a81e`）。スキルの最初に、フックが動いていることの確かめを足す（[Task 35](plan.md#task-35)） |
| 軽微 | `hooks/guard_xlide.py` | ほかのフックが `updatedInput` で入力を書き換えると、ガードの判定を後から外せる（敵対的なパス。公式ドキュメントによる） | 受け入れるリスクに書く（[Task 35](plan.md#task-35)） |
| 重大 | `tests/test_guard_xlide.py` | matcher のテストは `re.fullmatch` で確かめるが、Claude Code は先頭と末尾を固定しない | 直す（[Task 35](plan.md#task-35)） |
| 軽微 | `tests/test_guard_xlide.py` | チームの拒否の位置（許可リストより前）を固定するテストがない（Task 33 のレビュー） | 直す（[Task 35](plan.md#task-35)） |
| 重大 | README | uv が選ぶ Python 本体の場所を、sandbox から書かせない対象に書いていない。`pkill -f xlide-mcp` が広すぎる（敵対的なパス） | 直した（`054a81e`） |
| 軽微 | README、runbook、design | 「変数が設定されている」と「空でない値」の違い、runbook の数え方、設計の図の古い matcher（Task 33 のレビュー） | 直した（`054a81e`） |

重さは、レビューの規則どおりに付けた（直し方が分かっている敵対的なパスの指摘は重大と数える）。付録: 会話の記録に残ったブックの中身を後のセッションが読める、という Red Team の指摘（確からしさ 4/10）は、README の注意 2 に記録が残ることを書いているので、採らない。

QA の確かめ（正しいブックは `pass`、チームの変数があると `xlide_doctor` も `agent_teams_enabled`、257 文字の `query` は `query_too_long`、変数がなければ `xlide_doctor` は許可、全体のテスト、shellcheck、`claude plugin validate . --strict`）は、どれも期待のとおりだった。

<a name="review-8"></a>

### /review（8 回目、`3b6dc4b`）

7 回目の修正（Task 35・36）の後に、ブランチ全体をもう一度見た。専門のレビュアー 6 つ、Red Team、Claude の敵対的なパスを出し、7 回目の後の差分（スキルの最初の確かめ）を重点にした。Codex のパスは、人が通常のターミナルで実行するため、ここでは飛ばした。専門のレビュアーは、Performance の 2 件のほかは指摘なし。敵対的なパスは、ガードを迂回する新しい道は見つからないと結論した。

| 重さ | 場所 | 内容 | 採否 |
| --- | --- | --- | --- |
| 軽微 | スキル | Step 5 の「`--agent-teams` で起動されているなら止まる」は、モデルが起動の引数を見られないので、何もしない（Red Team と敵対的なパスの両方） | 直す。チームが有効なときだけ見えるツールを手がかりにする（[Task 37](plan.md#task-37)）（D4 で Agent ツールの引数に変えた。[実機での確認](#manual)） |
| 軽微 | `hooks/intake_common.py`、README | 承認の記録（ファイルの実際のパスと SHA-256）は、プラグインのデータの置き場所に、プラグインを外すまで残る。README に書いていない（Red Team） | README に書く（[Task 38](plan.md#task-38)） |
| 重大 | README | Troubleshooting に、最初の確かめで止まったときの説明がない。`wrong_caller` の行に、確かめでは正常と書いていない（主担当と敵対的なパス） | 直した（`9a01971`） |
| 重大 | README | `pgrep` の手順が PID を 1 つと見ていた。uvx と、それが起動する Python の両方が当たる（敵対的なパス） | 直した（`9a01971`） |
| 軽微 | README | 使い方の「手順 1 の前に」が、ファイルを置く手順を指して読める。止まる場合を結果と許可の確認だけ挙げていた | 直した（`9a01971`） |
| 軽微 | スキル、README | フックが止まった環境で許可の確認が出たとき、「今後確認しない」を選ぶと許可の規則が残りうる（敵対的なパス。推測） | 「いいえ」を選び、許可や今後確認しない選択肢を選ばない、と書いた（`9a01971`） |
| 軽微 | `tests/test_skill_and_agent.py` | 確かめが手順 1〜4 の中に動いてもテストが通る（Task 35 のレビュー） | 直した（`854db19`）。確かめを手順 1 に動かした写しで落ちることを確かめた |

重さは、レビューの規則どおりに付けた（直し方が分かっている敵対的なパスの指摘は重大と数える）。採らなかったもの:

- `scripts/check_workbook.py` の `_MASHUP_SPLIT` は、細工した部品で 2 乗の手間になる（Performance、確からしさ 6/10）。検査は 20 秒で打ち切られて拒否になり、型は pyopenvba 6.6.0 に合わせてあるので、変えると読み方の違いを生む。
- 呼び出しのたびに検査し直す（Performance、確からしさ 5/10）。README の `check_timeout` の行に、読むたびに検査することと、大きなブックで時間切れになりやすいことを書いている。
- 付録: Seatbelt のプロファイルが IPC と IOKit を止めていない（Red Team、確からしさ 4/10）。

QA の確かめ（メインの会話からの `xlide_doctor` は `wrong_caller`、チームの変数があると `agent_teams_enabled`、サブエージェントからの `xlide_doctor` は許可、全体のテスト、shellcheck、`claude plugin validate . --strict`。直した後にも全体のテスト・shellcheck・検証をやり直した）は、どれも期待のとおりだった。
