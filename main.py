# youtube-comments-pager/main.py # コピーペースト作業での識別用、除去しないように。
import json
import os
import re  # 正規表現モジュールをインポート
import shutil  # ファイル操作（フォルダのコピー）のためにインポート
import sys  # sysモジュールをインポート
import tkinter as tk  # tkinterをインポート
from tkinter import filedialog  # filedialogをインポート
from typing import (Any, Dict,  # Pylanceの型問題検出対策とList, Dict, Optionalのインポート
                    List, Optional)

from jinja2 import Environment, FileSystemLoader

# プログラムのルートディレクトリ（実行ファイルが存在する場所）を特定
# PyInstallerでフリーズされたアプリケーションとして実行されている場合、sys.executable が実行ファイル自身のパスを返します。
# 通常のPythonスクリプトとして実行されている場合、os.path.abspath(__file__) がスクリプト自身のパスを返します。
APPLICATION_ROOT_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

# 各種ディレクトリパスの定義
# すべてのデータフォルダは実行ファイルと同じディレクトリに配置される想定
TEMPLATES_DIR = os.path.join(APPLICATION_ROOT_DIR, 'templates')
STATIC_DIR = os.path.join(APPLICATION_ROOT_DIR, 'static') # コピー元のstaticフォルダ
DEFAULT_DATA_DIR = os.path.join(APPLICATION_ROOT_DIR, 'default') # デフォルトデータフォルダのパス

# RAWDATA_DIR は、ファイルダイアログの初期ディレクトリとしてのみ使用されるか、概念的に存在するのみ。
# 直接的なデータ読み込み元ではなくなる。
RAWDATA_DIR = os.path.join(APPLICATION_ROOT_DIR, 'rawdata')

# OUTPUT_DIR は動的に設定されるため、ここでは初期化しない

