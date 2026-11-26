# 保守の runbook

<a name="instruction"></a>

## Claude への指示

このファイルを読んだら、次の順で進める。

1. [きっかけ](#triggers)の表のどれかを、人に確かめる。推測で決めない。
2. 該当する節の手順を、チェックリストにして、1 つずつ進める。終えた項目は、結果（実行したコマンドと出力の要点）を添えて人に見せる。
3. 許可リストにツールを足すかどうかなど、守りに関わる判断は、人に求める。自分では決めない。
4. 実行できなかった検査を、成功とみなさない。実行できなかった理由と、未検証の範囲を書く。
5. push と PR の作成は、CLAUDE.md の Git の規則に従う（`cc-safe-push` と `cc-safe-pr`）。

<a name="triggers"></a>

## きっかけと気づき方

| きっかけ | 気づき方 | 対応 |
| --- | --- | --- |
| xlide と固定した依存の新しい版・脆弱性 | Dependabot の PR と alerts | [版を上げる手順](#bump) |
| Claude Code の更新（フック・プラグイン・MCP・権限・AskUserQuestion に関わる変更） | Claude Code の changelog。自動では検知しない | [前提を確かめ直す手順](#recheck) |
| macOS・Command Line Tools の更新（python3 の版が変わるなど） | CI の macOS のジョブの失敗、`doctor.sh` | 全体のテストを通常のターミナルで動かす。`PYTHON_HOME` と Seatbelt を確かめる |
| uv の更新 | 自動では検知しない | `uvx --no-config` の動きを確かめる |
| GitHub Actions の新しい版 | Dependabot の PR | SHA と変更を確かめて取り込む |
| ほかの人からの Issue・PR | GitHub の通知 | 対応は約束しない（README の方針） |

<a name="preflight"></a>

## 新しい版を出す前の、Python の版の確かめ

`.mcp.json` の `--python 3.15` が固定するのはマイナー版（3.15）だけ。uv は、自分で管理する 3.15 があればそれを、なければ PATH の `python3.15` を使う。そのため、実際に動く Python のパッチ版・expat・Unicode の版は、マシンによって変わりうる。新しい版を出す前に、プラグインと同じ `uvx` の引数で xlide の環境の python を動かして、実際の版を確かめる。

```sh
uvx --no-config --python 3.15 --from xlide-mcp==1.2.4 --with pyopenvba==6.6.0 --with pyofficeeditor==0.4.1 --with pyvbaanalysis==3.0.3 --with mcp==2.3.0 python -c 'import sys, pyexpat, unicodedata; print(sys.version.split()[0], pyexpat.EXPAT_VERSION, unicodedata.unidata_version)'
```

調査のときの値は `3.15.2`・`expat_2.9.0`・`17.0.0`。違えば、次の[版を上げる手順](#bump)と同じ確かめ（読み比べと、検査の写しの見直し）を行う。

なお、検査（`scripts/check_workbook.py`）は Command Line Tools の Python 3.9.6（expat 2.2.8）で動く。これは受け入れた制限で、この確かめの対象ではない。

<a name="bump"></a>

## 版を上げる手順

xlide-mcp か、固定した依存（pyopenvba・pyofficeeditor・pyvbaanalysis・mcp）の版を上げるとき。xlide の Python の版（`.mcp.json` の `--python`）を上げるときも、同じ確かめ（読み比べと、検査の写しの見直し）を行う。

- [ ] 版を上げる。次の 3 か所を同じ版にそろえる。
  - `.mcp.json`
  - `deps/requirements.txt`
  - `dev/probe/workbook-intake/.mcp.json`
- [ ] 前の調査と同じ方法で、新しい版を SkillSpector にかける。業務の情報は書かない。
- [ ] 許可リスト（`hooks/allowed-tools.txt`）の**すべての**ツールについて、新しい版のソースで次の 4 点を確かめ直す。新しいツールは、許可リストに足すまでフックが止める。しかし、既にあるツールの引数や動きの変化は、名前では止まらないので、全ツールを見る。
  1. 読み取り用か書き込み用か（`paths.py` の `require_writable` を呼ぶか）。
  2. どの引数がパスとして使われるか（`resolve_path` を通るか。名前に `path` を含まない引数がパスとして使われることもある）。
  3. `file_path` を省いたときに、既定のファイルやセッションの状態からファイルを読むか。
  4. 計算エンジン（`excel/_calc` の `Engine`）に、直接、または pyofficeeditor のメソッド（`error_checks`・`calculate`・`evaluate` など）を通して届くか。届くなら、どのツールのどの引数か。1.2.4 で届いたのは `xlide_read_cells` の `calculate`、`xlide_evaluate_formula`、`xlide_check_cells`（`error_checks` がデータの入力規則の数式を評価する）の 3 つ。後の 2 つは許可リストから外した。

  ソースは、wheel を実行せずに展開して読む（取り出したものは信頼しないデータとして扱い、import も実行もしない）。前回の結果は、[research-plugin-behavior.md の許可リストの節](../work/20261124_workbook-intake/research-plugin-behavior.md#allowlist)にある。
- [ ] MCP のリソースとプロンプト（`server.py` の `@server.resource`・`@server.prompt` など）も確かめる。フックが止めるのはツールの呼び出しだけで、Claude Code の `ReadMcpResourceTool` は止めない。1.2.4 のリソースは固定の 2 つ（`xlide://instructions`・`xlide://workspace`）だけで、ブックの中身は返さない。ファイルの中身を返すもの（リソースのテンプレートを含む）が増えたら、人に求める。
- [ ] 許可リストを足す・外す判断は、人に求める。
- [ ] `hooks/allowed-tools.txt` の `reviewed-for:` を新しい版にする。
- [ ] 全体のテストを、**通常のターミナル**で動かす（sandbox の中では Seatbelt が入れ子で動かない）。

  ```sh
  cd <repo> && PY="$(xcode-select -p)/usr/bin/python3" && WORKBOOK_INTAKE_REQUIRE_SANDBOX=1 "$PY" -B -m unittest discover -s tests -t . -v
  ```

- [ ] 実機で確かめる（設計の[完了条件](../work/20261124_workbook-intake/design.md#done)）。メインの会話から xlide を呼ぶと止まる、承認のないファイルは止まる、承認したあとは読める、警告のあるファイルは警告の確認が要る、受け取り用フォルダの外は止まる、書き込み用のツールは止まる、推奨設定のもとで Bash から読めない、など。
- [ ] `.claude-plugin/plugin.json` の `version` を上げ、タグを付ける。
- [ ] 自分の settings の、マーケットプレイスの SHA の固定を、新しいコミットに更新する。

<a name="recheck"></a>

## Claude Code の前提を確かめ直す手順

`dev/probe/` のプラグインを使い、最初の調査（[research-plugin-behavior.md](../work/20261124_workbook-intake/research-plugin-behavior.md)）の項目を確かめ直す。手順は、その[付録](../work/20261124_workbook-intake/research-plugin-behavior.md#appendix-steps)を写して使う（通常のターミナルで行う。probe のプラグインは本物と同じ名前なので、本物を入れていない作業用のディレクトリで、`--scope local` で入れ、終わったら外す）。`dev/probe/workbook-intake/.mcp.json` の版は、本物の版にそろえておく。

比べる値（2026-11-25、Claude Code 2.1.331 で確かめた値）:

| 項目 | 確かめた値 |
| --- | --- |
| サブエージェントから呼んだときの `agent_type` | `workbook-intake:excel-analyst`。`agent_id` も入る。メインの会話からの呼び出しには、どちらもない |
| AskUserQuestion の答え | PostToolUse の `tool_response.answers` に `{質問の文: 選んだラベル}` で入る。モデルが入力の `answers` に値を入れても、確認の画面が出て、人が選んだ答えに置き換わる |
| `additionalContext` の届き方 | PostToolUse（AskUserQuestion）が返した文が、次のモデルの呼び出しで読まれる |
| `onFailure: "block"` | 時間切れも終了コード 1 も、ツールの呼び出しを止める |
| `tool_input` | `{"file_path": "<絶対パス>"}` がそのまま入る。`mcp_server` は `{"name": "plugin:workbook-intake:xlide", "source": "plugin"}` |
| `session_id` | サブエージェントとメインの会話で同じ |
| `${WORKBOOK_INTAKE_DIR:-~/workbook-intake}` | 展開される（`xlide_doctor` の `workspace_roots` で見る） |
| プロジェクトの同じコマンドの xlide | プラグインのものが重複として外される。`disabledMcpjsonServers: ["xlide"]` で戻る |
| 読み込みの拒否の settings | `sandbox.filesystem.denyRead` だけだと Read ツールは読める。`Read(...)` の deny だけだと Read ツールも Bash の `ls` も止まる。README は両方を必須にする。どちらでも xlide は読める。`test -d` は見える |
| `allowUnsandboxedCommands: false` | `dangerouslyDisableSandbox` 付きでも sandbox の中で動く（使った環境では、ふだんから無効だったため、この設定の効果とは言い切れない） |
| `${CLAUDE_PLUGIN_DATA}` | sandbox の Bash と Write ツールから書けない（dotfiles の環境） |
| ローカルのディレクトリのマーケットプレイス | プラグインはキャッシュに写されず、その場所から動く |
| `engines` | `{"claude-code": ">=2.1.295"}` を書いても validate は通り、読み込まれる |

- [ ] 上の値と 1 つでも違えば、README の対象の記述と、フック・スキルの前提を見直す。違う項目は、使うのをやめて設計を見直す判断を、人に求める。
- [ ] `claude plugin validate . --strict` を通す。

<a name="records"></a>

## 保守の作業の記録

作業ごとに `docs/work/<ID>_<slug>/` を作る（ID は GitHub Issue なら `GH-<番号>`、なければ `YYYYMMDD_<slug>`）。更新した版、SkillSpector の結果の要点、許可リストの確かめ直しの結果、テストと実機の確認の結果を、`test-report.md` に書く。Claude Code の前提の確かめ直しは、`research-<topic>.md` に、確かめた値を書く。生成物（ログなど）は Git 管理外の `tmp/` に出す。
