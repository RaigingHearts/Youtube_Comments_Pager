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

def process_youtube_comments(comments_data: Any) -> List[Dict]:
    """
    YouTube APIのコメントデータをツリー構造（トップレベルと返信）に整理します。
    comments_dataがリストの場合（APIレスポンスの形式）に対応します。
    """
    processed_comments = []
    # comments_dataがリストであり、かつ最初の要素が辞書で'items'キーを持つことを確認
    if isinstance(comments_data, list) and comments_data and 'items' in comments_data[0]:
        for item in comments_data[0]['items']: # ここを修正: comments_data[0] から 'items' にアクセス
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

    # 選択されたフォルダ名が 'youtube_data_<動画ID>_<Y-m-d>' 形式であるかを検証
    selected_folder_name = os.path.basename(selected_folder_path)
    if not (selected_folder_name.startswith("youtube_data_") and re.match(r"youtube_data_[a-zA-Z0-9_-]+_\d{4}-\d{2}-\d{2}", selected_folder_name)):
        print(f"エラー: 選択されたフォルダ名 '{selected_folder_name}' は無効な形式です。")
        print("フォルダ名は 'youtube_data_<動画ID>_<Y-m-d>' の形式である必要があります。")
        sys.exit(1) # 無効なフォルダ名の場合、エラー終了

    print(f"選択されたフォルダ: {selected_folder_path}")

    # 選択されたフォルダ内のJSONファイルからvideo_idとchannel_idを検出
    actual_video_id = None
    actual_channel_id = None

    for filename in os.listdir(selected_folder_path):
        if filename.startswith("video_info_raw_") and filename.endswith(".json"):
            match = re.match(r"video_info_raw_([a-zA-Z0-9_-]+)\.json", filename)
            if match:
                actual_video_id = match.group(1)
                print(f"情報: 選択されたフォルダ内のファイル名から video_id を検出しました: {actual_video_id}")
        elif filename.startswith("channel_info_raw_") and filename.endswith(".json"):
            match = re.match(r"channel_info_raw_([a-zA-Z0-9_-]+)\.json", filename)
            if match:
                actual_channel_id = match.group(1)
                print(f"情報: 選択されたフォルダ内のファイル名から channel_id を検出しました: {actual_channel_id}")

    # IDが見つからない場合のフォールバックとして、ダミーIDを使用
    video_id_to_use = actual_video_id if actual_video_id else 'DUMMY_VIDEO_ID_ABC123'
    channel_id_to_use = actual_channel_id if actual_channel_id else 'DUMMY_CHANNEL_ID_XYZ789'

    # JSONファイルのパスは選択されたフォルダ内
    comments_json_path = os.path.join(selected_folder_path, f'comments_raw_{video_id_to_use}.json')
    videos_json_path = os.path.join(selected_folder_path, f'video_info_raw_{video_id_to_use}.json')
    channel_json_path = os.path.join(selected_folder_path, f'channel_info_raw_{channel_id_to_use}.json')

    comments_data = load_json_data(comments_json_path)
    videos_data = load_json_data(videos_json_path)
    channel_data = load_json_data(channel_json_path) # チャンネルデータを読み込み

    # Fallback to dummy data if actual data is not found from selected folder
    # comments_dataはリスト形式でロードされることを想定
    if not comments_data or not (isinstance(comments_data, list) and comments_data and 'items' in comments_data[0]):
        print(f"情報: '{comments_json_path}' が見つからないか読み込めません、または形式が不正です。ダミーコメントデータを使用します。")
        # ダミーデータもリスト形式でラップされていることを確認
        # pager-template-maker/default ディレクトリを参照するように変更
        dummy_comments_path = os.path.join(DEFAULT_DATA_DIR, 'dummy_comments.json')
        comments_data = load_json_data(dummy_comments_path)
        if not comments_data or not (isinstance(comments_data, list) and comments_data and 'items' in comments_data[0]):
            print("警告: ダミーコメントデータも読み込めませんでした、または形式が不正です。コメントなしで処理を続行します。")
            comments_data = [{'items': []}] # 空のリストで、かつ最初の要素が'items'を持つ辞書

    if not videos_data:
        print(f"情報: '{videos_json_path}' が見つからないか読み込めません。ダミー動画情報を使用します。")
        dummy_video_path = os.path.join(DEFAULT_DATA_DIR, 'dummy_video_info.json')
        videos_data = load_json_data(dummy_video_path)
        if not videos_data:
            print("警告: ダミー動画情報も読み込めませんでした。動画情報なしで処理を続行します。")
            videos_data = {'items': [{ 'snippet': {} }]}

    if not channel_data: # Add fallback for channel data
        print(f"情報: '{channel_json_path}' が見つからないか読み込めません。ダミーチャンネル情報を使用します。")
        dummy_channel_path = os.path.join(DEFAULT_DATA_DIR, 'dummy_channel_info.json')
        channel_data = load_json_data(dummy_channel_path)
        if not channel_data:
            print("警告: ダミーチャンネル情報も読み込めませんでした。チャンネル情報なしで処理を続行します。")
            channel_data = {'items': [{ 'snippet': {} }]}


    processed_comments = process_youtube_comments(comments_data)

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
