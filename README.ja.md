# workbook-intake

[English](README.md)

外から受け取った Excel のブックを、Claude が xlide-mcp で解析する前に、作りの面から検査する Claude Code のプラグインです。

これは xlide-mcp とも NVIDIA SkillSpector とも関係のない、個人のプロジェクトです。
使うときは自己責任でお願いします。安全を保証するものではありません。

> [!WARNING]
> 検査が減らせるリスクは一部です。ブックを開いたり、どこかに送ったりして安全になるわけではありません。使う前に[制限](#limitations)を読んでください。

<a name="overview"></a>

## 何をするか

- xlide が読めるのは、受け取り用のフォルダ 1 つ（既定は `~/workbook-intake`）の中だけです。
- xlide がファイルを読む前に、個人情報や機密情報が含まれていないことの確認を求めます。答えはフックが記録し、モデルは答えを選べません。
- そのあと、フックが macOS の Seatbelt（通信も書き込みもできない）の中で、ファイルの作りを検査し、結果を固定の語彙で伝えます。
- xlide を呼べるのは、読み取り用のサブエージェントだけで、使えるのは読み取り用のツールだけです。それ以外の呼び出しはフックが止めます。

このプラグインに xlide のコードは含まれません。xlide-mcp は、固定した版を実行時に PyPI から取得します。

<a name="notes"></a>

## 利用上の注意

読ませたファイルの中身は、モデルへの入力として Anthropic に送られ、手元にも残ることがあります。

1. ファイルの中のものは何でも読めます。コメント、名前の定義、VBA、Power Query、外部リンクのパスなどです。非表示のシートや保護は、隠す仕組みとして働きません。個人情報（氏名・住所・生年月日・収入・借入など）が入ったファイルは、そのまま送ることになります。
2. 会話の記録は手元に平文で残ります（`~/.claude/projects/<project>/*.jsonl`。既定で 30 日。`cleanupPeriodDays` で変えられます）。
3. 顧客や取引先から受け取ったファイルに、Claude を誘導する文（プロンプトインジェクション）が入っていることがあります。xlide は読み取り専用で動き、解析するサブエージェントは Bash も Web も持ちません。ただし、要約を受け取るメインの会話は自分のツールを持っており、誘導されるおそれは残ります。
4. セルの値は、Excel が最後に保存したときの計算結果です。再計算はできません（フックが止めます）。Claude の読み違いもあります。人に出す数字は Excel で照らし合わせてください。
5. ファイルを Anthropic に送ってよいかは、所属の規程や契約で決まります。プラグインは、あなたに確かめて答えを記録するだけで、中身の判断はできません。

<a name="requirements"></a>

## Requirements（必要なもの）

- macOS（検査に Seatbelt の `sandbox-exec` を使います）。
- Command Line Tools（`xcode-select --install`。`python3` のため）。
- [uv](https://docs.astral.sh/uv/)（`uvx`）。
- Claude Code 2.1.295 以上（フックの `onFailure` のため）。`plugin.json` の `engines` で宣言していますが、Claude Code が `engines` を読むのは 2.1.323 以降なので、それより古い版では強制されません。マーケットプレイスをコミットの SHA で固定する（Install を見てください）には、2.1.324 以上が要ります。
- xlide は Python 3.15 で動きます。手元になければ、uv が初回の起動で取得します（取得できない環境では xlide のツールが見えません）。
- 初回は、`uvx` が Python と固定した版のパッケージを取得するので、通信が要り、時間がかかります。

`scripts/doctor.sh` が、スキルの開始時に必要なものを確かめます。`macos`・`uvx`・`python3`・`sandbox_exec`・`intake_dir_protected` ごとに `ok <項目>` か `missing <項目>` を出し、最後に `folder <パス>` を出します。

<a name="install"></a>

## Install（入れ方）

GitHub から入れてください。手元の作業用コピーをマーケットプレイスにして入れないでください。プラグインがそのフォルダの中でそのまま動き、そこで動く sandbox 付きのセッションから書き換えられうるためです。

手早い方法:

```sh
claude plugin marketplace add kado-ta/workbook-intake
claude plugin install workbook-intake@workbook-intake
```

おすすめは、確かめたコミットに固定し、自動更新を切ったままにすることです。ユーザーの settings（`~/.claude/settings.json`）で、`ref` に 40 文字のコミット SHA を書きます（マーケットプレイスのソースは `ref` に SHA を書けます。Claude Code 2.1.324 以上）。

```json
{
  "extraKnownMarketplaces": {
    "workbook-intake": {
      "source": {
        "source": "github",
        "repo": "kado-ta/workbook-intake",
        "ref": "<確かめたコミットの SHA（40 文字）>"
      },
      "autoUpdate": false
    }
  }
}
```

そのあと `claude plugin install workbook-intake@workbook-intake` を実行します。書き方は[公式ドキュメント](https://code.claude.com/docs/en/plugins/marketplace-reference.md#marketplace-sources)を見てください。

<a name="configuration"></a>

## Configuration（設定）

受け取り用フォルダを作ります: `mkdir -p ~/workbook-intake`。

プラグインは settings を配れないので、`~/.claude/settings.json` に自分で書きます。

必須（両方）。Claude の Bash と Read ツールが、受け取り用フォルダを読めなくなります。xlide とフックは sandbox の外で動くので、読めます。probe では `denyRead` だけだと Read ツールが読めたので、両方が要ります。Bash から受け取り用フォルダを一覧できると、スキルは止まります。

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

推奨:

- `"sandbox": {"allowUnsandboxedCommands": false}`: Claude Code のドキュメントによると、sandbox の外でコマンドを動かす要求を、Claude Code が無視するようになります。自分の確認では、この設定の効果だけを切り分けられていません。
- `"sandbox": {"failIfUnavailable": true}`: ドキュメントによると、sandbox が使えないとき、sandbox なしで動かさずに、Claude Code が起動を止めます。
- `"sandbox": {"filesystem": {"denyWrite": ["~/workbook-intake"]}}`: sandbox の中のコマンドが、このフォルダに書けないようにします（`~` で起動したセッションで効きます）。

`failIfUnavailable` と `denyWrite` の書き方は、動かして確かめた例ではなく、ドキュメントにあるキー名から書いたものです。これらのキーは、[settings の一覧](https://code.claude.com/docs/en/settings-reference.md)（`sandbox.filesystem.denyRead`・`sandbox.filesystem.denyWrite`・`sandbox.failIfUnavailable`・`sandbox.allowUnsandboxedCommands`）と[sandboxing](https://code.claude.com/docs/en/sandboxing.md)にあります。

プロジェクトが、同じ `uvx` のコマンドで `xlide` を定義していると、使われるのは片方だけで、プラグインのものは重複として外されます（Claude Code 2.1.331 で確認）。プロジェクトのほうは `"disabledMcpjsonServers": ["xlide"]` で無効にします。

別のフォルダを使うときは、Claude Code を起動する環境で `WORKBOOK_INTAKE_DIR` を設定し、2 つの拒否の設定も同じフォルダに変えます。

<a name="usage"></a>

## Usage（使い方）

1. ファイルを受け取り用フォルダに置きます（`.xlsx`・`.xlsm`・`.xltx`・`.xltm`・`.xlam`・`.xlsb`。100 MB まで）。
2. ファイルの名前を示して、解析を頼みます。例: 「`sales.xlsx` を /workbook-intake:analyze で解析して」。Claude はフォルダの中を一覧できないので、名前を示してください。
3. スキルが、固定の質問を出します。入力の確認と、検査に警告があるときだけの、警告の確認です。「確認した」「続ける」を選ぶと、フックが記録します。記録が効くのは、このセッションと、そのファイルの同じ中身だけです。
4. 読み取り専用のサブエージェント `workbook-intake:excel-analyst` が、xlide でブックを読み、要約を返します。

Google スプレッドシートは直接読みません。`.xlsx` でダウンロードして受け取り用フォルダに置いてください（Apps Script は含まれず、Google 独自の関数は Excel と同じには動かないことがあります）。claude.ai の Google Sheets のコネクタは、このプラグインの守りの外です。

<a name="checks"></a>

## Checks（検査）

検査は、Seatbelt の中で動く Python のスクリプトです。出すのは固定のコードだけで、ファイル由来の文字列は出しません。

不合格のコード（ファイルは読まれません）:

| コード | 意味 |
| --- | --- |
| `unsupported_extension` | 対象の拡張子ではない |
| `file_too_large` | 100 MB を超える |
| `encrypted` | 暗号化されている |
| `not_zip` | zip として開けない、または読み手によって読み方が変わりうる zip の形（注釈、前置きのデータ、エントリの隙間や重なり、ZIP64、中央ディレクトリと食い違うローカルヘッダー、Unicode Path の extra、フラグの 5・6 ビット、長さや CRC が中央ディレクトリと違う部品のデータ）。または、Power Query の部品の中の zip が壊れている（正規の形でない base64、節や部品の長さの食い違い） |
| `too_many_parts` | 部品が 10,000 を超える |
| `unsafe_part_name` | 部品名に `..`・絶対パス・`\`・ドライブ名（`C:` など）・NUL・空のセグメント・`.` のセグメント・中身のあるディレクトリ名がある、文字コードの印と合わない名前がある、または大文字小文字だけが違う名前が重なる |
| `uncompressed_too_large` | 展開の合計が 256 MB を超える（Power Query の部品の中の zip を含む）。または、名前が `customXml/item*.xml` の部品（`item1.xml`・`itemProps1.xml` など）が 32 MB を超える |
| `compression_ratio_too_high` | 1 つの部品（Power Query の部品の中の zip の部品を含む）が 100 倍を超えて圧縮されている |
| `xml_dtd` | 部品に `<!DOCTYPE` か `<!ENTITY` がある。XML に限らずすべての部品を探し、Power Query の部品の中身（中の zip の部品とメタデータ）も探すので、SVG の画像や、HTML を書き出すマクロでも出ることがある |

警告のコード（確認してから続けます）:

| コード | 意味 |
| --- | --- |
| `vba_project` | VBA のプロジェクトがある |
| `external_link` | 外部のブックへのリンクがある |
| `data_connection` | データ接続がある |
| `external_relationship` | ファイルの外を指す関係がある |
| `power_query` | Power Query（DataMashup）がある。クエリの中の文字列（M のコード、クエリ名、説明）は確かめない |
| `embedded_object` | 埋め込みのオブジェクトがある |
| `activex` | ActiveX がある |
| `hidden_sheet` | 非表示のシートがある |
| `very_hidden_sheet` | `veryHidden` のシートがある |
| `invisible_characters` | 文字列に、ゼロ幅・向きの制御・タグの文字がある |
| `instruction_like_text` | AI への指示らしい文言がある |
| `very_long_string` | 10,000 文字を超える文字列がある（Power Query のブックでも出ることがある。クエリが 1 本の長い符号化された文字列として保存されるため） |
| `strings_not_checked` | 確かめきれなかった部品がある。その部品の文字列・シートの状態・関係は分からない: `.xlsb`（二進）、大きすぎる XML、検査が読めない XML、1 つの要素に同じローカル名の属性が 2 つある、256 段より深い入れ子、バイトオーダーマークがなく先頭 2 バイトに NUL がある部品、段落の中の入れ子になったテキストの塊、xlide の読み手と XML の構文の読み方が違う部品（`<!-->` で始まるコメントなど） |

検査の状態: `pass`、`fail`、`error`（語彙の外の出力や、想定外の結果）、`timeout`（20 秒超）、`sandbox_missing`（`sandbox-exec` がない）。

<a name="limitations"></a>

## Limitations（制限）

- 文字列の検査は見逃すことがあり、誤検知もあります。ウイルス対策ではありません。ウイルス対策は、使う人の端末のものに任せてください。
- 検査のあと、読むまでにファイルが差し替えられることがあります。受け取り用フォルダは sandbox の書き込みの範囲の外ですが、sandbox の外のもの（人や、ほかのアプリ）は差し替えられます。`denyWrite` を使ってください。
- 推奨設定がない環境では、スキルを通らない使い方（ほかのスキルや、Bash で読むよう直接頼むこと）で、受け取り用フォルダを読めます。`doctor.sh` はスキルの中でしか動きません。
- `disableAllHooks` は、どのスコープの設定（リポジトリの `.claude/settings.json` を含む）でもフックを止められます（管理設定のフックは除く）。プラグインのフックも止まる見込みです（推測で、確かめていません）。止まると、メインの会話から xlide を呼べ、入力の確認も検査も効きません。止まっている環境では使わないでください。
- VBA のソースは、xlide が上限なしに展開します。マクロのブック（`vba_project` の警告）は、メモリを多く使うことがあります。
- 入力の確認は、AskUserQuestion の画面に人が答えることに頼ります。ほかのプラグインのフックや SDK のホストが答えを埋める環境では、人の確認なしに承認が記録されることがあります。
- ツール名には `mcp__plugin_workbook-intake_xlide__` が付きます（例: `mcp__plugin_workbook-intake_xlide__xlide_doctor`）。サーバー名だけを書いた matcher（`mcp__xlide__.*`）には当たりません。
- プラグインのサブエージェントは自分の MCP サーバーを持てないので、xlide はメインの会話からも見えます。メインの会話からの呼び出しは、フックが止めます。
- フックの許可は、確認を省くだけです。settings の deny と ask の規則は残ります。
- ファイル名の見せかけ（似た文字、特殊な空白、結合文字）は、完全には防げません。その名前の実ファイルが受け取り用フォルダに要ります。
- `.xls` は扱えません。xlide が `.xlsb` のシートを読めるのは Windows だけです（macOS では、シートのツールが `.xlsb` を拒否します）。
- 承認の記録は、プラグインのデータの置き場所にあります。sandbox の中のコマンドがそこへ書ける環境では、承認を偽れます。
- プラグインのキャッシュが sandbox から書ける環境では、フックを書き換えられます。GitHub のアカウントが乗っ取られると、悪い更新を配られうるので、SHA で固定して自動更新を切っておくと、自分で確かめた版だけを使いやすくなりますが、防げるわけではありません。
- uv の取得元は、環境変数（`UV_DEFAULT_INDEX` など）で変えられます。
- xlide は `uvx` を PATH から探して起動します。PATH の先頭に、sandbox から書ける場所を置かないでください。
- macOS だけです。xlide の Windows 向けの live 系のツールは使いません。
- 守りの対象外: このプラグインなしで xlide を使う人、Google Sheets のコネクタ。

<a name="troubleshooting"></a>

## Troubleshooting（困ったとき）

入力の確認のフックが返す文（`workbook-intake: consent=...`、`warnings_ack=...`）。記録できたときは `consent=recorded; check=<状態>; failures=...; warnings=...` か `warnings_ack=recorded` です。記録されなかったときの `reason=` は次のとおりです。

| 理由 | 意味 |
| --- | --- |
| `bad_input` | フックの入力かセッション ID を読めない |
| `question_mismatch` | 固定の質問と違う |
| `not_confirmed` | 答えが「確認した」「続ける」ではない |
| `path_not_absolute` | パスが絶対パスではない |
| `intake_dir_invalid` | 受け取り用フォルダがない、シンボリックリンク、または `/` |
| `outside_intake` | ファイルが受け取り用フォルダの外にある |
| `not_regular_file` | 通常のファイルではない |
| `unsupported_extension` | 対象外の拡張子 |
| `file_too_large` | 100 MB を超える |
| `path_not_canonical` | パスが実体のパスと違う、または前後に空白か制御文字がある |
| `file_changed` | 検査のあいだにファイルが変わった |
| `consent_store_unavailable` | 記録を書けない（プラグインのデータの置き場所がない） |
| `no_consent` | このファイルの中身に、入力の確認の記録がない |
| `internal_error` | フックの想定外のエラー |

xlide を守るフックの拒否（`workbook-intake: <理由>`。必要なら括弧の中に不合格か警告のコード）:

| 理由 | 意味 |
| --- | --- |
| `not_plugin_server` | このプラグインの xlide のツールではない（プロジェクトの xlide など） |
| `tool_not_allowed` | 許可リスト（`hooks/allowed-tools.txt`）にないツール |
| `wrong_caller` | 呼び出し元が `workbook-intake:excel-analyst` ではない |
| `unexpected_path_argument` | `file_path` 以外にパスらしい引数がある |
| `calculation_not_allowed` | 計算を求める呼び出し（`calculate=true` など）。xlide の計算エンジンは上限なくメモリを使いうるため |
| `missing_file_path` | ツールに `file_path` が要る |
| `bad_input` | フックの入力を読めない |
| `outside_intake`・`path_not_absolute`・`intake_dir_invalid`・`not_regular_file`・`unsupported_extension`・`file_too_large` | 上の表と同じ |
| `path_not_canonical` | 上の表と同じ（そのようなパスは、フックと xlide とで別のファイルに解決されうるため） |
| `consent_store_unavailable`・`no_consent` | 上の表と同じ |
| `check_failed` | 検査が不合格（不合格のコードが続く） |
| `check_timeout` | 検査が 20 秒を超えた。XML が合計でおよそ 200 MB 以上のブック（大きなシートが多い 50 MB の `.xlsx` など）で起きやすい。検査は読むたびに行う |
| `sandbox_missing` | `sandbox-exec` がない |
| `check_error` | 検査の結果を使えない、または検査のあとにファイルが変わった |
| `warnings_not_acknowledged` | 警告があり、警告の確認が記録されていない |
| `python_missing` | Command Line Tools の `python3` が見つからない（xlide の呼び出しはすべて止まる） |
| `internal_error` | フックの想定外のエラー |

フックが拒否したら、スキルは止まって理由を伝えます。別の方法でファイルを読もうとはしません。

`doctor.sh` の項目: `macos`（macOS ではない）、`uvx`（uv が PATH にない）、`python3`（Command Line Tools がない、またはその python が root の持ち物でない）、`sandbox_exec`（`/usr/bin/sandbox-exec` がない）、`intake_dir_protected`（Bash から受け取り用フォルダを一覧できる。必須の設定がないか、sandbox が切れている）。xlide のツールが見えないときは、uv がない、初回の取得に失敗した、プロジェクトの `xlide` にプラグインのものが外された、のどれかです（[設定](#configuration)を見てください）。

<a name="maintenance"></a>

## Maintenance（保守）

作者は、プライベートの時間が許す範囲で保守します。定期的な更新も、Issue や PR への返事も、約束はしません。

- 版を固定しています（xlide-mcp 1.2.4 と依存 4 つ）。それらにセキュリティの修正が出ても、作者が固定を上げるまでは入りません。
- マーケットプレイスをコミットの SHA で固定し、自動更新を切っておいてください。SHA を動かす前に、差分を読んでください。
- 急ぐときは、リポジトリを fork して、自分で固定を上げてください（MIT）。
- 作者の手順は [docs/runbooks/maintenance.md](docs/runbooks/maintenance.md) にあります（日本語）。

<a name="license"></a>

## License（ライセンス）

MIT。[LICENSE](LICENSE) を見てください。

[xlide-mcp](https://github.com/WilliamSmithEdward/xlide_mcp) の作者と、その土台のライブラリの作者に感謝します。どれも MIT です。このリポジトリには含まれず、サーバーの起動時に `uvx` が PyPI から取得します。
