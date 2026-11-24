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

`719943d` から `d093bcb` までに、Seatbelt・フック・検査のコードとそのテスト（`hooks/`、`scripts/check_workbook.*`、`tests/test_sandbox_profile.py`、`tests/test_guard_xlide.py`、`tests/test_record_consent.py`、`tests/test_check_workbook.py`）は変わっていない（`git diff --stat` で確かめた）。そのため、人による Seatbelt 付きの実行は、やり直していない。CI（Linux と macOS）の結果は、PR を作った後に足す。

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

<a name="reviews"></a>

## レビュー

（Task 12 で書く: `/review`、`/security-review`、Codex のレビューの結果と、採否）
