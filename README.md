# **YouTube Comments Pager \- README**

## **1\. プロジェクト概要**

「YouTube Comments Pager」は、YouTube Data APIから取得したRAW形式のJSONデータ（動画情報、チャンネル情報、コメントスレッド）を読み込み、整形されたHTMLページ（index.html）として出力するPythonスクリプトです。このツールは、特定のYouTube動画のコメントをオフラインで閲覧したり、カスタマイズ可能な形式でアーカイブしたりすることを目的としています。

生成されるHTMLページは表示専用であり、コメントの投稿機能やインタラクティブな要素は含まれません。

**バージョン**: 1.0

## **2\. 機能**

* 指定された動画IDに対応する動画情報（タイトル、説明、サムネイル、公開日時）を表示します。  
* 動画のチャンネル情報（アイコンとタイトル）を表示します。  
* コメントデータ（トップレベルコメントと返信コメント）をツリー形式で整形して表示します。  
* 親コメントと返信コメントの両方でコメント投稿者のチャンネルアイコンを表示します。  
* pager-template-maker ツールと連携し、表示する各要素（動画タイトル、動画チャンネル情報、説明、サムネイル、動画メタ情報、コメント投稿者名、コメント本文、コメントメタ情報、返信コメントの各要素）の表示/非表示をカスタマイズできます。  
* **ファイルダイアログを使って、youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> 形式の動画データフォルダを直接選択して処理できます。**  
* **生成された index.html と static フォルダは、選択した動画データフォルダ内に配置されます。**

## **3\. 使用方法**

### **3.1. 前提条件**

* Python 3.x  
* pip (Pythonのパッケージインストーラ)  
* 以下のPythonライブラリ: jinja2, tkinter (通常Pythonに標準で含まれていますが、システムによっては別途インストールが必要な場合があります)

pip install jinja2  
\# tkinter は通常Pythonに標準で含まれているため、別途インストールは不要です。  
\# ただし、Linux環境などでtkinterが不足している場合は、OSのパッケージマネージャーでインストールが必要な場合があります  
\# 例: sudo apt-get install python3-tk

### **3.2. 必要なフォルダとファイルの配置**

PyInstallerでビルドされた実行ファイルを使用する場合：  
実行ファイル（main.exeなど）があるディレクトリの直下に、以下のフォルダとファイルを配置してください。

* youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> 形式のデータフォルダ:  
  このフォルダ内に、以下のJSONファイルを配置します。  
  例: 実行ファイルのあるディレクトリ/rawdata/youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\>/ または任意の場所  
  * comments\_raw\_\<動画ID\>.json (例: comments\_raw\_9SAhwYXG4Uc.json)  
  * comment\_replies\_raw\_\<動画ID\>.json (返信Rawデータが保存されている場合)
  * video\_info\_raw\_\<動画ID\>.json  
  * channel\_info\_raw\_\<チャンネルID\>.json  
  * **注意**: これらのJSONファイルは、YouTube Data APIから直接取得したRAWデータ形式である必要があります。コメントスレッドデータは、commentThreads.listのRawレスポンスページを配列に格納し、各ページがitemsキーを持つ形式を想定しています。返信データは別ファイルに保存され、親コメントIDと返信Rawレスポンスページの配列で関連付けられます。  
  * **推奨**: これらのフォルダは、以前からの慣例として rawdata フォルダの直下に作成することを推奨します。ファイル選択ダイアログの初期ディレクトリが rawdata に設定されます。  
* **templates フォルダ**:  
  * 実行ファイルのあるディレクトリ/templates/pager-template.html (デフォルトテンプレート)  
  * 実行ファイルのあるディレクトリ/templates/example.html (カスタマイズされたテンプレートがあれば)  
* **static フォルダ**:  
  * 実行ファイルのあるディレクトリ/static/css/style.css  
* **default フォルダ**:  
  * 実行ファイルのあるディレクトリ/default/dummy\_comments.json  
  * 実行ファイルのあるディレクトリ/default/dummy\_video\_info.json  
  * 実行ファイルのあるディレクトリ/default/dummy\_channel\_info.json  
  * 実行ファイルのあるディレクトリ/default/pager-template.html  
  * 実行ファイルのあるディレクトリ/default/style.css  
  * （これらのファイルは、pager-template-maker の default フォルダからコピーしてください。）

Pythonスクリプトとして直接実行する場合（開発用）：  
youtube-comments-pager ディレクトリの直下に、上記のフォルダ構造（rawdata, templates, static, default）を作成し、それぞれのファイルを配置してください。youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> フォルダは rawdata フォルダ内に作成することを推奨します。

コメントスレッドRawファイルは複数ページを含む場合があります。ページャーは各ページのitemsを処理し、親コメントIDの重複は先に出現したレコードを採用して二重表示を避けます。返信Rawファイルは `parent_id` と `raw_responses` を持つレコードのリストです。返信Rawと親スレッド内の返信プレビューは返信IDで統合し、外部返信Rawが部分保存でもプレビューにしかない返信を保持します。返信IDが重複する場合も二重表示を避け、重複を警告します。最後に保存されたRawページに `nextPageToken` が残る場合は、後続ページが保存されていない可能性を警告しますが、scraper全体の取得状態は判定しません。コメントスレッドRawファイルが欠落・JSON不正の場合は、ダミーコメントへ置き換えずエラーとして扱います。