def load_json_data(filepath: str) -> Any:
    """
    指定されたJSONファイルからデータを読み込みます。
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません - {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"エラー: JSON形式が不正です - {filepath}")
        return None

def process_youtube_comments(comments_data: Any, replies_data: Any = None) -> List[Dict]:
    """
    保存済みのコメントスレッドRawページと返信Rawページを、表示用の親子構造へ整理します。

    comments_data:
        commentThreads.list のRawレスポンスページを格納したリスト。
    replies_data:
        parent_id と raw_responses を持つ返信Rawレコードのリスト。
        Noneの場合は、親スレッドRaw内に含まれる返信だけを使用します。
    """
    if not isinstance(comments_data, list):
        raise ValueError("コメントスレッドRawデータは、APIレスポンスページのリストである必要があります。")

    def normalize_comment(comment: Any, kind: str) -> Dict:
        if not isinstance(comment, dict):
            raise ValueError("{}コメントのデータが辞書ではありません。".format(kind))
        comment_id = comment.get("id")
        snippet = comment.get("snippet")
        if not isinstance(comment_id, str) or not comment_id:
            raise ValueError("{}コメントに有効なidがありません。".format(kind))
        if not isinstance(snippet, dict):
            raise ValueError("{}コメントのsnippetがありません、または不正です。".format(kind))
        return {
            "id": comment_id,
            "authorDisplayName": snippet.get("authorDisplayName", "不明な投稿者"),
            "authorProfileImageUrl": snippet.get("authorProfileImageUrl", ""),
            "textDisplay": snippet.get("textDisplay", snippet.get("textOriginal", "")),
            "publishedAt": snippet.get("publishedAt", ""),
            "likeCount": snippet.get("likeCount", 0)
        }

    processed_comments = []
    comments_by_parent_id = {}
    inline_replies_by_parent_id = {}
    expected_reply_counts_by_parent_id = {}

    # 親コメントRawレスポンスはページをまたいですべて処理する。
    for page_index, page in enumerate(comments_data, start=1):
        if not isinstance(page, dict):
            raise ValueError("コメントスレッドRawデータの{}ページ目が辞書ではありません。".format(page_index))
        items = page.get("items")
        if not isinstance(items, list):
            raise ValueError("コメントスレッドRawデータの{}ページ目にitemsリストがありません。".format(page_index))

        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError("コメントスレッドRawデータの{}ページ目、{}件目が辞書ではありません。".format(page_index, item_index))
            thread_snippet = item.get("snippet")
            if not isinstance(thread_snippet, dict):
                raise ValueError("コメントスレッドRawデータの{}ページ目、{}件目にsnippetがありません。".format(page_index, item_index))
            top_level = thread_snippet.get("topLevelComment")
            top_level_info = normalize_comment(top_level, "トップレベル")
            parent_id = top_level_info["id"]
            expected_reply_count = thread_snippet.get("totalReplyCount", 0)
            if isinstance(expected_reply_count, int) and expected_reply_count > 0:
                expected_reply_counts_by_parent_id[parent_id] = max(
                    expected_reply_counts_by_parent_id.get(parent_id, 0),
                    expected_reply_count
                )

            comment_info = dict(top_level_info)
            comment_info["replies"] = []
            processed_comments.append(comment_info)
            comments_by_parent_id.setdefault(parent_id, []).append(comment_info)

            # commentThreads.list(part="snippet,replies") に含まれる返信は、
            # 別ファイルがない場合や返信Rawレコードが空の場合の部分データとして保持する。
            inline_replies = []
            replies_container = item.get("replies")
            if replies_container is not None:
                if not isinstance(replies_container, dict):
                    raise ValueError("親コメント '{}' のrepliesが辞書ではありません。".format(parent_id))
                reply_items = replies_container.get("comments", [])
                if not isinstance(reply_items, list):
                    raise ValueError("親コメント '{}' のreplies.commentsがリストではありません。".format(parent_id))
                for reply in reply_items:
                    inline_replies.append(normalize_comment(reply, "返信"))
            inline_replies_by_parent_id.setdefault(parent_id, []).extend(inline_replies)

    external_replies_by_parent_id = {}
    if replies_data is not None:
        if not isinstance(replies_data, list):
            raise ValueError("返信Rawデータは、parent_idとraw_responsesを持つレコードのリストである必要があります。")

        # 返信Rawファイル内の全レコード・全ページを親コメントIDごとに集約する。
        for record_index, record in enumerate(replies_data, start=1):
            if not isinstance(record, dict):
                raise ValueError("返信Rawデータの{}件目が辞書ではありません。".format(record_index))
            parent_id = record.get("parent_id")
            raw_responses = record.get("raw_responses")
            if not isinstance(parent_id, str) or not parent_id:
                raise ValueError("返信Rawデータの{}件目に有効なparent_idがありません。".format(record_index))
            if not isinstance(raw_responses, list):
                raise ValueError("返信Rawデータの親コメント '{}' にraw_responsesリストがありません。".format(parent_id))

            for page_index, page in enumerate(raw_responses, start=1):
                if not isinstance(page, dict):
                    raise ValueError("親コメント '{}' の返信Raw {}ページ目が辞書ではありません。".format(parent_id, page_index))
                reply_items = page.get("items")
                if not isinstance(reply_items, list):
                    raise ValueError("親コメント '{}' の返信Raw {}ページ目にitemsリストがありません。".format(parent_id, page_index))
                for reply in reply_items:
                    normalized_reply = normalize_comment(reply, "返信")
                    external_replies_by_parent_id.setdefault(parent_id, []).append(normalized_reply)

    # 親コメントが欠落している返信RawはHTMLに紐付けられないため、警告して区別する。
    for parent_id in external_replies_by_parent_id:
        if parent_id not in comments_by_parent_id:
            print("警告: 返信Rawの親コメント '{}' がコメントスレッドRawにありません。返信を表示できません。".format(parent_id))

    # 返信Rawの実データがあればそちらを優先し、なければ親スレッド内の返信を表示する。
    for parent_id, parent_comments in comments_by_parent_id.items():
        external_replies = external_replies_by_parent_id.get(parent_id, [])
        selected_replies = external_replies or inline_replies_by_parent_id.get(parent_id, [])
        expected_reply_count = expected_reply_counts_by_parent_id.get(parent_id, 0)
        if expected_reply_count > len(selected_replies):
            print(
                "警告: 親コメント '{}' の返信はAPI記録上{}件ですが、RAWデータから表示できる返信は{}件です。".format(
                    parent_id, expected_reply_count, len(selected_replies)
                )
            )
        for parent_comment in parent_comments:
            parent_comment["replies"] = list(selected_replies)

    return processed_comments

def generate_html_page(video_data: Dict, comments_data: List[Dict], channel_data: Dict, template_filename: str = 'pager-template.html', output_filename: str = 'index.html', output_dir: str = '') -> Optional[str]:
    """
    Jinja2テンプレートを使用してHTMLページを生成します。
    output_dir に生成先を指定できるように変更。
    """
    try:
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        template = env.get_template(template_filename)

        # staticファイルへのURLを生成する関数をJinja2環境に追加
        def static_url(path: str) -> str:
            # 静的ファイルへの参照は常にstatic/からの相対パスとしてHTMLに埋め込まれる
            return os.path.join('static', path).replace('\\', '/') # Windowsパス対策
        
        env.globals['static_url'] = static_url

        # Safely get the first video item and its snippet
        first_video_item = None
        if video_data and 'items' in video_data and video_data['items']: # 'items'が存在し、かつ空でないことを確認
            first_video_item = video_data['items'][0]
        
        if first_video_item and 'snippet' in first_video_item:
            # 動画説明の改行をHTMLの<br>タグに変換
            description = first_video_item['snippet'].get('description', '')
            first_video_item['snippet']['description'] = description.replace('\n', '<br>')

            # チャンネルアイコンのURLを動画データに追加
            if channel_data and 'items' in channel_data and channel_data['items']:
                channel_snippet = channel_data['items'][0].get('snippet')
                if channel_snippet:
                    if 'thumbnails' in channel_snippet and 'high' in channel_snippet['thumbnails']:
                        first_video_item['snippet']['channelThumbnailUrl'] = channel_snippet['thumbnails']['high'].get('url')
                    # channelTitleがvideo_dataにない場合、channel_dataから取得
                    if 'channelTitle' not in first_video_item['snippet']:
                        first_video_item['snippet']['channelTitle'] = channel_snippet.get('title', '不明なチャンネル')


        # テンプレートレンダリング
        rendered_html = template.render(
            video=first_video_item, # 安全に取得した最初の動画アイテムを渡す
            comments=comments_data # 処理済みのコメントデータを渡す
        )

        output_filepath = os.path.join(output_dir, output_filename) # output_dirを使用
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(rendered_html)
        print(f"HTMLページを生成しました: {output_filepath}")
        return output_filepath
    except Exception as e:
        print(f"エラー: HTMLページの生成中に問題が発生しました: {e}")
        return None # エラー発生時はNoneを返す

def main():
    # tkinterのルートウィンドウを作成し、非表示にする
    root = tk.Tk()
    root.withdraw()

    print("動画データ（JSONファイル）が格納されているフォルダを選択してください。")
    print("フォルダ名は 'youtube_data_<動画ID>_<Y-m-d>' の形式である必要があります。")

    # ファイルダイアログを開き、フォルダを選択させる
    # initialdir に RAWDATA_DIR を指定することで、デフォルトの開始フォルダを提示できる
    selected_folder_path = filedialog.askdirectory(
        initialdir=RAWDATA_DIR if os.path.exists(RAWDATA_DIR) else APPLICATION_ROOT_DIR,
        title="動画データフォルダを選択してください"
    )

    if not selected_folder_path:
        print("フォルダが選択されませんでした。処理を終了します。")
        sys.exit(0) # ユーザーがキャンセルした場合、正常終了

    # 現行scraperのフォルダ名（日時まで）と、旧形式（日付のみ）の両方を検証
    selected_folder_name = os.path.basename(selected_folder_path)
    folder_match = re.match(
        r"^youtube_data_([a-zA-Z0-9_-]{11})_(\d{4}-\d{2}-\d{2})(?:_(\d{2})_(\d{2})_(\d{2}))?$",
        selected_folder_name
    )
    if not folder_match:
        print("エラー: 選択されたフォルダ名 '{}' は無効な形式です。".format(selected_folder_name))
        print("形式: youtube_data_<動画ID>_<YYYY-MM-DD_HH_MM_SS>（旧形式のYYYY-MM-DDも可）")
        sys.exit(1) # 無効なフォルダ名の場合、エラー終了
    folder_video_id = folder_match.group(1)

    print(f"選択されたフォルダ: {selected_folder_path}")

    # 選択フォルダ内のファイル名からvideo_idとchannel_idを検出
    actual_video_id = None
    actual_channel_id = None

    for filename in os.listdir(selected_folder_path):
        if filename.startswith("video_info_raw_") and filename.endswith(".json"):
            match = re.match(r"^video_info_raw_([a-zA-Z0-9_-]{11})\.json$", filename)
            if match:
                actual_video_id = match.group(1)
        elif filename.startswith("channel_info_raw_") and filename.endswith(".json"):
            match = re.match(r"^channel_info_raw_([a-zA-Z0-9_-]+)\.json$", filename)
            if match:
                actual_channel_id = match.group(1)

    # video_infoが欠落した部分データでも、フォルダ名から動画IDを特定できる。
    if actual_video_id and actual_video_id != folder_video_id:
        print("エラー: フォルダ名の動画IDとvideo_infoファイル名の動画IDが一致しません。")
        sys.exit(1)
    video_id_to_use = actual_video_id or folder_video_id

    comments_json_path = os.path.join(selected_folder_path, "comments_raw_{}.json".format(video_id_to_use))
    replies_json_path = os.path.join(selected_folder_path, "comment_replies_raw_{}.json".format(video_id_to_use))
    videos_json_path = os.path.join(selected_folder_path, "video_info_raw_{}.json".format(video_id_to_use))
    channel_json_path = (
        os.path.join(selected_folder_path, "channel_info_raw_{}.json".format(actual_channel_id))
        if actual_channel_id else None
    )

    # コメントRawは必須。欠落・JSON不正をダミーコメントや正常な空データに置き換えない。
    comments_data = load_json_data(comments_json_path)
    if comments_data is None:
        print("エラー: コメントスレッドRawデータを読み込めません。ファイルの欠落またはJSON不正を確認してください。")
        sys.exit(1)

    # 返信Rawファイルは取得データがある場合に保存されるため、存在しない場合は親スレッド内の返信だけを使用する。
    replies_data = None
    if os.path.exists(replies_json_path):
        replies_data = load_json_data(replies_json_path)
        if replies_data is None:
            print("エラー: 返信RawデータのJSON形式が不正です。")
            sys.exit(1)
    else:
        print("警告: 返信Rawファイルがありません。親スレッドRaw内に含まれる返信のみ表示します。")

    # 動画・チャンネル情報は任意。欠落時は空の情報として扱い、コメント処理は継続する。
    videos_data = load_json_data(videos_json_path) if os.path.exists(videos_json_path) else None
    if videos_data is None:
        print("警告: 動画情報Rawデータがありません、または読み込めません。動画情報なしで続行します。")
        videos_data = {"items": []}

    channel_data = load_json_data(channel_json_path) if channel_json_path and os.path.exists(channel_json_path) else None
    if channel_data is None:
        print("警告: チャンネル情報Rawデータがありません、または読み込めません。チャンネル情報なしで続行します。")
        channel_data = {"items": []}

    try:
        processed_comments = process_youtube_comments(comments_data, replies_data)
    except ValueError as e:
        print("エラー: コメントRawデータの構造が不正です: {}".format(e))
        sys.exit(1)



    # 使用するテンプレートを指定 (例: 'pager-template.html' または 'example.html')
    template_to_use = 'pager-template.html' 
    output_html_filename = 'index.html'

    # ユーザーの要求に応じて、example.htmlが存在すればそちらを優先的に使用
    # example.htmlはbundledなのでBUNDLED_DATA_ROOT_DIRから探す
    example_template_path = os.path.join(TEMPLATES_DIR, 'example.html')
    if os.path.exists(example_template_path):
        template_to_use = 'example.html'
        print(f"情報: '{example_template_path}' が見つかったため、このテンプレートを使用します。")
    else:
        print(f"情報: '{example_template_path}' が見つかりません。デフォルトの '{template_to_use}' を使用します。")

    # generate_html_page に選択されたフォルダパスを output_dir として渡す
    generated_filepath = generate_html_page(videos_data, processed_comments, channel_data, template_to_use, output_html_filename, output_dir=selected_folder_path)

    if generated_filepath:
        print(f"HTMLページが正常に生成されました: {generated_filepath}")

        # Staticフォルダを、生成されたindex.htmlと同じフォルダにコピー
        target_static_dir = os.path.join(selected_folder_path, 'static')
        
        if os.path.exists(target_static_dir):
            print(f"情報: 既存の '{target_static_dir}' フォルダを削除しています...")
            try:
                shutil.rmtree(target_static_dir)
                print("既存フォルダの削除が完了しました。")
            except OSError as e:
                print(f"エラー: 既存のstaticフォルダを削除できませんでした: {e}")
                print("HTMLページの生成は成功しましたが、staticファイルのコピーに問題が発生しました。手動でコピーしてください。")
                return # 処理を中断するか、エラーを報告して続行しない

        try:
            print(f"情報: '{STATIC_DIR}' から '{target_static_dir}' へ静的ファイルをコピーしています...")
            shutil.copytree(STATIC_DIR, target_static_dir)
            print("静的ファイルのコピーが完了しました。")
        except Exception as e:
            print(f"エラー: 静的ファイルのコピー中に問題が発生しました: {e}")
            print("HTMLページの生成は成功しましたが、staticファイルのコピーに問題が発生しました。手動でコピーしてください。")
    else:
        print("HTMLページの生成に失敗しました。")

if __name__ == '__main__':
    main()
