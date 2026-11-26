# workbook-intake

[English](README.md)

外から受け取った Excel のブックを、Claude が xlide-mcp で解析する前に、作りの面から検査する Claude Code のプラグインです。

これは xlide-mcp とも NVIDIA SkillSpector とも関係のない、個人のプロジェクトです。
使うときは自己責任でお願いします。安全を保証するものではありません。

> [!WARNING]
> 検査が減らせるリスクは一部です。ブックを開いたり、どこかに送ったりして安全になるわけではありません。使う前に[制限](#limitations)を読んでください。

<a name="overview"></a>

## 何をするか

- xlide が読めるのは、受取用フォルダ 1 つ（既定は `~/workbook-intake`。変える方法は[別の受取用フォルダを使う](#another-folder)）の中だけです。
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
4. セルの値は、Excel が最後に保存したときの計算結果です。再計算・数式の評価・セルのエラー検査・VBA の静的な解析・正規表現の検索はできません（フックが止めます）。Claude の読み違いもあります。人に出す数字は Excel で照らし合わせてください。
5. ファイルを Anthropic に送ってよいかは、所属の規程や契約で決まります。プラグインは、あなたに確かめて答えを記録するだけで、中身の判断はできません。
6. 確認の答えは、`${CLAUDE_PLUGIN_DATA}/consents/`（`~/.claude/plugins/data/<id>/consents/`。`<id>` はプラグインの識別子の、英数字・`_`・`-` 以外の文字を `-` に置き換えたものです）に、セッションごとに `<セッション ID の SHA-256>.jsonl` というファイルで、平文のまま残ります。各行には、確認を求めたファイルの実際のパス（パスには取引先の名前が入ることがあります）と中身の SHA-256 が入ります。入力の確認の行には、さらに検査の結果と、不合格と警告のコードが入り、警告の確認の行には、さらに警告のコードが入ります。プラグインにこれらを消す処理はありません。Claude Code は、プラグインを最後に入れていた場所から外すときにこのフォルダを消しますが、`--keep-data` を付けた場合は残ります（ほかにも残る場合があります。[plugin uninstall](https://code.claude.com/docs/en/plugins/cli-reference.md#plugin-uninstall) を見てください）。それより前に消すときは、プラグインを使っている Claude Code のセッションがないことを確かめてから、`consents` フォルダを削除してください。フォルダがなくても、次の確認のときに作り直されます。次の分析では、ファイルの確認をもう一度求められます。
7. 守られるのは、受取用フォルダの中のファイルだけです。フォルダの外のコピー（ダウンロード先、メールの添付）とハードリンクは守られず、Claude は別の経路から読めます。コピーではなく、ファイルをフォルダに移してください。

<a name="requirements"></a>

## 必要なもの

- macOS（検査に Seatbelt の `sandbox-exec` を使います）。
- Command Line Tools（`xcode-select --install`。`python3` のため）。
- [uv](https://docs.astral.sh/uv/)（`uvx`）。
- Claude Code 2.1.295 以上（フックの `onFailure` のため）。`plugin.json` の `engines` で宣言していますが、Claude Code が `engines` を読むのは 2.1.323 以降なので、それより古い版では強制されません。マーケットプレイスをコミットの SHA で固定する（[インストール](#install)を見てください）には、2.1.324 以上が要ります。
- xlide は Python 3.15 で動きます。手元になければ、uv が初回の起動で取得します（取得できない環境では xlide のツールが見えません）。固定するのはマイナー版（3.15）だけです。uv が管理する 3.15 があればそれを、なければ PATH の `python3.15` を使います。
- 初回は、`uvx` が Python と固定した版のパッケージを取得するので、通信が要り、時間がかかります。

`scripts/doctor.sh` が、スキルの開始時に必要なものを確かめます。`macos`・`uvx`・`python3`・`sandbox_exec`・`intake_dir_protected` ごとに `ok <項目>` か `missing <項目>` を出し、最後に `folder <パス>` を出します。

<a name="install"></a>

## インストール

GitHub から入れてください。手元の作業用コピーをマーケットプレイスにして入れないでください。プラグインがそのフォルダの中でそのまま動き、そこで動く sandbox 付きのセッションから書き換えられうるためです。

プラグインは settings を配れないので、[必須の設定](#required-settings)は自分で書きます。書く先は、プラグインを有効にした範囲と同じ範囲の settings のファイルです。次の 2 通りのどちらかを選びます。

| | すべてのプロジェクトで使う | 1 つのプロジェクトで使う |
| --- | --- | --- |
| プラグインの範囲 | `user`（`claude plugin install` の既定） | `local` |
| 設定を書くファイル | `~/.claude/settings.json` | プロジェクトのフォルダの `.claude/settings.local.json`（または `.claude/settings.json`） |

プロジェクトの settings は、そのプロジェクトで起動したセッションにだけ効きます。プラグインが有効なのに必須の設定がないプロジェクトでは、スキルは最初の確かめで止まります。ただし、スキルを使わずに頼めば、Claude は受取用フォルダを読めます（[制限](#limitations)）。

<a name="install-every-project"></a>

### すべてのプロジェクトで使う

1. 受取用フォルダを作ります。

   ```sh
   mkdir -p ~/workbook-intake
   ```

2. マーケットプレイスを足し、プラグインを入れます。

   ```sh
   claude plugin marketplace add kado-ta/workbook-intake
   claude plugin install workbook-intake@workbook-intake
   ```

3. [必須の設定](#required-settings)を `~/.claude/settings.json` に足します。

<a name="install-one-project"></a>

### 1 つのプロジェクトで使う

1. 受取用フォルダを作ります。

   ```sh
   mkdir -p ~/workbook-intake
   ```

2. プロジェクトのフォルダで、マーケットプレイスを足し、`--scope local` を付けてプラグインを入れます。

   ```sh
   cd <使うプロジェクト>
   claude plugin marketplace add kado-ta/workbook-intake
   claude plugin install workbook-intake@workbook-intake --scope local
   ```

3. [必須の設定](#required-settings)を、そのプロジェクトのフォルダの `.claude/settings.local.json` に足します。プロジェクトの `.claude/settings.json` に書いても、このプロジェクトで起動したセッションには同じように効きます。違いは共有されるかどうかです。`.claude/settings.local.json` は自分だけのものです（手で作ったときは `.gitignore` に足してください）。`.claude/settings.json` はコミットすると、そのプロジェクトで作業する全員に効きます。

<a name="pin"></a>

### 確かめたコミットに固定する（推奨）

手順 2 の `claude plugin marketplace add` の代わりに、マーケットプレイスを確かめたコミットに固定し、自動更新を切ったままにします。`~/.claude/settings.json` で、`ref` に 40 文字のコミット SHA を書きます（マーケットプレイスのソースは `ref` に SHA を書けます。Claude Code 2.1.324 以上）。

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

そのあと、選んだ方法の `claude plugin install` のコマンドを実行します。書き方は[公式ドキュメント](https://code.claude.com/docs/en/plugins/marketplace-reference.md#marketplace-sources)を見てください。

<a name="required-settings"></a>

### 必須の設定

選んだ方法の settings のファイル（`~/.claude/settings.json` か、プロジェクトの `.claude/settings.local.json` か `.claude/settings.json`）に、両方を足します。今の settings に足してください（置き換えないでください）。sandbox は既定で無効なので、`"enabled": true` も必須に含まれます。Claude の Bash と Read ツールが、受取用フォルダを読めなくなります。xlide とフックは sandbox の外で動くので、読めます。probe では `denyRead` だけだと Read ツールが読めたので、両方が要ります。sandbox が Bash による受取用フォルダの読み取りを拒否しないと、スキルは止まります。

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

### 推奨の設定

- `"sandbox": {"allowUnsandboxedCommands": false}`: Claude Code のドキュメントによると、sandbox の外でコマンドを動かす要求を、Claude Code が無視するようになります。自分の確認では、この設定の効果だけを切り分けられていません。
- `"sandbox": {"failIfUnavailable": true}`: ドキュメントによると、sandbox が使えないとき、sandbox なしで動かさずに、Claude Code が起動を止めます。
- `"sandbox": {"filesystem": {"denyWrite": ["~/workbook-intake"]}}`: sandbox の中のコマンドが、このフォルダに書けないようにします（`~` で起動したセッションで効きます）。

`failIfUnavailable` と `denyWrite` の書き方は、動かして確かめた例ではなく、ドキュメントにあるキー名から書いたものです。これらのキーは、[settings の一覧](https://code.claude.com/docs/en/settings-reference.md)（`sandbox.filesystem.denyRead`・`sandbox.filesystem.denyWrite`・`sandbox.failIfUnavailable`・`sandbox.allowUnsandboxedCommands`）と[sandboxing](https://code.claude.com/docs/en/sandboxing.md)にあります。

<a name="another-folder"></a>

### 別の受取用フォルダを使う

別のフォルダを使うときは、Claude Code を起動する環境で `WORKBOOK_INTAKE_DIR` を設定し、[必須の設定](#required-settings)にある 2 つの拒否（`sandbox.filesystem.denyRead` と、`permissions.deny` の `Read(...)` の規則）も、同じフォルダに変えます。この 2 つは、絶対パスの書き方が違います。`sandbox.filesystem.denyRead` は `/abs/path` と書きますが、`Read(...)` の権限の規則は先頭に斜線を 2 つ付けて `Read(//abs/path/**)` と書きます（斜線が 1 つだと、設定ファイルの場所からの相対になります）。ホームフォルダの下なら、どちらも `~/...` と書けます。フォルダのパスに `:` は使えません。xlide が複数のフォルダに分けてしまうため、フックは `intake_dir_invalid` で拒否します。

たとえば `~/received` を使うときは、次のようにします。

1. フォルダを作り、Claude Code を起動するシェルで変数を設定してから起動します（毎回使うなら、`export` の行を `~/.zshrc` などに書きます）。フック、xlide、`doctor.sh` は、どれも起動したときのこの変数を見ます。

   ```sh
   mkdir -p ~/received
   export WORKBOOK_INTAKE_DIR=~/received
   claude
   ```

2. 選んだ方法の settings のファイル（`~/.claude/settings.json` か、プロジェクトの `.claude/settings.local.json` か `.claude/settings.json`）で、2 つの拒否をそのフォルダに変えます。ほかのキーはそのまま残します。変えた後の必須の設定は、次のとおりです。

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

<a name="project-xlide"></a>

### プロジェクトの xlide

プロジェクトが、同じ `uvx` のコマンドで `xlide` を定義していると、使われるのは片方だけで、プラグインのものは重複として外されます（Claude Code 2.1.331 で確認）。プロジェクトのほうは `"disabledMcpjsonServers": ["xlide"]` で無効にします。プラグインが有効な範囲では、サブエージェント（アナリスト）以外からの xlide の呼び出しは、プロジェクト自身の xlide サーバーへの呼び出しを含めて、フックがすべて拒否します。

<a name="usage"></a>

## 使い方

1. ファイルを受取用フォルダに置きます（`.xlsx`・`.xlsm`・`.xlam`・`.xlsb`。100 MiB まで）。テンプレート（`.xltx`・`.xltm`）は、xlide が読めないため受け付けません。Excel で `.xlsx` か `.xlsm` に保存し直してから置いてください。
2. ファイルの名前を示して、解析を頼みます。例: 「`sales.xlsx` を /workbook-intake:analyze で解析して」。Claude はフォルダの中を一覧できないので、名前を示してください。
3. スキルが、固定の質問を出します。入力の確認と、検査に警告があるときだけの、警告の確認です。「確認した」「続ける」を選ぶと、フックが記録します。記録が効くのは、このセッションと、そのファイルの同じ中身だけです。
4. 読み取り専用のサブエージェント `workbook-intake:excel-analyst` が、xlide でブックを読み、要約を返します。

スキルは始まるとき（手順 2 で、何かを尋ねる前に）、まず受取用フォルダの中の存在しないファイル名（`workbook-intake-read-check.xlsx`）を Read で 1 回呼び、Claude Code が権限の設定を理由に拒否したときだけ進みます（`Read(...)` の deny が設定されていることの確かめです）。そのあと、メインの会話から `xlide_doctor` を 1 回呼び、フックが動いていることを確かめます。フックはこの呼び出しを `workbook-intake: wrong_caller` で拒否します。この拒否は正常です。`xlide_doctor` の許可の確認が出たときは、フックが動いていません。「いいえ」を選んでください（許可する選択肢や、今後確認しない選択肢は選ばないでください）。この拒否のほかの結果（結果が返った、許可しなかった、ほかの理由で拒否された）では、スキルは止まります（[トラブルシューティング](#troubleshooting) を見てください）。同じところで、Agent ツールに `name` か `team_name` の引数があるときも、スキルは止まります（エージェントのチームが有効です）。

Google スプレッドシートは直接読みません。`.xlsx` でダウンロードして受取用フォルダに置いてください（Apps Script は含まれず、Google 独自の関数は Excel と同じには動かないことがあります）。claude.ai の Google Sheets のコネクタは、このプラグインの守りの外です。

<a name="checks"></a>

## 入力ファイルチェック

入力ファイルチェック（以下、検査）は、Seatbelt の中で動く Python のスクリプトです。出すのは固定のコードだけで、ファイル由来の文字列は出しません。

不合格のコード（ファイルは読まれません）:

| コード | 意味 |
| --- | --- |
| `unsupported_extension` | 対象の拡張子ではない |
| `file_too_large` | 100 MiB を超える |
| `encrypted` | 暗号化されている |
| `not_zip` | zip として開けない、または読み手によって読み方が変わりうる zip の形（注釈、前置きのデータ、エントリの隙間や重なり、ZIP64、中央ディレクトリと食い違うローカルヘッダー、Unicode Path の extra、フラグの 5・6 ビット、長さや CRC が中央ディレクトリと違う部品のデータ）。または、Power Query の部品の中の zip が壊れている（Base64 の文字の外の文字がある、パディングの位置が違う、復号できない長さである、または節や部品の長さが食い違う） |
| `too_many_parts` | 外側のパッケージの部品が 10,000 を超える。Power Query の部品の中の zip には部品の数の上限はなく、展開の合計と圧縮率の上限で大きさを抑える |
| `unsafe_part_name` | 部品名に `..`・絶対パス・`\`・ドライブ名（`C:` など）・NUL・空のセグメント・`.` のセグメント・中身のあるディレクトリ名がある、文字コードの印と合わない名前がある、または大文字小文字だけが違う名前が重なる |
| `uncompressed_too_large` | 展開の合計が 256 MiB を超える（Power Query の部品の中の zip を含む）。または、名前が `customXml/item*.xml` の部品（`item1.xml`・`itemProps1.xml` など）が 32 MiB を超える |
| `compression_ratio_too_high` | 1 つの部品（Power Query の部品の中の zip の部品を含む）が 100 倍を超えて圧縮されている。100 KiB 以下の部品には、この上限を使わない |
| `xml_dtd` | 部品に `<!DOCTYPE` か `<!ENTITY` がある。XML に限らずすべての部品を探し、Power Query の部品の中身（中の zip の部品とメタデータ）も探すので、SVG の画像や、HTML を書き出すマクロでも出ることがある |

警告のコード（確認してから続けます）:

| コード | 意味 |
| --- | --- |
| `vba_project` | VBA のプロジェクトがある |
| `external_link` | 外部のブックへのリンクがある |
| `data_connection` | データ接続がある |
| `external_relationship` | ファイルの外を指す関係がある |
| `power_query` | どれかの部品に `DataMashup` の印がある（Power Query の意味）。クエリの中の文字列（M のコード、クエリ名、説明）は確かめない |
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

## 制限

- 文字列の検査は見逃すことがあり、誤検知もあります。ウイルス対策ではありません。ウイルス対策は、使う人の端末のものに任せてください。
- 検査のあと、読むまでにファイルが差し替えられることがあります。受取用フォルダは sandbox の書き込みの範囲の外ですが、sandbox の外のもの（人や、ほかのアプリ）は差し替えられます。`denyWrite` を使ってください。
- 推奨設定がない環境では、スキルを通らない使い方（ほかのスキルや、Bash で読むよう直接頼むこと）で、受取用フォルダを読めます。`doctor.sh` はスキルの中でしか動きません。
- `disableAllHooks` は、どのスコープの設定（リポジトリの `.claude/settings.json` を含む）でもフックを止められます（管理設定のフックは除く）。プラグインのフックも止まる見込みです（推測で、確かめていません）。管理設定の `allowManagedHooksOnly` も、自分で入れたプラグインのフックを止めます。そのときも、プラグインの xlide のサーバーは読み込まれます。止まると、メインの会話から xlide を呼べ、入力の確認も検査も効きません。止まっている環境では使わないでください。
- 検査は、Command Line Tools の Python 3.9.6 と、その expat 2.2.8 で動きます。Seatbelt は、乗っ取られた検査の書き込み・通信・実行を止めますが、判定そのものは守りません。文字コードの厳密な復号、DTD の拒否、1 部品 32 MiB の上限で、届く面を狭くしています。
- VBA のソースは、xlide が上限なしに展開します。マクロのブック（`vba_project` の警告）は、メモリを多く使うことがあります。
- 細工したファイルで、許可しているツールを通して、xlide が多くの時間やメモリを使うことがまだありえます。例（測った値は[テストレポート](docs/work/20261124_workbook-intake/test-report.md#review-5)にあります）: 長い共有数式を読む、1 行に大量のセルがある、クエリが数千件ある、VBA の行の継続が多い。xlide は sandbox の外で動き、メモリの上限がありません。重くなったら Claude Code を止め、通常のターミナルで xlide のプロセスを終えてください（sandbox の中のコマンドからは見えません）。`pgrep -fl 'xlide-mcp.*--read-only'` でプロセスを一覧し（uvx と、それが起動する Python の両方が出ます）、出た PID をすべて `kill` で止めます。最も重い形（計算、VBA の静的な解析、正規表現の検索）はフックが止めます。
- エージェントのチーム（実験的な機能、`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`）は切ってください。有効にすると、ブックを読むエージェントがほかの仲間に直接話しかけられることがあるため、この変数が空でない値（`0` を含む）を持つ間は、フックがすべての xlide の呼び出しを止めます（`agent_teams_enabled`）。この確かめは、フックのプロセスに渡る環境だけを見ます。起動の引数 `--agent-teams` でもエージェントのチームは有効になり、そのときフックは見分けられません。その代わりに、スキルは、Agent ツールに `name` か `team_name` の引数があると止まります。Claude Code は、エージェントのチームが有効な間だけ、これらの引数を足します（Claude Code 2.1.332 の本体を読んで確かめました）。`--agent-teams` を付けて Claude Code を起動しないでください。
- `.mcp.json` が固定するのは xlide-mcp と 4 つの依存だけです。ほかの依存は、uv が環境を作るときに解決します。後の起動で作り直すこともあるので、新しい版はどの起動でも入りえます（下の依存のセキュリティの修正を受け取るため）。
- 入力の確認は、AskUserQuestion の画面に人が答えることに頼ります。ほかのプラグインのフックや SDK のホストが答えを埋める環境では、人の確認なしに承認が記録されることがあります。
- PreToolUse のフックは並行して動き、ほかのプラグインや自分のフックは `updatedInput` で入力を書き換えられます。ガードが許可した後で書き換えられると、承認や検査を通らない入力で xlide が動くことがあります（受取用フォルダの外は xlide 自身が止めます）。入力を書き換えるフックを入れないでください。
- ツール名には `mcp__plugin_workbook-intake_xlide__` が付きます（例: `mcp__plugin_workbook-intake_xlide__xlide_doctor`）。サーバー名だけを書いた matcher（`mcp__xlide__.*`）には当たりません。
- プラグインのサブエージェントは自分の MCP サーバーを持てないので、xlide はメインの会話からも見えます。メインの会話からの呼び出しは、フックが止めます。
- フックの許可は、確認を省くだけです。settings の deny と ask の規則は残ります。
- ファイル名の見せかけ（似た文字、特殊な空白、結合文字）は、完全には防げません。その名前の実ファイルが受取用フォルダに要ります。
- `.xls` は扱えません。xlide が `.xlsb` のシートを読めるのは Windows だけです（macOS では、シートのツールが `.xlsb` を拒否します）。
- 承認の記録は、プラグインのデータの置き場所にあります。sandbox の中のコマンドがそこへ書ける環境では、承認を偽れます。
- プラグインのキャッシュが sandbox から書ける環境では、フックを書き換えられます。GitHub のアカウントが乗っ取られると、悪い更新を配られうるので、SHA で固定して自動更新を切っておくと、自分で確かめた版だけを使いやすくなりますが、防げるわけではありません。
- uv の取得元は、環境変数（`UV_DEFAULT_INDEX` など）で変えられます。
- xlide は `uvx` を PATH から探して起動します。PATH の先頭に、sandbox から書ける場所を置かないでください。
- xlide は、uv のキャッシュ（`~/.cache/uv`、または `UV_CACHE_DIR`）から、sandbox の外で動きます。sandbox のコマンドからそこへ書けないようにしてください。sandbox の書き込みの許可に入れず、`~` で起動するセッションでは `denyWrite` に足します。そこで書き換えられたコードは、次に xlide が起動したときに、あなたの権限で動きます。`--python 3.15` で uv が選ぶ Python（`uv python find 3.15` で確かめられます）も同じで、キャッシュの外にあることがあります。
- macOS だけです。xlide の Windows 向けの live 系のツールは使いません。
- スキルは Read の deny を `workbook-intake-read-check.xlsx` という 1 つの名前で確かめるので、フォルダより狭い deny（例: `Read(~/workbook-intake/**/*.xlsx)`）は、正しい規則と見分けられません。規則は、[必須の設定](#required-settings)のとおりフォルダ全体に書いてください。
- 守りの対象外: このプラグインなしで xlide を使う人、Google Sheets のコネクタ。

<a name="troubleshooting"></a>

## トラブルシューティング

入力の確認のフックが返す文（`workbook-intake: consent=...`、`warnings_ack=...`）。記録できたときは `consent=recorded; check=<状態>; failures=...; warnings=...` か `warnings_ack=recorded` です。記録されなかったときの `reason=` は次のとおりです。

| 理由 | 意味 |
| --- | --- |
| `bad_input` | フックの入力かセッション ID を読めない |
| `question_mismatch` | 固定の質問と違う |
| `not_confirmed` | 答えが「確認した」「続ける」ではない |
| `path_not_absolute` | パスが絶対パスではない |
| `intake_dir_invalid` | 受取用フォルダがない、シンボリックリンク、`/`、またはパスに `:` を含む |
| `outside_intake` | ファイルが受取用フォルダの外にある |
| `not_regular_file` | 通常のファイルではない |
| `unsupported_extension` | 対象外の拡張子 |
| `file_too_large` | 100 MiB を超える |
| `path_not_canonical` | パスが実体のパスと違う、または前後に空白か制御文字がある |
| `file_changed` | 検査のあいだにファイルが変わった |
| `consent_store_unavailable` | 記録を書けない（プラグインのデータの置き場所がない、または記録を最後まで書けなかった） |
| `no_consent` | このファイルの中身に、入力の確認の記録がない |
| `internal_error` | フックの想定外のエラー |

xlide を守るフックの拒否（`workbook-intake: <理由>`。必要なら括弧の中に不合格か警告のコード）:

| 理由 | 意味 |
| --- | --- |
| `not_plugin_server` | このプラグインの xlide のツールではない（プロジェクトの xlide など）、または Claude Code がサーバーの由来を渡していない（古い版） |
| `tool_not_allowed` | 許可リスト（`hooks/allowed-tools.txt`）にないツール |
| `wrong_caller` | 呼び出し元が `workbook-intake:excel-analyst` ではない。スキルの最初の確かめでは、メインの会話からのこの拒否が 1 回返るのが正常 |
| `unexpected_path_argument` | `file_path` 以外にパスらしい引数がある |
| `calculation_not_allowed` | 計算を求める呼び出し（`calculate=true` など）。xlide の計算エンジンは上限なくメモリを使いうるため |
| `regex_not_allowed` | 正規表現の検索を求める呼び出し（`is_regex=true`）。xlide は渡された正規表現を時間の上限なしに当てるため |
| `query_too_long` | 256 文字を超える検索の文字列（`query`）。大文字小文字を区別しない検索の手間は、本文の長さと文字列の長さの掛け算で増えるため |
| `agent_teams_enabled` | エージェントのチームが有効（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` が空でない値を持つ）。切ってから Claude Code を起動し直してください |
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

スキルが最初の確かめで止まり、`xlide_doctor` の結果が返ったか、許可の確認が出たときは、このセッションで xlide を守るフックが動いていません。どの設定ファイルでも `disableAllHooks` が設定されているとき、または管理設定の `allowManagedHooksOnly` が有効なときに、フックは止まります（[制限](#limitations)を見てください）。フックが動くまで、このプラグインを使わないでください。ほかの理由で拒否されたときは、上の表を見てください。スキルが Read の確かめで止まったときは、受取用フォルダへの `Read(...)` の deny がないか、フォルダに当たっていません。[必須の設定](#required-settings)のとおりに足してください（別のフォルダなら `Read(//abs/path/**)` の形）。その Read の許可の確認が出たときは、許可しないでください。Read をセッション全体で止めている（例: `--disallowedTools Read`）ときも、Read の確かめは deny の拒否を返さないので、スキルは止まります。Read を止めずに、[必須の設定](#required-settings)の deny を足して起動してください。スキルが最初の確かめで、Agent ツールに `name` か `team_name` の引数があるために止まったときは、エージェントのチームが有効です。`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` を外すか空にし、`--agent-teams` を付けずに、Claude Code を起動し直してください。スキルは、Agent ツールの定義が見えないときも止まります。そのセッションでは、どのみちサブエージェントを起動できません。

`doctor.sh` の項目: `macos`（macOS ではない）、`uvx`（uv が PATH にない）、`python3`（Command Line Tools がない、またはその python が root の持ち物でない）、`sandbox_exec`（`/usr/bin/sandbox-exec` がない）、`intake_dir_protected`（Bash による受取用フォルダの一覧を sandbox が拒否しなかった。必須の設定がない、sandbox が無効、フォルダがない）。xlide のツールが見えないときは、uv がない、初回の取得に失敗した、プロジェクトの `xlide` にプラグインのものが外された、のどれかです（[プロジェクトの xlide](#project-xlide)を見てください）。

<a name="maintenance"></a>

## メンテナンス

作者は、プライベートの時間が許す範囲で保守します。定期的な更新も、Issue や PR への返事も、約束はしません。

- 版を固定しています（xlide-mcp 1.2.4 と依存 4 つ）。それらにセキュリティの修正が出ても、作者が固定を上げるまでは入りません。ほかの依存は固定していません。uv が環境を作るとき（後の起動で作り直すこともあります）に解決するので、それらの修正（とほかの新しい版）は、固定を上げなくても入ります。
- マーケットプレイスをコミットの SHA で固定し、自動更新を切っておいてください。SHA を動かす前に、差分を読んでください。
- 急ぐときは、リポジトリを fork して、自分で固定を上げてください（MIT）。
- 作者の手順は [docs/runbooks/maintenance.md](docs/runbooks/maintenance.md) にあります（日本語）。

<a name="license"></a>

## ライセンス

MIT ライセンスです。[LICENSE](LICENSE) ファイルを見てください。

[xlide-mcp](https://github.com/WilliamSmithEdward/xlide_mcp) の作者と、その土台のライブラリの作者に感謝します。どれも MIT です。このリポジトリには含まれず、サーバーの起動時に `uvx` が PyPI から取得します。
