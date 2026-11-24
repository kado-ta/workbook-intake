---
status: done
created: 2026-11-25
---

<a name="title"></a>

# workbook-intake: xlide 1.2.4 と pyofficeeditor 0.4.1 のブックの読み方

<a name="related"></a>

## 関連

- 前の調査: [research-plugin-behavior.md](research-plugin-behavior.md)（ツールの一覧と許可リスト）
- 設計: [design.md](design.md)
- 対象の検査: `scripts/check_workbook.py`

<a name="summary"></a>

## 要約

- 許可したツールは、1 つのファイルを 4 通りの ZIP の読み手で読む。pyofficeeditor の `ZipArchive`（シートのツール）、pyopenvba の Power Query 用の `OpcFile`（クエリのツール）、Python 3.15.2 の `zipfile`（VBA のツールと `xlide_list_shapes`）、DataMashup の中の小さな読み手。検査は Python 3.9.6 の `zipfile` で読む。`xlide_project_info` は 3 通りの読み手で、`xlide_list_shapes` は 2 通りの読み手で、同じファイルを読む。
- 読み手の間で、オフセットの基準、重複名の勝ち方、名前の付け替え（Unicode Path、0x7075）、ZIP64 の判定が違う。検査が、4 つの読み手が同じ部品を同じバイトで見る条件を自分で確かめないと、どれかと食い違う。
- pyofficeeditor の XML の読み手は独自のもので、名前空間を処理せず、属性をローカル名の最初の一致で引く（`xmlns:Target` も `Target` として拾う）。ルート要素の前後の文字、遅い XML 宣言、重複属性を許す。DOCTYPE は拒否する。文字列は `_xHHHH_` を文字に戻してから返し、CDATA の中身は返さない。
- 確かめた範囲で、検査の判定が xlide と食い違う形は、背景の 3 つ（中央ディレクトリが 2 つあるファイル、最初の `<` より前の文字、`\` を含む Target）のほかに 5 つある。名前が `/` で終わる部品（検査は飛ばす）、`//` を含む Target、`xmlns:Target` と接頭辞付きの属性、`_xHHHH_`、Python の版で違う 0x7075 の扱い。
- 検査に要ることは [検査に求められること](#requirements) にまとめた。

<a name="method"></a>

## 調べ方

- 読んだもの: xlide 1.2.4 のソース（`tmp/xlide-src/xlide_mcp`）、uv のキャッシュ（`~/.cache/uv/archive-v0/<id>/lib/python3.15/site-packages/`）の pyofficeeditor 0.4.1 と pyopenvba 6.6.0、CPython 3.15.2 と 3.9.6 の `zipfile`。
- 動く環境（事実）: xlide は uv の環境の `bin/python`（Python 3.15.2、expat 2.9.0）で動く。検査は Command Line Tools の python3（Python 3.9.6、expat 2.2.8）で動く（`hooks/guard-xlide.sh:8-12`、`hooks/intake_common.py:90-105`）。
- 確かめたこと: 中立な目印（`MARKER` と U+200B）だけを入れた小さなブックを `$TMPDIR` に作った。uv の環境の Python で pyofficeeditor に読ませ、検査を Command Line Tools の python3 で直接（Seatbelt なしで）動かした。結果は [確かめた挙動](#probe)。
- 書き方: 行番号は、パッケージのルートからの相対パスで書く（`pyofficeeditor/_zip.py:201`、`xlide_mcp/paths.py:30`）。CPython は `zipfile/__init__.py`（3.15）と `zipfile.py`（3.9）と書く。コードから言えないことには「推測」と書く。

<a name="readers"></a>

## 読み手の一覧

| 読み手 | 場所 | 使う側 |
| --- | --- | --- |
| `ZipArchive` と独自の XML | `pyofficeeditor/_zip.py`・`_xml.py`・`opc.py` | シートのツール、`xlide_project_info` のシートの要約、`xlide_list_shapes` の位置と状態 |
| `OpcFile` | `pyopenvba/powerquery/_opc.py` | クエリのツール、`xlide_project_info` のクエリの要約 |
| DataMashup の中の `Package` | `pyopenvba/powerquery/_package.py:84-120` | 同上（ローカルヘッダーを先頭から順にたどる） |
| `zipfile`（3.15） | `pyopenvba/_host.py:901-906`、`xlide_mcp/xlsx.py:418-441` | VBA のツール、`xlide_project_info` の VBA、`xlide_list_shapes` |
| `zipfile`（3.9）と expat 2.2.8 | `scripts/check_workbook.py` | 検査 |

<a name="zip"></a>

## ZIP

<a name="zip-eocd"></a>

### 1. EOCD の探し方と ZIP64

- `ZipArchive` は `data.rfind(_EOCD_SIG)` で、ファイル全体から最後の署名を探す（`pyofficeeditor/_zip.py:201`）。最後の 22 バイトだけを見ることも、64 KiB の窓に絞ることもしない。確かめるのは、EOCD の 22 バイトがファイルに収まることだけ（`:202-206`）。
- 注釈は `data[eocd + 22 : eocd + 22 + comment_len]` を取るだけで（`:214`）、注釈の終わりとファイルの終わりが合うかは確かめない。注釈の後ろの余りも、宣言より短い注釈も通る。注釈の中に署名があれば、そちらが EOCD になる。
- ZIP64 は読まない。EOCD より前のどこかに `PK\x06\x07` があれば、部品の中身の中でも、ファイルを拒否する（`:207-211`、probe の t13）。中央のエントリの大きさかオフセットが 0xFFFFFFFF でも拒否する（`:251-254`）。
- `OpcFile` も `raw.rfind(_END)` で最後の署名を使う（`pyopenvba/powerquery/_opc.py:81`）。ZIP64 は、EOCD の 20 バイト前に locator があるときだけ拒否する（`:84-87`）。0xFFFFFFFF は確かめない。
- `zipfile` は、3.15 も 3.9 も、最後の 22 バイトが注釈なしの EOCD ならそれを使う。違えば、最後の 64 KiB と 22 バイトの中から最後の署名を探す（3.15 `zipfile/__init__.py:358-385`、3.9 `zipfile.py:275-296`）。ZIP64 は読む（3.15 `zipfile/__init__.py:285-343`）。

<a name="zip-offsets"></a>

### 2. オフセットとエントリ数

- `ZipArchive` は、EOCD の 10 バイト目からを、総エントリ数・中央ディレクトリの大きさ・そのオフセット・注釈の長さとして読む（`pyofficeeditor/_zip.py:213`）。ディスク番号と「このディスクのエントリ数」は読まない。
- 中央ディレクトリは EOCD のオフセットの位置から（`:221`）、ローカルヘッダーは中央に書かれたオフセットの位置から読む（`:266-273`）。どちらもファイルの先頭からの絶対の位置で、前置きのデータの分を足さない。
- エントリ数は EOCD の総エントリ数で決まる（`:222`）。中央ディレクトリの大きさは、各エントリの固定部 46 バイトが範囲に収まるかにだけ使う（`:223-226`）。名前・extra・コメントが範囲を越えても、件数の後ろに余りがあっても通る。オフセットと大きさの和が EOCD の位置と合うかは確かめない。
- `OpcFile` も絶対の位置で読み、件数は EOCD の総エントリ数を使い、大きさは読まない（`pyopenvba/powerquery/_opc.py:88-91`）。
- `zipfile` は「EOCD の位置 − 大きさ − オフセット」を前置きの長さ（`concat`）とし、中央ディレクトリの開始とローカルヘッダーのオフセットに足す（3.15 `zipfile/__init__.py:272-283,1577-1580,1624`、3.9 `zipfile.py:1325-1336,1381`）。件数は使わず、大きさを使い切るまで読む（3.15 `:1589`、3.9 `:1346`）。
- よって、前置きがあるファイル（中央ディレクトリが 2 つあるものを含む）では、`ZipArchive`・`OpcFile` と `zipfile`（検査、VBA のツール、`xlide_list_shapes`）とで、読む部品が分かれる。前置きがなく、件数と大きさが合うファイルでは、同じ位置を読む。

<a name="zip-local"></a>

### 3. データの位置、大きさ、ローカルヘッダーの照合

- データの開始は、ローカルヘッダーの名前の長さと extra の長さで決まる（`pyofficeeditor/_zip.py:277-282`）。`OpcFile`（`_opc.py:104-105`）と `zipfile` も同じ。
- 圧縮後の大きさ・CRC・展開後の大きさは、中央の値を使う（`_zip.py:283-287`）。ローカルの値は、書き戻しのために、違うときだけ控える（`:317-321`）。
- データ記述子（bit 3）は、後ろの 12 か 16 バイトを書き戻し用に取るだけで、大きさは中央の値を信じる（`:289-301`）。
- ローカルヘッダーは署名だけを確かめる（`:270-273`）。名前・フラグ・圧縮方式・版は中央と照らさない。暗号化のフラグ（bit 0）も見ない。エントリ同士の重なりも確かめない。
- 展開は `zlib.decompress(self.stored, -15)` で一度に行い、長さと CRC を中央の値と照らす（`:127-148`）。`OpcFile` は長さも CRC も照らさない（`_opc.py:59-67`）。
- `zipfile` は、ローカルヘッダーの名前が中央の名前と違えば拒否する（3.15 `zipfile/__init__.py:1793-1796`、3.9 `zipfile.py:1544-1547`）。3.15 は、エントリが次のエントリか中央ディレクトリに重なっても拒否する（`zipfile/__init__.py:1798-1810`）。3.9 にこの確認はない。

<a name="zip-names"></a>

### 4. 重複名、圧縮方式、上限

- `ZipArchive` の名前の照合は、大文字小文字を区別する完全一致で、中央ディレクトリの順で最初のものが勝つ（`pyofficeeditor/_zip.py:185-187,427-450`、probe の t7）。`OpcFile` も最初が勝つ（`_opc.py:132-139`）。
- `zipfile` は `NameToInfo` に後から上書きするので、最後のものが勝つ（3.15 `zipfile/__init__.py:1626`、3.9 `zipfile.py:1383`）。`xlide_list_shapes` の読み手は全エントリを読み、名前の辞書に後から上書きする（`xlide_mcp/xlsx.py:431-435`）。
- 名前は、bit 11 があれば UTF-8、なければ cp437 で読む（`_zip.py:264`。`zipfile` も同じ）。`OpcFile` は bit 11 を見ず、いつも UTF-8 で読む（`_opc.py:98`）。
- NUL を含む名前は、`zipfile` が NUL の前で切る（3.9 `zipfile.py:346-350`、3.15 `zipfile/__init__.py:404-412`）。`ZipArchive` は切らない。
- **Python 3.15 の `zipfile` は、中央の extra に Unicode Path（0x7075）があり、その CRC が元の名前と合えば、名前をその値に置き換える**（`zipfile/__init__.py:604-612`）。3.9 の `_decodeExtra` は ZIP64 しか扱わない（`zipfile.py:460-470`）。`ZipArchive` も置き換えない（probe の t8）。
- 圧縮方式は 0 と 8 だけで、ほかは部品を読むときに拒否する（`_zip.py:127-140`）。開くときではないので、読まない部品の方式は問われない。
- 大きさと圧縮率の上限はない。ファイル全体を `read_bytes()` で読み（`pyofficeeditor/opc.py:364-368`）、部品は一度に展開する。DataMashup の中の `Package` だけは、宣言された大きさに 1 バイトを足した分までしか展開しない（`pyopenvba/powerquery/_package.py:104-109`）。

<a name="tools"></a>

### 5. ツールごとの読み手と部品

| ツール | 読み手 | 読む部品 |
| --- | --- | --- |
| `xlide_project_info` | `zipfile`（3.15）、`OpcFile`、`ZipArchive`（3 回開く） | `xl/vbaProject.bin` と署名の部品の名前、`customXml/itemN.xml`、ワークブックとシートの一式 |
| `xlide_validate_project`・`xlide_list_modules`・`xlide_read_module`・`xlide_list_procedures`・`xlide_search_modules`・`xlide_analyze`・`xlide_list_references`・`xlide_list_forms`・`xlide_read_form` | `zipfile`（3.15） | 固定名の `xl/vbaProject.bin` だけ |
| `xlide_list_queries`・`xlide_read_query` | `OpcFile` と `Package` | `customXml/itemN.xml` と、その中の DataMashup |
| `xlide_list_sheets`・`xlide_read_cells`・`xlide_evaluate_formula`・`xlide_check_cells`・`xlide_page_setup` | `ZipArchive` | [8](#opc-parts) の表のとおり |
| `xlide_list_shapes` | `zipfile`（3.15、全部品を読む）と `ZipArchive` | 固定名の `xl/workbook.xml`・`xl/_rels/workbook.xml.rels`、シート、描画、VML、ctrlProp |
| `xlide_doctor`・`xlide_rules` | なし | なし |

- `xlide_project_info` の VBA は `pyopenvba.ExcelFile` で開く（`xlide_mcp/tools/discovery.py:132`、`hosts.py:237-250`）。`ExcelFile` は `zipfile.ZipFile(io.BytesIO(raw))` で開き（`pyopenvba/_host.py:901-906`）、`xl/vbaProject.bin` を名前で読む（`pyopenvba/excel.py:34`、`_host.py:906,973`）。署名は、`xl/_rels/vbaProject.bin.rels` を大文字小文字を無視して探し、正規表現で読む（`pyopenvba/_package_signature.py:43-64`、`xlide_mcp/project.py:502-531`）。クエリは `PowerQueryWorkbook` で開く（`tools/discovery.py:413-423`）。シートは `cells.sheets`・`named_ranges`・`chart_sheets` が、それぞれ pyofficeeditor で開く（`tools/discovery.py:426-440`、`cells.py:162-192`）。
- VBA のツールは `require_readable` で `.xlsx` を拒否し（`hosts.py:213-219`）、`.xlsm`・`.xlam`・`.xlsb` を `ExcelFile` で開く（`tools/modules.py:94-98,161-164,260-263,311-323`、`tools/analysis.py:83-93`、`tools/catalog.py:67-74`、`tools/forms.py:63-65,140-142`、`tools/discovery.py:186-198`）。CFB の中だけを読み、ほかの部品は読まない（`pyopenvba/_host.py:268-286,388-392`）。
- クエリのツールは、名前が `customXml/item(\d+).xml` に合い（`pyopenvba/powerquery/workbook.py:62`）、`DataMashup` のバイト列を含み、ルート要素が DataMashup の名前空間の、最初の部品を使う（`:99-113,318-322`）。関係（rels）も `[Content_Types].xml` も使わない。ルート要素は ElementTree で確かめ、中身は正規表現で切り出して base64 を戻す（`:87-96`）。中の `Formulas/Section1.m` とメタデータ（ElementTree、`_metadata.py:467-471`）を読む（`workbook.py:278-285`）。
- シートのツールは `excel_with_sheets` で `.xlsx`・`.xlsm`・`.xlam` に限る（`tools/sheets.py:688-700`、`hosts.py:46`）。`.xlsb` には Windows の Excel が要り、macOS では拒否する（`grid.py:65-73`）。各ツールは `cells.open_workbook` で開く（`cells.py:107-119`、`tools/sheets.py:57-62,127-134,203`、`tools/ranges.py:65-68`、`tools/features.py:500-526`）。
- `xlide_list_shapes` は、`read_sheet_shapes` が xlide 自身の `xlsx.Workbook` で（`shapes.py:116-126`）、`control_states` が pyofficeeditor で読む（`shapes.py:748-768`）。
- `.xltx` は `host_info` が拒否し（`hosts.py:69-75,120-128`）、`.xltm` は VBA もシートもクエリも読まない（`hosts.py:28,42,46,51`）。検査はこの 2 つを受け付ける（`scripts/check_workbook.py:19`）が、xlide は読まない。

<a name="xml"></a>

## XML

<a name="xml-reader"></a>

### 6. XML の読み手と、許すもの

pyofficeeditor の読み手は独自の再帰下降のもので（`pyofficeeditor/_xml.py:576-729`）、expat も ElementTree も使わない。

<a name="xml-encoding"></a>

#### 文字コード

- BOM（UTF-8・UTF-16LE・UTF-16BE）があれば、それに従う。BOM がなければ、先頭 2 バイトが `<\0` なら UTF-16LE、`\0<` なら UTF-16BE、ほかは UTF-8 とする（`:65-87`）。復号は厳密で、失敗すれば拒否する（`:544-547`）。
- 宣言の `encoding` は、BOM の後の文字列が `<?xml` で始まるときだけ見て、検出と族（UTF-8 か UTF-16 か）が違えば拒否する（`:90-107,549-555`）。宣言が先頭になければ、何を宣言していても見ない（probe の t6d）。

<a name="xml-edges"></a>

#### 先頭と末尾

- 最初の `<` より前の文字は、何であっても読み飛ばして prolog に入れる（`:600-606`、probe の t6f）。prolog の処理命令やコメントの間の文字も、同じループで読み飛ばす（`:602-610`）。
- XML 宣言は prolog のどこにあってもよく、いくつあってもよい（`<?` は処理命令として読み飛ばす。`:607-608`）。
- ルート要素の後ろは解析せず、そのまま epilog として持つ（`:624`）。文字や 2 つ目の要素があっても通る（probe の t6a）。

<a name="xml-dtd"></a>

#### DTD と実体

- prolog の `<!DOCTYPE` と `<!doctype` は拒否する（`:611-616`）。ほかの `<!` も、prolog でも要素の中でも拒否する（`:617-618,726-727`）。DTD は一切処理しない（`:28-38`）。
- 実体は、定義済みの 5 つと数値の文字参照だけを戻す。ほかの名前付きの実体は、値を読むときに拒否する（`:110-133`）。数値の値は確かめないので、`&#0;` は NUL になる（`:121-124`）。
- `&` の後ろが実体の形でなければ、そのまま文字として残す（`:61` の正規表現に合わないため）。

<a name="xml-elements"></a>

#### 要素と属性

- 名前は、空白・`/`・`>`・`=` 以外の文字の並び（`:53-54`）。終了タグは開始タグとの完全一致を求める（`:708-710`）。入れ子は 256 段まで（`:51,636-637`）。
- 属性は、値を引用符で囲むことだけを求める。属性の間の空白、重複、値の中の `<` は確かめない（`:672-694`、probe の t6e）。
- 名前空間を処理しない。接頭辞のない名前で引くと、接頭辞を除いたローカル名で照らす（`:174-190`）。属性の `get` は、ローカル名が合う最初の属性の値を返す（`:360-364`）。`xmlns:Target` のローカル名も `Target` なので、`Target` より前にあれば、そちらの値になる（probe の t1）。接頭辞付きの名前（`r:id` など）で引くと、修飾名の完全一致を求める。
- 属性の値は、改行と TAB を空白にしてから、実体を戻す（`:157-167`）。

<a name="xml-text"></a>

#### 文字列

- 要素の `.text` は、直下の文字のノードだけをつなぐ。CDATA・コメント・処理命令は含めない（`:480-487,717-725`、probe の t6c）。
- Excel の層は、共有文字列やシート名などを、`_xHHHH_` から文字に戻して返す（`pyofficeeditor/excel/_xstring.py:32,44-55`、`_sharedstrings.py:173-176`、`workbook.py:1251-1255`、probe の t5）。
- 共有文字列は、`si` の直下に `t` があればその 1 つだけを返し、なければ `r` の中の `t` をつなぐ。`rPh` は返さない（`_sharedstrings.py:173-176`）。

<a name="xml-others"></a>

#### ほかの読み手と検査

- `xlide_list_shapes` の `xlsx.Workbook` は、UTF-8 として復号し（不正なバイトは置き換える。`xlsx.py:445-453`）、正規表現で走査する（`:67-109`）。`<?` と `<!` は `>` まで読み飛ばす（`:78-84`）ので、DOCTYPE も実体を展開せずに飛ばす。名前は修飾名の完全一致で（`x:sheet` は `sheet` に当たらない）、重複した属性は後のものが勝つ（`:104-107`）。
- VML は正規表現で読む（`shapes.py:327-391`）。Power Query は ElementTree（expat 2.9.0）を使う（`pyopenvba/powerquery/workbook.py:109-113`、`_metadata.py:467-471`）。
- 検査は、部品を ElementTree の `XMLParser`（expat 2.2.8）に流す（`scripts/check_workbook.py:253-266`）。先頭 4 KiB の中で、BOM と空白の後が `<` でない部品は、XML として読まず、何も数えない（`:148-162,255-259`）。読めない部品は `strings_not_checked` として数える（`:267-272`）。

<a name="opc"></a>

## OPC

<a name="opc-resolve"></a>

### 7. ワークブックの見つけ方と、Target の解決

- `[Content_Types].xml` は、開くときに名前の完全一致で存在することだけを求める（`pyofficeeditor/opc.py:349-353`）。ワークブックを探すのには使わない。
- ワークブックは、`_rels/.rels`（完全一致）のルート要素の直下の `Relationship` から探す（`opc.py:247-249,455-477`）。ルート要素の名前も、`Relationship` の接頭辞も確かめない。その中で `Type` が transitional の officeDocument と完全一致するものを、ちょうど 1 つ選ぶ（`:45,262-278,479-482`）。0 か 2 つ以上なら拒否する。strict の型は数えない。決め打ちの名前への切り替えはない。
- 外部かどうかは、`TargetMode` が `External` と完全一致するかで決める（`:217-219`）。小文字の `external` は、内部の部品として解決される。
- 解決の規則（`opc.py:50-95`）:
  - `/` で始まる Target は絶対として `normalize_part_name` に渡す。`\` を `/` にし、先頭の `/` をすべて落とし、`./` を含むか `/.` で終わるときだけ、`.`・`..`・空のセグメントを畳む（`:53-56`）。それ以外は畳まないので、`//` も末尾の `/` も残る（probe の t4・t3）。
  - 相対の Target は、元の部品のフォルダーとつないで `_collapse` に渡す。空と `.` のセグメントを落とし、`..` で 1 つ戻り、ルートより上に出れば拒否する（`:59-70,94-95`）。ここでは `\` を直さない。ただ、部品を引く `xml()`・`read()`・`has_part()` がもう一度 `normalize_part_name` を通すので、結果として `\` は `/` になる（`:383-395,433-443`、probe の t11）。
  - パーセント符号は戻さない（probe の t12）。`#` から後ろも外さない。照合は大文字小文字を区別する（`_zip.py:427-442`）。
- シートは、ワークブックのルート要素の直下の最初の `sheets` の、直下の `sheet` から関係を引く。`r:id`（修飾名の完全一致）がなければ、ローカル名 `id` の最初の属性を使う（`excel/workbook.py:206-230`）。関係の種類は確かめず、chartsheet でなければ、どの種類でもワークシートとして読む（`:227-230`）。
- 非表示の判定は、名前の合う最初の `sheet` の、ローカル名 `state` の最初の属性が、`hidden`・`veryHidden` と完全一致するかで決める（`excel/worksheet.py:1494-1501`。xlide は `cells.py:378-402`）。接頭辞付きの `x:state` でも当たる（probe の t2）。
- `xlide_list_shapes` の読み手は、ルートの rels を見ずに、`xl/workbook.xml` と `xl/_rels/workbook.xml.rels` を名前で読む（`xlsx.py:465-468`）。Target は、先頭の `/` を落とすか、相対なら空と `.` を落とし、ルートより上に出る `..` は黙って捨てる。`\` は直さない（`:1032-1046`）。
- 検査は、ルートの rels の `Type` が `/relationships/officeDocument` で終わる関係を、深さを問わず最大 100 集める（`scripts/check_workbook.py:193-206`）。`posixpath.normpath` で畳み、大文字小文字を無視して引く（`:276-281`）。名前が `/` で終わる部品は、ディレクトリとして飛ばし、XML として読まない（`:295-296`）。

<a name="opc-parts"></a>

### 8. ツールが XML として読む部品

| 部品 | 見つけ方 | 読むツール |
| --- | --- | --- |
| ルートの rels | 名前 `_rels/.rels` | pyofficeeditor で開くすべて |
| ワークブック | ルートの officeDocument の関係 | 同上。`xlide_list_shapes` は固定名の `xl/workbook.xml` も読む |
| ワークブックの rels | `<フォルダー>/_rels/<名前>.rels`（`opc.py:73-82`） | 同上 |
| シート（ワークシートとグラフシート） | `sheet` の r:id。関係の種類を問わない | 開くたびに全シート（`workbook.py:214-230`） |
| 共有文字列 | ワークブックの関係のうち、種類が sharedStrings の最初のもの（`workbook.py:924-932,1041-1046`） | `xlide_read_cells` など |
| スタイルとテーマ | 種類が styles・theme の最初のもの（`workbook.py:912-921,954-959`） | 書式付きの文字（`include=text`）、リッチテキスト |
| 定義名 | ワークブックの `definedNames`（`workbook.py:615-626`） | `xlide_list_sheets`、`xlide_project_info`、`xlide_page_setup`（印刷範囲。`excel/_pagesetup.py:26`、`worksheet.py:4172-4191`）、計算 |
| テーブル | シートの `tableParts` の r:id（`worksheet.py:1214-1226`） | 計算（推測: 構造化参照のため） |
| 外部リンク | `externalReferences` の r:id。関係の種類を問わない（`excel/_externals.py:42-58`） | 計算（`excel/_calc/engine.py:277`） |
| ピボットテーブル | シートの関係のうち、種類が pivotTable のすべて（`excel/_pivots.py:68-75`） | `xlide_list_sheets`、`xlide_project_info` |
| 描画とグラフ | シートの関係のうち、種類が drawing のもの（`worksheet.py:2622-2629`）。`xlsx.py` の側は `<drawing r:id>` か種類（`shapes.py:397-411`） | `xlide_list_shapes`、グラフシートの要約 |
| VML と ctrlProp | `legacyDrawing` の r:id か種類が vmlDrawing（`worksheet.py:2578-2606`）、`controls` の r:id（`:3695-3736`、`shapes.py:283-324`） | `xlide_list_shapes` |
| customXml | 名前 `customXml/itemN.xml` | クエリのツール、`xlide_project_info` |
| `xl/vbaProject.bin`（XML ではない） | 固定名 | VBA のツール |

推測: コメントとスレッドのコメントは、許可したツールからは読まれない（読む `xlide_manage_comment` は許可していない）。

<a name="paths"></a>

## パス

<a name="paths-resolve"></a>

### 9. `resolve_path`

- 引数なしの `str.strip()` で、前後の `str.isspace()` の空白をすべて落とす。空なら拒否し、NUL を含めば拒否する（`xlide_mcp/paths.py:30-34`）。
- `Path(text).expanduser()` で先頭の `~` と `~user` を展開し（`:36`）、相対のパスは最初のルートの下に置く（`:37-39`）。
- `candidate.resolve()`（strict なし）で、シンボリックリンクをたどり、`..` を畳む。存在しない末尾も通す（`:41-44`）。
- ルートの内側かを、`Path` の部品の単位で確かめる（`:46-52,101-102`）。`allow_outside_roots` なら確かめない。最後に、存在して通常のファイルであることを確かめる（`:54-59`）。
- Unicode の正規化も、大文字小文字の畳み込みもしない。
- ツールは、確かめた後のパスを何度も開き直す。`xlide_project_info` は pyopenvba・`OpcFile`・pyofficeeditor 3 回で、最大 5 回開く（`tools/discovery.py:132,155-158,426-432`）。各読み手は、そのつど `read_bytes()` か `zipfile.ZipFile` で読む（`pyopenvba/_host.py:902`、`pyopenvba/powerquery/workbook.py:278`、`pyofficeeditor/opc.py:368`）。
- ガード（`hooks/intake_common.py:207-231`）は `strip` しない。先頭に空白があれば `isabs` で、末尾に空白があれば拡張子の確認で拒否するので、ガードが通す値では `strip()` は何も変えない。`~` で始まる値も `isabs` で拒否する。シンボリックリンクは、どちらも解決する（`os.path.realpath` と `Path.resolve`）。
- 推測: APFS は正規化の違う名前を同じファイルとして引くので、正規化をしないことによる食い違いは、macOS では起きにくい。
- 推測: 開き直しの間の差し替えは、検査では防げない（[design.md](design.md) の受け入れるリスクの TOCTOU と同じ）。

<a name="probe"></a>

## 確かめた挙動

`$TMPDIR` に作ったブックを、pyofficeeditor 0.4.1（Python 3.15.2）と検査（Python 3.9.6）に読ませた結果（2026-11-25）。

| 名前 | 作り | pyofficeeditor | 検査 |
| --- | --- | --- | --- |
| t1 | ルートの関係に `xmlns:Target="xl/other.xml"` を `Target` の前に置く。`xl/other.xml` のシートは非表示 | ワークブックは `xl/other.xml`、シートは非表示 | 通る。`hidden_sheet` なし |
| t1b | 同じく `x:Target`（接頭辞を宣言） | 同上 | 同上 |
| t2 | `sheet` に `x:state="hidden"` | 非表示 | 通る。`hidden_sheet` なし |
| t3・u1 | Target が `/xl/book.xml/`、部品の名前が `/` で終わる。共有文字列も `/xl/strings.xml/` | ワークブックは `xl/book.xml/`、A1 は `xl/strings.xml/` の値 | 通る。U+200B を入れても `invisible_characters` なし |
| t4 | Target が `/xl//workbook.xml`。`xl//workbook.xml` のシートは非表示、`xl/workbook.xml` は表示 | ワークブックは `xl//workbook.xml`、非表示 | 通る。`hidden_sheet` なし |
| t5 | 共有文字列が `_x004D_ARKER_x200B_` | `MARKER` と U+200B | 通る。`invisible_characters` なし |
| t6a | ルート要素の後ろに `tail<x/>` | 読む | `strings_not_checked` |
| t6b・u2 | UTF-16LE で BOM なし | 読む | 読む（`invisible_characters` が出る） |
| t6c・u3 | `t` の中身が CDATA | 空の文字列 | CDATA の中身を読む |
| t6d | コメントの後に `encoding="UTF-16"` の宣言（中身は UTF-8） | 読む | `strings_not_checked` |
| t6e | 空白のない属性、`state` の重複、値の中の `<` | 読む。最初の `state`（hidden）が勝つ | `strings_not_checked` |
| t6f | 先頭に `x` | 読む | 通る。何も数えない |
| t6g | `<!doctype sst>` | 拒否する | `strings_not_checked` |
| t7 | 同じ名前の共有文字列が 2 つ | 最初のもの。`zipfile` 3.15 は最後のもの | `unsafe_part_name` で失敗 |
| t8 | 名前 `xl/strings2.xml` に、0x7075 で `xl/sharedStrings.xml` | 名前は `xl/strings2.xml` | 名前は `xl/strings2.xml`。`zipfile` 3.15 だけが `xl/sharedStrings.xml` と読む |
| t11 | 相対の Target が `xl\workbook.xml`。シートは非表示 | `xl/workbook.xml` を読み、非表示 | 通る。`hidden_sheet` なし |
| t12 | Target が `xl/work%62ook.xml` | 部品がないとして拒否する | 通る |
| t13 | 無圧縮の部品の中に `PK\x06\x07` | ZIP64 として拒否する | 通る（制御文字で `strings_not_checked`） |

<a name="inferences"></a>

## 推測

- 推測: 0x7075 で別の名前を `xl/vbaProject.bin` に付け替えたエントリは、VBA のツール（`zipfile` 3.15）からはマクロとして読まれ、検査（3.9）からは別の名前に見えて、名前による `vba_project` の警告が出ない。仕組み（名前の付け替え）は t8 で確かめたが、VBA のツールでは試していない。
- 推測: Excel は名前空間を区別するので、`xmlns:Target` や `x:state` を xlide と同じには読まない。xlide と Excel の間でも、表示と読む内容が食い違いうる。Excel では試していない。
- 推測: 検査で XML の解析が途中で失敗すると、その部品の非表示のシートや関係の数は、失敗する前までの分しか数えない（`scripts/check_workbook.py:243-273` で、途中の `collector` を返すため）。警告は `strings_not_checked` だけで、非表示のシートや関係の警告が欠けたことは表さない。
- 推測: `xlide_read_query` の M と、VBA のツールが返すモジュールのソースは、検査の文字列の確認の対象にない（検査は `customXml/` を XML として読まず、`vbaProject.bin` は CFB なので文字列を見ない。`scripts/check_workbook.py:307-308`）。今は `power_query` と `vba_project` の警告だけが知らせる。

<a name="requirements"></a>

## 検査に求められること

xlide と同じ部品を同じバイトで見るために、検査がすべきこと。

- ZIP: EOCD がファイルの最後の 22 バイトにあり、注釈の長さが 0 であることを求める。
- ZIP: EOCD の 20 バイト前に ZIP64 の locator がなく、どのエントリの大きさとオフセットも 0xFFFFFFFF でないことを求める。
- ZIP: ディスク番号が 0 で、EOCD の「このディスクのエントリ数」と総エントリ数が等しいことを求める。
- ZIP: 中央ディレクトリのオフセットと大きさの和が、EOCD の位置にちょうど等しい（前置きのデータがない）ことを求める。
- ZIP: 中央ディレクトリを大きさのとおりに読み、総エントリ数と同じ件数で、ちょうど使い切ることを求める。
- ZIP: 各エントリのローカルヘッダーの署名、名前のバイト列、フラグ、圧縮方式が、中央のものと一致することを求める。
- ZIP: エントリの範囲（ローカルヘッダー、データ、データ記述子）が、互いにも中央ディレクトリとも重ならないことを求める。
- ZIP: 部品の中身は、ローカルヘッダーの名前と extra の長さの後ろから中央の圧縮後の大きさだけ取り、展開した長さと CRC を中央の値と照らす。
- ZIP: 名前は大文字小文字を区別して照らし、大文字小文字を無視して重複する名前は拒否する（今のまま）。
- ZIP: 名前に NUL、`\`、空のセグメント（`//`）、`.` や `..` のセグメント、先頭の `/` があれば拒否する。
- ZIP: 名前が `/` で終わるエントリは、ディレクトリとして飛ばさずに部品として検査するか、拒否する。
- ZIP: bit 11 がないのに ASCII 以外を含む名前と、bit 11 があるのに UTF-8 として正しくない名前を拒否する。
- ZIP: 中央かローカルの extra に Unicode Path（0x7075）を持つエントリを拒否する。
- ZIP: 圧縮方式が 0 と 8 以外のエントリと、暗号化のフラグを持つエントリを拒否する（今のまま）。
- ZIP: 上の条件は、検査の Python（3.9.6）の `zipfile` に任せずに、ファイルのバイト列から直接確かめる。
- OPC: ルートの rels の直下の `Relationship` のうち、`Type` が transitional の officeDocument と完全一致するものが、ちょうど 1 つであることを求める。
- OPC: 同じ要素の中に、ローカル名（`:` の後ろ）が同じ属性が 2 つ以上あれば、`xmlns:` の宣言を含めて拒否する。
- OPC: 属性は、接頭辞の有無を問わずローカル名で引く（`x:state` も `state` として扱う）。
- OPC: `TargetMode` が `External` と完全一致しない関係は、内部の部品への関係として解決もする。
- OPC: 内部の Target が `\`・`%`・`#`・`//` を含むか、`/` で終わるか、`.` や `..` のセグメントを含めば拒否する。
- OPC: ルートの officeDocument の Target が `xl/workbook.xml` に解決されることを求める（`xlide_list_shapes` は固定名で読むため）。
- OPC: 非表示のシートは、そのワークブックのルート要素の直下の最初の `sheets` の、直下の `sheet` の `state` が `hidden`・`veryHidden` と完全一致するかで数える。
- OPC: `sheet` と `externalReference` が r:id で指す部品は、関係の種類を問わずにたどり、`externalReference` の先は、種類と名前に関わらず外部リンクとして数える。
- XML: 部品の文字コードは、pyofficeeditor と同じ規則（BOM、BOM なしの `<\0` と `\0<` は UTF-16、ほかは UTF-8）で決め、厳密に復号する。
- XML: BOM の後、最初の `<` までに空白以外の文字がある部品は拒否し、空白だけなら長さに関わらず XML として検査する。
- XML: XML 宣言が先頭以外にある部品と、宣言が 2 つ以上ある部品を拒否する。
- XML: ルート要素の後ろに、空白・コメント・処理命令以外のものがある部品を拒否する。
- XML: expat で読めない部品は、`strings_not_checked` の警告ではなく、失敗にする。
- XML: 文字列は、`_xHHHH_` を文字に戻した後の形でも、不可視の文字と指示らしい文言を確かめる。
- 文字列: `xlide_read_query` の M と、VBA のモジュールのソースも文字列の確認の対象に入れるか、確かめていないことを警告の扱いで示す。
- パス: ガードは、`file_path` の前後に `str.isspace()` の空白があれば拒否する（xlide は `strip()` してから開くため。今は別の確認で結果として拒否している）。