## **3.3. HTMLページの生成**

1. テンプレートのカスタマイズ（任意）:  
   もし表示要素をカスタマイズしたい場合は、pager-template-maker ツールを使用してください。  
   N:\\Documents\\(python\_scripts)\\pager-template-maker\\ ディレクトリで python main.py を実行し、GUIツールで表示項目を調整した後、「HTML保存」ボタンをクリックして example.html を保存してください。これにより、youtube-comments-pager\\templates\\example.html が更新されます。また、pager-template-maker\\default の内容を youtube-comments-pager\\default にコピーしてください。  
2. **main.py の実行**:  
   * Pythonスクリプトとして直接実行する場合（開発用）:  
     youtube-comments-pager ディレクトリ (例: N:\\Documents\\(python\_scripts)\\youtube-comments-pager\\) に移動し、以下のコマンドを実行します。  
     python main.py

   * PyInstallerでビルドされた実行ファイルを使用する場合:  
     上記「3.2. 必要なフォルダとファイルの配置」に従ってフォルダとファイルが配置されていることを確認し、実行ファイル（例: main.exe）を直接実行します。

プログラムが起動すると、**「動画データフォルダを選択してください」というファイルダイアログが表示されます。** JSONデータが格納されている youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> 形式のフォルダを選択してください。

### **3.4. 生成されたHTMLの確認**

スクリプトの実行後、**選択した動画データフォルダの直下に** index.html が生成され、static フォルダがコピーされます。この index.html ファイルをウェブブラウザで開いて、整形されたコメントページを確認してください。

## **4\. PyInstallerでのビルド方法（頒布アーカイブ作成）**

youtube-comments-pager を実行可能ファイルとして配布するには、PyInstallerを使用します。

### **4.1. PyInstallerのインストール**

PyInstallerがインストールされていない場合は、以下のコマンドでインストールします。

pip install pyinstaller

### **4.2. ビルドコマンド**

youtube-comments-pager ディレクトリ (例: N:\\Documents\\(python\_scripts)\\youtube-comments-pager\\) に移動し、以下のコマンドを実行します。

pyinstaller \--onefile \--windowed main.py

**コマンドの説明**:

* \--onefile: 単一の実行可能ファイルを生成します。  
* \--windowed または \-w: コンソールウィンドウを表示しません（GUIアプリケーションの場合に推奨）。tkinterのファイルダイアログを使用する場合、このオプションを使用することで、バックグラウンドのコンソールウィンドウが表示されなくなります。  
* \--add-data オプションは使用しません。必要なデータフォルダ（templates, static, default）は、実行ファイルとは別に配置する必要があります。

### **4.3. 生成されるファイル**

ビルドが成功すると、dist ディレクトリ内に実行可能ファイル（例: main.exe または main）が生成されます。

### **4.4. 頒布時の注意点**

生成された実行可能ファイルは、外部の templates、static、default フォルダに依存します。また、読み込むRAWデータも youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> 形式のフォルダとして、実行ファイルとは別に存在する必要があります。配布する際は、上記「3.2. 必要なフォルダとファイルの配置」に従ってこれらのフォルダとファイルを配置する必要があることを明確に伝えてください。

## **5. テスト（開発時）**

プロジェクトのルートディレクトリから、コメントRawデータのページ処理と親子紐付けを確認できます。

```bash
python -m unittest discover -s tests -t . -v
```

テストでは、以下を確認します。

* 動画データフォルダ名から動画IDを抽出する処理（現行日時付き形式と旧日付のみ形式）
* コメントスレッドRawの複数ページ処理
* 返信Rawの複数ページ処理と親コメントIDによる紐付け
* 返信Rawがない場合・返信ページのitemsが空の場合のインライン返信へのフォールバック
* 外部返信Rawとインライン返信プレビューのID重複排除・統合
* 重複親コメントID・返信IDの二重表示防止
* 最後の保存Rawページに `nextPageToken` が残る場合の警告（取得状態の判定はしない）
* 正常な空コメントリストと、欠落・不正・構造不一致の区別

**テスト実行状況（2026-11-27）**: 変更前のテスト10件は成功済みです。今回の重複・部分Raw対応でテストを12件に拡張しましたが、拡張後の12件はこの作業環境では実行できていません。ローカル環境で上記コマンドを実行して確認してください。実データ一式を使ったHTML生成確認は、既存のOSF保存データで再確認が必要です。

## **6. 注意事項**

* このツールは、YouTube Data APIから取得済みのRAWデータを使用します。APIキーは不要です。  
* コメント投稿機能は含まれていません。表示専用です。  
* JSONデータのフォーマットがYouTube Data APIの標準形式と異なる場合、正しく動作しない可能性があります。  
* **選択するフォルダ名は youtube\_data\_\<動画ID\>\_\<YYYY-MM-DD_HH_MM_SS\> の形式に従う必要があります。** 旧形式の日付のみ（YYYY-MM-DD）のフォルダも読み込み対象として受け付けます。 異なる名前のフォルダを選択した場合、エラーメッセージが表示され、プログラムが終了します。

ご不明な点がございましたら、お気軽にお問い合わせください。