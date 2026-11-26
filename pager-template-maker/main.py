# pager-template-maker/main.py # コピーペースト作業での識別用、除去しないように。
import json  # 設定保存・読み込み用
import os
import re  # 正規表現用
import sys

from jinja2 import (Environment, FileSystemLoader,  # Templateをインポート
                    Template)
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (QApplication, QCheckBox, QFileDialog, QGroupBox,
                             QHBoxLayout, QMainWindow, QPushButton,
                             QSizePolicy, QTextEdit, QVBoxLayout, QWidget)


class TemplateDesignerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("コメントテンプレートデザイナ")
        self.setGeometry(100, 100, 1200, 800) # ウィンドウサイズを設定

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # メインレイアウトを分割し、エディタ、要素設定、プレビューを並列に配置
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # --- 左側のエディタ部分 ---
        self.editor_container = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_container)
        self.main_layout.addWidget(self.editor_container, 2) # 2の比率で幅を確保

        # HTMLエディタ
        self.html_editor = QTextEdit()
        self.html_editor.setPlaceholderText("ここにHTMLテンプレートを記述してください...")
        self.editor_layout.addWidget(self.html_editor)
        self.html_editor.textChanged.connect(self.update_preview)

        # CSSエディタ
        self.css_editor = QTextEdit()
        self.css_editor.setPlaceholderText("ここにCSSスタイルを記述してください...")
        self.editor_layout.addWidget(self.css_editor)
        self.css_editor.textChanged.connect(self.update_preview)

        # ファイル操作ボタン
        self.button_layout = QHBoxLayout()
        self.load_html_button = QPushButton("HTML読込")
        self.load_html_button.clicked.connect(self.load_html)
        self.button_layout.addWidget(self.load_html_button)

        self.save_html_button = QPushButton("HTML保存")
        self.save_html_button.clicked.connect(self.save_html)
        self.button_layout.addWidget(self.save_html_button)

        self.load_css_button = QPushButton("CSS読込")
        self.load_css_button.clicked.connect(self.load_css)
        self.button_layout.addWidget(self.load_css_button)

        self.save_css_button = QPushButton("CSS保存")
        self.save_css_button.clicked.connect(self.save_css)
        self.button_layout.addWidget(self.save_css_button)
        
        self.editor_layout.addLayout(self.button_layout)

        # --- 中央の要素設定部分 ---
        self.settings_container = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_container)
        self.main_layout.addWidget(self.settings_container, 1) # 1の比率で幅を確保

        # 動画情報表示項目グループ
        self.video_settings_group = QGroupBox("動画情報表示項目")
        self.video_settings_layout = QVBoxLayout()
        self.video_settings_group.setLayout(self.video_settings_layout)
        self.settings_layout.addWidget(self.video_settings_group)

        self.checkbox_channel_icon = QCheckBox("チャンネルアイコン") # 新しいチェックボックス
        self.checkbox_video_title = QCheckBox("動画タイトル")
        self.checkbox_video_description = QCheckBox("動画説明")
        self.checkbox_video_thumbnail = QCheckBox("サムネイル")
        self.checkbox_video_meta = QCheckBox("動画メタ情報 (公開日時/チャンネル)")
        
        self.video_settings_layout.addWidget(self.checkbox_channel_icon) # レイアウトに追加
        self.video_settings_layout.addWidget(self.checkbox_video_title)
        self.video_settings_layout.addWidget(self.checkbox_video_description)
        self.video_settings_layout.addWidget(self.checkbox_video_thumbnail)
        self.video_settings_layout.addWidget(self.checkbox_video_meta)

        self.checkbox_channel_icon.stateChanged.connect(self.update_preview) # シグナル接続
        self.checkbox_video_title.stateChanged.connect(self.update_preview)
        self.checkbox_video_description.stateChanged.connect(self.update_preview)
        self.checkbox_video_thumbnail.stateChanged.connect(self.update_preview)
        self.checkbox_video_meta.stateChanged.connect(self.update_preview)

        # コメント表示項目グループ
        self.comment_settings_group = QGroupBox("コメント表示項目")
        self.comment_settings_layout = QVBoxLayout()
        self.comment_settings_group.setLayout(self.comment_settings_layout)
        self.settings_layout.addWidget(self.comment_settings_group)

        self.checkbox_comment_author = QCheckBox("投稿者名")
        self.checkbox_comment_text = QCheckBox("コメント本文")
        self.checkbox_comment_meta = QCheckBox("投稿メタ情報 (日時/いいね)") # 投稿日時といいね数をまとめる
        
        self.comment_settings_layout.addWidget(self.checkbox_comment_author)
        self.comment_settings_layout.addWidget(self.checkbox_comment_text)
        self.comment_settings_layout.addWidget(self.checkbox_comment_meta)

        self.checkbox_comment_author.stateChanged.connect(self.update_preview)
        self.checkbox_comment_text.stateChanged.connect(self.update_preview)
        self.checkbox_comment_meta.stateChanged.connect(self.update_preview)

        # 返信コメント表示項目グループ
        self.reply_settings_group = QGroupBox("返信コメント表示項目")
        self.reply_settings_layout = QVBoxLayout()
        self.reply_settings_group.setLayout(self.reply_settings_layout)
        self.settings_layout.addWidget(self.reply_settings_group)

        self.checkbox_reply_author = QCheckBox("返信投稿者名")
        self.checkbox_reply_text = QCheckBox("返信コメント本文")
        self.checkbox_reply_meta = QCheckBox("返信投稿メタ情報 (日時/いいね)") # 投稿日時といいね数をまとめる
        
        self.reply_settings_layout.addWidget(self.checkbox_reply_author)
        self.reply_settings_layout.addWidget(self.checkbox_reply_text)
        self.reply_settings_layout.addWidget(self.checkbox_reply_meta)

        self.checkbox_reply_author.stateChanged.connect(self.update_preview)
        self.checkbox_reply_text.stateChanged.connect(self.update_preview)
        self.checkbox_reply_meta.stateChanged.connect(self.update_preview)

        self.settings_layout.addStretch(1) # 残りのスペースを埋める

        # --- 右側のプレビュー部分 ---
        self.web_view = QWebEngineView()
        self.main_layout.addWidget(self.web_view, 4) # 4の比率で幅を確保 (エディタの2倍の幅)
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # プレビュー更新用のタイマー
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(300) # 0.3秒後に更新 (少し短縮)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._do_update_preview)

        # 初期コンテンツの読み込み
        self.load_initial_content()
        self.load_settings() # 設定を読み込み、チェックボックスの状態を復元

    # --- メソッド定義をここに移動 ---
    def update_preview(self):
        """テキストエディタまたはチェックボックスの変更があったときにプレビュー更新タイマーをリセット/開始"""
        self.preview_timer.stop()
        self.preview_timer.start()

    def load_json_data(self, filepath):
        """
        指定されたJSONファイルからデータを読み込みます。
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # print(f"エラー: ファイルが見つかりません - {filepath}") # 警告を減らすためコメントアウト
            return None
        except json.JSONDecodeError:
            print(f"エラー: JSON形式が不正です - {filepath}")
            return None

    def process_youtube_comments(self, comments_data):
        """
        YouTube APIのコメントデータをツリー構造（トップレベルと返信）に整理します。
        comments_dataがリストの場合（APIレスポンスの形式）に対応します。
        """
        processed_comments = []
        # comments_dataがリストであり、かつ最初の要素が辞書で'items'キーを持つことを確認
        if isinstance(comments_data, list) and comments_data and 'items' in comments_data[0]:
            for item in comments_data[0]['items']:
                top_level_comment = item['snippet']['topLevelComment']
                comment_info = {
                    'id': top_level_comment['id'],
                    'authorDisplayName': top_level_comment['snippet']['authorDisplayName'],
                    'authorProfileImageUrl': top_level_comment['snippet'].get('authorProfileImageUrl', ''), # チャンネルアイコンURLを追加
                    'textDisplay': top_level_comment['snippet']['textDisplay'],
                    'publishedAt': top_level_comment['snippet']['publishedAt'],
                    'likeCount': top_level_comment['snippet']['likeCount'],
                    'replies': [] # 返信コメントを格納するリスト
                }
                
                # 返信コメントが存在する場合
                if 'replies' in item:
                    for reply in item['replies']['comments']:
                        reply_info = {
                            'id': reply['id'],
                            'authorDisplayName': reply['snippet']['authorDisplayName'],
                            'authorProfileImageUrl': reply['snippet'].get('authorProfileImageUrl', ''), # チャンネルアイコンURLを追加
                            'textDisplay': reply['snippet']['textDisplay'],
                            'publishedAt': reply['snippet']['publishedAt'],
                            'likeCount': reply['snippet']['likeCount']
                        }
                        comment_info['replies'].append(reply_info)
                processed_comments.append(comment_info)
        return processed_comments

    def _get_dummy_data(self):
        """プレビュー用のダミーデータをロードまたは生成します。"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # pager-template-maker/main.py と同じディレクトリのJSONファイルのパス
        local_video_json_path = os.path.join(base_dir, 'video_info_raw_9SAhwYXG4Uc.json')
        local_comments_json_path = os.path.join(base_dir, 'comments_raw_9SAhwYXG4Uc.json')
        local_channel_json_path = os.path.join(base_dir, 'channel_info_raw_UCnvljokhYpyxUZc6l12pJog.json') # チャンネルJSONパス

        # pager-template-maker/default/ 用のダミーJSONファイルのパス
        dummy_default_dir = os.path.join(base_dir, 'default')
        dummy_video_json_path = os.path.join(dummy_default_dir, 'dummy-video-info.json')
        dummy_comments_json_path = os.path.join(dummy_default_dir, 'dummy-comments.json')
        dummy_channel_json_path = os.path.join(dummy_default_dir, 'dummy-channel-info.json') # ダミーチャンネルJSONパス

        # まず pager-template-maker/main.py と同じディレクトリのJSONデータを試行
        video_data_for_preview = self.load_json_data(local_video_json_path) or self.load_json_data(dummy_video_json_path)
        comments_raw_data_for_preview = self.load_json_data(local_comments_json_path) or self.load_json_data(dummy_comments_json_path)
        channel_data_for_preview = self.load_json_data(local_channel_json_path) or self.load_json_data(dummy_channel_json_path)

        # 実際のデータが読み込めない場合、デフォルトのダミーデータにフォールバック
        if not video_data_for_preview:
            print(f"警告: 動画情報が見つかりません。ダミーデータを使用します。")
            video_data_for_preview = {'items': { 'snippet': {'title': 'ダミー動画タイトル', 'description': 'ダミー動画説明文です。\n改行もテストします。', 'publishedAt': '2025-01-01T00:00:00Z', 'channelTitle': 'ダミーチャンネル', 'thumbnails': {'high': {'url': 'https://placehold.co/480x270/cccccc/ffffff?text=Dummy+Thumbnail'}}, 'channelThumbnailUrl': 'https://placehold.co/60x60/cccccc/ffffff?text=Dummy+Icon'}}}
        
        if not comments_raw_data_for_preview:
            print(f"警告: コメント情報が見つかりません。ダミーデータを使用します。")
            # ダミーコメントデータをリストでラップ
            comments_raw_data_for_preview = [{
                "items": [
                    {"snippet": {"topLevelComment": {"id": "dummy_comment_1", "snippet": {"authorDisplayName": "ダミーユーザー1", "authorProfileImageUrl": "https://placehold.co/40x40/cccccc/ffffff?text=DU1", "textDisplay": "これはダミーのトップレベルコメントです。\n改行もテストします。", "publishedAt": "2025-05-20T10:00:00Z", "likeCount": 5}}}},
                    {"snippet": {"topLevelComment": {"id": "dummy_comment_2", "snippet": {"authorDisplayName": "ダミーユーザー2", "authorProfileImageUrl": "https://placehold.co/40x40/cccccc/ffffff?text=DU2", "textDisplay": "別のダミーコメントです。", "publishedAt": "2025-05-20T11:00:00Z", "likeCount": 10}}, "replies": {"comments": [
                        {"id": "dummy_reply_1", "snippet": {"authorDisplayName": "返信ユーザーA", "authorProfileImageUrl": "https://placehold.co/40x40/cccccc/ffffff?text=RA", "textDisplay": "ダミー返信1です。", "publishedAt": "2025-05-20T11:05:00Z", "likeCount": 2}},
                        {"id": "dummy_reply_2", "snippet": {"authorDisplayName": "返信ユーザーB", "authorProfileImageUrl": "https://placehold.co/40x40/cccccc/ffffff?text=RB", "textDisplay": "ダミー返信2です。\n複数行の返信。", "publishedAt": "2025-05-20T11:10:00Z", "likeCount": 1}}
                    ]}}}
                ]
            }]

        if not channel_data_for_preview: # チャンネルデータもフォールバック
            print(f"警告: チャンネル情報が見つかりません。ダミーデータを使用します。")
            channel_data_for_preview = {'items': [{'snippet': {'title': 'ダミーチャンネル', 'thumbnails': {'high': {'url': 'https://placehold.co/60x60/cccccc/ffffff?text=Dummy+Icon'}} }}]}


        # コメントデータをツリー構造に整理
        processed_comments_for_preview = self.process_youtube_comments(comments_raw_data_for_preview)

        # Jinja2のプレースホルダーを実際のデータで置き換えるためのコンテキスト
        # ここで動画とコメントのダミーデータを完全にレンダリングする

        # チャンネルアイコンのURLを動画データに追加 (channel_data_for_previewから取得)
        video_snippet = video_data_for_preview['items'][0]['snippet']
        if channel_data_for_preview and 'items' in channel_data_for_preview and channel_data_for_preview['items']:
            channel_snippet = channel_data_for_preview['items'][0].get('snippet')
            if channel_snippet:
                if 'thumbnails' in channel_snippet and 'high' in channel_snippet['thumbnails']:
                    video_snippet['channelThumbnailUrl'] = channel_snippet['thumbnails']['high'].get('url') # video_snippetに直接追加
                # channelTitleがvideo_dataにない場合、channel_dataから取得
                if 'channelTitle' not in video_snippet:
                    video_snippet['channelTitle'] = channel_snippet.get('title', '不明なチャンネル')

        # 動画説明の改行をHTMLの<br>タグに変換
        if 'description' in video_snippet:
            video_snippet['description'] = video_snippet['description'].replace('\n', '<br>')

        return {
            'video': video_data_for_preview['items'][0],
            'comments': processed_comments_for_preview,
            'channel_data': channel_data_for_preview # 必要であれば
        }
            
    def _apply_toggle_markers(self, html_string):
            """
        HTML文字列内のSTART/ENDマーカーをチェックボックスの状態に基づいて処理します。
        チェックOFFの場合はブロックを削除、ONの場合はマーカーのみ削除。
            """
        elements_to_toggle = {
            'CHANNEL_ICON': self.checkbox_channel_icon.isChecked(), # 新しいチェックボックスの状態
            'VIDEO_TITLE': self.checkbox_video_title.isChecked(),
            'VIDEO_DESCRIPTION': self.checkbox_video_description.isChecked(),
            'VIDEO_THUMBNAIL': self.checkbox_video_thumbnail.isChecked(),
            'VIDEO_META': self.checkbox_video_meta.isChecked(),
            'COMMENT_AUTHOR': self.checkbox_comment_author.isChecked(),
            'COMMENT_TEXT': self.checkbox_comment_text.isChecked(),
            'COMMENT_META': self.checkbox_comment_meta.isChecked(),
            'REPLY_AUTHOR': self.checkbox_reply_author.isChecked(),
            'REPLY_TEXT': self.checkbox_reply_text.isChecked(),
            'REPLY_META': self.checkbox_reply_meta.isChecked(),
            'COMMENT_SUBMISSION': False, # コメント投稿セクションは常にOFF
        }

        processed_html = html_string
        for key, is_checked in elements_to_toggle.items():
            # 正しいマーカー文字列を使用
            start_marker = f"%"  # 修正箇所
            end_marker = f"%"    # 修正箇所
            
            # 正規表現でマーカー間のコンテンツを検索
            pattern = re.compile(f"{re.escape(start_marker)}(.*?){re.escape(end_marker)}", re.DOTALL)
            
            if not is_checked:
                processed_html = pattern.sub("", processed_html)
            else:
                processed_html = processed_html.replace(start_marker, "").replace(end_marker, "")
        return processed_html

    def _do_update_preview(self):
        """実際のプレビュー更新処理（UI更新のみ）"""
        html_content = self.html_editor.toPlainText()
        css_content = self.css_editor.toPlainText()

        # プレビュー用にJinja2テンプレートをダミーデータでレンダリング
        env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__)))) # 現在のディレクトリをベースに
        template = Template(html_content) # エディタのテキストを直接テンプレートとして扱う

        # static_url関数をJinja2環境に追加
        def static_url(path: str) -> str:
            # プレビューではCSSを直接埋め込むため、この関数はダミーで良い
            return f"static/{path}" 
        env.globals['static_url'] = static_url

        dummy_data = self._get_dummy_data()
        rendered_html_for_preview = template.render(
            video=dummy_data['video'],
            comments=dummy_data['comments']
        )

        # レンダリングされたHTMLにトグルマーカーの処理を適用
        final_html_for_preview = self._apply_toggle_markers(rendered_html_for_preview)

        # CSSを直接HTMLに埋め込む
        final_html_for_preview = final_html_for_preview.replace(
            '<link rel="stylesheet" href="{{ static_url(\'css/style.css\') }}">',
            '<style>' + css_content + '</style>'
        )
        
        # JavaScriptを直接HTMLに埋め込む（今回は返信ボタンがないので、空または最小限に）
        # <script>タグ自体は残し、中身を空にします
        final_html_for_preview = final_html_for_preview.replace(
            '<script src="{{ static_url(\'js/script.js\') }}"></script>',
            "<script></script>" # JavaScript不要なので空のスクリプトタグに置換
        )

        # フッター部分を削除（コピーライトが不要なため）
        footer_start = "<footer>"
        footer_end = "</footer>"
        if footer_start in final_html_for_preview and footer_end in final_html_for_preview:
            start_idx = final_html_for_preview.find(footer_start)
            end_idx = final_html_for_preview.find(footer_end, start_idx) + len(footer_end)
            final_html_for_preview = final_html_for_preview[:start_idx] + final_html_for_preview[end_idx:]

        self.web_view.setHtml(final_html_for_preview)

    def load_initial_content(self):
        """
        初回起動時にデフォルトのテンプレートファイルを読み込みます。
        """
        # pager-template-maker/default/ からファイルを読み込む
        base_dir = os.path.dirname(os.path.abspath(__file__))
        default_html_path = os.path.join(base_dir, 'default', 'pager-template.html')
        default_css_path = os.path.join(base_dir, 'default', 'style.css')

        # HTMLテンプレートの初期読み込み
        if os.path.exists(default_html_path):
            with open(default_html_path, 'r', encoding='utf-8') as f:
                self.html_editor.setPlainText(f.read())
        else:
            print(f"警告: デフォルトHTMLテンプレートが見つかりません: {default_html_path}")

        # CSSファイルの初期読み込み
        if os.path.exists(default_css_path):
            with open(default_css_path, 'r', encoding='utf-8') as f:
                self.css_editor.setPlainText(f.read())
        else:
            print(f"警告: デフォルトCSSファイルが見つかりません: {default_css_path}")
        
        self._do_update_preview() # 初期読み込み後にプレビューを更新

    def get_settings(self):
        """現在のチェックボックスの状態を辞書として取得"""
        settings = {
            'channel_icon': self.checkbox_channel_icon.isChecked(), # 新しい設定項目
            'video_title': self.checkbox_video_title.isChecked(),
            'video_description': self.checkbox_video_description.isChecked(),
            'video_thumbnail': self.checkbox_video_thumbnail.isChecked(),
            'video_meta': self.checkbox_video_meta.isChecked(),
            'comment_author': self.checkbox_comment_author.isChecked(),
            'comment_text': self.checkbox_comment_text.isChecked(),
            'comment_meta': self.checkbox_comment_meta.isChecked(),
            'reply_author': self.checkbox_reply_author.isChecked(),
            'reply_text': self.checkbox_reply_text.isChecked(),
            'reply_meta': self.checkbox_reply_meta.isChecked(),
        }
        return settings

    def set_settings(self, settings):
        """辞書からチェックボックスの状態を設定"""
        # 初期状態ですべてONにするため、デフォルト値をTrueに設定
        self.checkbox_channel_icon.setChecked(settings.get('channel_icon', True)) # 新しい設定項目
        self.checkbox_video_title.setChecked(settings.get('video_title', True))
        self.checkbox_video_description.setChecked(settings.get('video_description', True))
        self.checkbox_video_thumbnail.setChecked(settings.get('video_thumbnail', True))
        self.checkbox_video_meta.setChecked(settings.get('video_meta', True))
        self.checkbox_comment_author.setChecked(settings.get('comment_author', True))
        self.checkbox_comment_text.setChecked(settings.get('comment_text', True))
        self.checkbox_comment_meta.setChecked(settings.get('comment_meta', True))
        self.checkbox_reply_author.setChecked(settings.get('reply_author', True))
        self.checkbox_reply_text.setChecked(settings.get('reply_text', True))
        self.checkbox_reply_meta.setChecked(settings.get('reply_meta', True))

    def load_settings(self):
        """設定ファイルからチェックボックスの状態を読み込む"""
        config_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        if os.path.exists(config_filepath):
            try:
                with open(config_filepath, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.set_settings(settings)
                    print(f"設定を {config_filepath} から読み込みました。")
            except json.JSONDecodeError:
                print(f"エラー: 設定ファイル {config_filepath} のJSON形式が不正です。")
            except Exception as e:
                print(f"設定ファイルの読み込み中にエラーが発生しました: {e}")
        else:
            # ファイルが存在しない場合は、全てのチェックボックスをデフォルトでオンにする
            self.set_settings(self.get_settings()) # get_settingsは全てTrueを返すので、これで初期化される

    def save_settings(self):
        """現在のチェックボックスの状態を設定ファイルに保存する"""
        config_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        settings = self.get_settings()
        try:
            with open(config_filepath, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False) # ensure_ascii=False で日本語もそのまま保存
            print(f"設定を {config_filepath} に保存しました。")
        except Exception as e:
            print(f"設定ファイルの保存中にエラーが発生しました: {e}")

    def load_html(self):
        """HTMLファイルを読み込みエディタに表示"""
        # defaultフォルダからの読み込みも考慮
        initial_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'default')
        filepath, _ = QFileDialog.getOpenFileName(self, "HTMLファイルを読み込む", initial_dir, "HTML Files (*.html);;All Files (*)")
        if filepath:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.html_editor.setPlainText(f.read())
            self._do_update_preview()

    def save_html(self):
        """HTMLエディタの内容をファイルに保存 (example.htmlとして保存)"""
        # エディタの元のHTMLコンテンツを取得
        original_html_content = self.html_editor.toPlainText()
        # マーカーのトグル処理のみを適用
        processed_html_for_save = self._apply_toggle_markers(original_html_content)

        # pager-template-maker直下のexample.htmlに保存
        output_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'example.html')
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(processed_html_for_save)
        print(f"HTMLファイルを {output_filepath} に保存しました。")

        # youtube-comments-pager/templates/example.html にもコピー
        target_pager_template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'youtube-comments-pager', 'templates')
        os.makedirs(target_pager_template_dir, exist_ok=True)
        target_pager_filepath = os.path.join(target_pager_template_dir, 'example.html')
        with open(target_pager_filepath, 'w', encoding='utf-8') as f:
            f.write(processed_html_for_save)
        print(f"コピーを {target_pager_filepath} に保存しました。")
        self.save_settings()

    def load_css(self):
        """CSSファイルを読み込みエディタに表示"""
        initial_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'default')
        filepath, _ = QFileDialog.getOpenFileName(self, "CSSファイルを読み込む", initial_dir, "CSS Files (*.css);;All Files (*)")
        if filepath:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.css_editor.setPlainText(f.read())
            self._do_update_preview()

    def save_css(self):
        """CSSエディタの内容をファイルに保存 (example.cssとして保存)"""
        # pager-template-maker直下のexample.cssに保存
        output_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'example.css')
        with open(output_filepath, 'w', encoding='utf-8') as f:
            self.css_editor.toPlainText()
        print(f"CSSファイルを {output_filepath} に保存しました。")
        # youtube-comments-pager/static/css/style.css にもコピー (これはあくまで例で、通常はexample.cssをコピー先の名前にする)
        # 今回は、youtube-comments-pagerのstyle.cssを上書きする形にします。
        target_pager_css_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'youtube-comments-pager', 'static', 'css')
        os.makedirs(target_pager_css_dir, exist_ok=True)
        target_pager_filepath = os.path.join(target_pager_css_dir, 'style.css') # style.cssを上書き
        with open(target_pager_filepath, 'w', encoding='utf-8') as f:
            f.write(self.css_editor.toPlainText())
        print(f"コピーを {target_pager_filepath} に保存しました。")
        self.save_settings() # CSS保存時に設定も保存


if __name__ == '__main__':
    # HiDPI スケーリングを有効にする
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    designer = TemplateDesignerApp()
    designer.show()
    sys.exit(app.exec_())
