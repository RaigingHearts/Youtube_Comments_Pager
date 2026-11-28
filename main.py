# youtube-comments-pager/main.py # コピーペースト作業での識別用、除去しないように。
import json
import logging
import os
import re  # 正規表現モジュールをインポート
import shutil  # ファイル操作（フォルダのコピー）のためにインポート
import stat  # リンク／再解析ポイントの検出
import sys  # sysモジュールをインポート
import tempfile  # 静的ファイル更新時の一時ファイル作成
import tkinter as tk  # tkinterをインポート
from tkinter import filedialog  # filedialogをインポート
from typing import (Any, Dict,  # Pylanceの型問題検出対策とList, Dict, Optionalのインポート
                    List, Optional)

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

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

def _is_link_or_reparse_point(path: str) -> bool:
    """
    Windowsのジャンクション等を含むリンク／再解析ポイントを検出します。
    lstat()でリンク先ではなくパス自体の属性を確認します。
    """
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return False

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return stat.S_ISLNK(path_stat.st_mode) or bool(file_attributes & reparse_flag)


def _raise_walk_error(error: OSError) -> None:
    """os.walkの走査エラーを握りつぶさず、同期処理を中断します。"""
    raise error


def sync_static_files(source_dir: str, target_dir: str) -> None:
    """
    同梱staticを生成先へ反映し、同梱ファイル以外は保持します。

    同じ相対パスにある同梱ファイルは置き換えます。同期先のリンク／再解析ポイントは
    外部パスへの書き込みを避けるため拒否します。各ファイルの置き換えは
    os.replace()で行いますが、複数ファイル全体を一括で原子的に更新するものではありません。
    """
    if not os.path.isdir(source_dir):
        raise FileNotFoundError("同梱staticフォルダが見つかりません: {}".format(source_dir))

    source_files = []
    source_directories = []
    for current_dir, directory_names, file_names in os.walk(source_dir, onerror=_raise_walk_error):
        directory_names.sort()
        file_names.sort()
        relative_dir = os.path.relpath(current_dir, source_dir)
        if relative_dir != ".":
            source_directories.append(relative_dir)
        for file_name in file_names:
            source_path = os.path.join(current_dir, file_name)
            relative_path = os.path.relpath(source_path, source_dir)
            source_files.append((source_path, relative_path))

    # target static自体がリンク／ジャンクション等なら、リンク先を同期先にしない。
    if _is_link_or_reparse_point(target_dir):
        raise OSError("生成先staticがリンクまたは再解析ポイントです。同期を中断します: {}".format(target_dir))
    if os.path.lexists(target_dir) and not os.path.isdir(target_dir):
        raise OSError("生成先staticのパスがディレクトリではありません: {}".format(target_dir))

    # 既存データへの変更前に、配置経路のリンク／再解析ポイントと型衝突を検査する。
    # リンク先が出力フォルダ外であっても、リンク経由の書き込みは許可しない。
    for relative_dir in source_directories:
        destination = target_dir
        for component in relative_dir.split(os.sep):
            destination = os.path.join(destination, component)
            if _is_link_or_reparse_point(destination):
                raise OSError("同期先ディレクトリがリンクまたは再解析ポイントです: {}".format(destination))
        if os.path.lexists(destination) and not os.path.isdir(destination):
            raise OSError("同梱ディレクトリと既存ファイルが衝突しています: {}".format(destination))

    for source_path, relative_path in source_files:
        destination = os.path.join(target_dir, relative_path)
        destination_parent = os.path.dirname(destination)
        if destination_parent != target_dir:
            current_parent = target_dir
            relative_parent = os.path.relpath(destination_parent, target_dir)
            for component in relative_parent.split(os.sep):
                current_parent = os.path.join(current_parent, component)
                if _is_link_or_reparse_point(current_parent):
                    raise OSError("同期先ディレクトリがリンクまたは再解析ポイントです: {}".format(current_parent))
        if _is_link_or_reparse_point(destination):
            raise OSError("同期先ファイルがリンクまたは再解析ポイントです: {}".format(destination))
        if os.path.lexists(destination) and not os.path.isfile(destination):
            raise OSError("同梱ファイルと既存ディレクトリ等が衝突しています: {}".format(destination))

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for relative_dir in source_directories:
        destination = os.path.join(target_dir, relative_dir)
        if not os.path.exists(destination):
            os.makedirs(destination)

    for source_path, relative_path in source_files:
        destination = os.path.join(target_dir, relative_path)
        destination_dir = os.path.dirname(destination)
        temporary_path = None
        try:
            file_descriptor, temporary_path = tempfile.mkstemp(
                prefix=".static-update-", dir=destination_dir
            )
            os.close(file_descriptor)
            shutil.copyfile(source_path, temporary_path)
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.remove(temporary_path)
                except OSError:
                    logger.warning("静的ファイル更新用の一時ファイルを削除できません: {}".format(temporary_path))


class JSONInputError(Exception):
    """JSON入力の読み込み失敗。対象パスと原因を保持します。"""

    def __init__(self, filepath: str, cause: Exception):
        self.filepath = filepath
        self.cause = cause
        super().__init__("{}: {}".format(filepath, cause))


def load_json_data(filepath: str) -> Any:
    """JSON読み込み失敗をNoneに変換せず、対象パスと原因を例外で伝えます。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise JSONInputError(filepath, e) from e


def load_optional_json_data(filepath: str) -> Any:
    """任意JSONの読み込み失敗を警告し、Noneとして返します。"""
    try:
        return load_json_data(filepath)
    except JSONInputError as e:
        logger.warning("任意JSONを利用できません。ファイル '{}'、原因: {}: {}。この情報なしで続行します。".format(
            e.filepath, type(e.cause).__name__, e.cause
        ))
        return None

def get_video_id_from_data_folder(folder_name: str) -> Optional[str]:
    """
    データフォルダ名から動画IDを取得します。
    現行scraperの日時付き形式と、旧日付のみの形式を受け付けます。
    """
    match = re.match(
        r"^youtube_data_([a-zA-Z0-9_-]{11})_(\d{4}-\d{2}-\d{2})(?:_(\d{2})_(\d{2})_(\d{2}))?$",
        folder_name
    )
    return match.group(1) if match else None


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

    def same_reply_content(first: Dict, second: Dict) -> bool:
        """同一返信IDの内容差を検出するための比較。"""
        fields = ("authorDisplayName", "textDisplay", "publishedAt", "likeCount")
        return all(first.get(field) == second.get(field) for field in fields)

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
    duplicate_parent_count = 0
    duplicate_inline_reply_count = 0
    duplicate_external_reply_count = 0

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
            parent_comments = comments_by_parent_id.setdefault(parent_id, [])
            if parent_comments:
                duplicate_parent_count += 1
                first_parent = parent_comments[0]
                if any(first_parent.get(key) != comment_info.get(key)
                       for key in ("authorDisplayName", "textDisplay", "publishedAt")):
                    logger.warning(
                        "親コメントID '{}' の重複レコードで内容が一致しません。"
                        "先に出現したレコードを採用します。".format(parent_id)
                    )
            else:
                processed_comments.append(comment_info)
                parent_comments.append(comment_info)

            # commentThreads.list(part="snippet,replies") の返信プレビューも、
            # 外部返信Rawが部分保存されている場合に利用できるよう保持する。
            replies_container = item.get("replies")
            if replies_container is not None:
                if not isinstance(replies_container, dict):
                    raise ValueError("親コメント '{}' のrepliesが辞書ではありません。".format(parent_id))
                reply_items = replies_container.get("comments", [])
                if not isinstance(reply_items, list):
                    raise ValueError("親コメント '{}' のreplies.commentsがリストではありません。".format(parent_id))
                inline_replies = inline_replies_by_parent_id.setdefault(parent_id, [])
                for reply in reply_items:
                    # 重複判定は外部返信Rawの優先確定後、全親横断で行う。
                    inline_replies.append(normalize_comment(reply, "返信"))

    if duplicate_parent_count:
        logger.warning(
            "親コメントRawに重複IDが{}件あります。"
            "重複表示を避け、先に出現した親コメントを採用しました。".format(duplicate_parent_count)
        )

    # 最後に保存された親コメントページにnextPageTokenが残っている場合、
    # そのRaw配列の後ろに未保存ページが存在する可能性がある。
    if comments_data and isinstance(comments_data[-1], dict) and comments_data[-1].get("nextPageToken"):
        logger.warning(
            "最後の親コメントRawページにnextPageTokenがあります。"
            "後続ページが保存されていない可能性があります（取得状態の判定ではありません）。"
        )

    external_replies_by_parent_id = {}
    reply_id_owner = {}
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
                    reply_id = normalized_reply["id"]
                    previous_parent_id = reply_id_owner.get(reply_id)
                    if previous_parent_id is not None:
                        previous_reply = next(
                            reply for reply in external_replies_by_parent_id.get(previous_parent_id, [])
                            if reply["id"] == reply_id
                        )
                        if not same_reply_content(previous_reply, normalized_reply):
                            logger.warning(
                                "返信ID '{}' の重複Rawで内容が一致しません。"
                                "先に出現した外部Rawを採用します。".format(reply_id)
                            )
                        logger.warning(
                            "返信ID '{}' が外部返信Raw内で重複しています。"
                            "先に出現した親 '{}' のレコードを採用し、親 '{}' の重複を除外します。".format(
                                reply_id, previous_parent_id, parent_id
                            )
                        )
                        duplicate_external_reply_count += 1
                        continue
                    reply_id_owner[reply_id] = parent_id
                    external_replies_by_parent_id.setdefault(parent_id, []).append(normalized_reply)

            # 最後の返信Rawページにtokenが残る場合、後続ページが保存されていない可能性がある。
            if raw_responses and isinstance(raw_responses[-1], dict) and raw_responses[-1].get("nextPageToken"):
                logger.warning(
                    "親コメント '{}' の最後の返信RawページにnextPageTokenがあります。"
                    "後続ページが保存されていない可能性があります（取得状態の判定ではありません）。".format(parent_id)
                )

    if duplicate_external_reply_count:
        logger.warning(
            "返信Rawに重複IDまたは複数親への重複紐付けが{}件あります。"
            "重複表示を避け、先に出現したレコードを採用しました。".format(duplicate_external_reply_count)
        )
    # 外部返信RawのID所有権を先に確定し、その後インライン返信を全親横断で照合する。
    external_reply_id_owner = dict(reply_id_owner)
    accepted_inline_replies_by_parent_id = {}
    accepted_inline_reply_by_id = {}
    for parent_id, inline_replies in inline_replies_by_parent_id.items():
        accepted_inline_replies = accepted_inline_replies_by_parent_id.setdefault(parent_id, [])
        for inline_reply in inline_replies:
            reply_id = inline_reply["id"]
            external_owner_parent_id = external_reply_id_owner.get(reply_id)
            if external_owner_parent_id is not None:
                external_reply = next(
                    reply for reply in external_replies_by_parent_id.get(external_owner_parent_id, [])
                    if reply["id"] == reply_id
                )
                if not same_reply_content(external_reply, inline_reply):
                    logger.warning(
                        "返信ID '{}' の外部Rawとインライン返信で内容が一致しません。"
                        "外部Rawを優先します。".format(reply_id)
                    )
                logger.warning(
                    "返信ID '{}' は外部返信Rawですでに採用済みです。"
                    "外部Rawの親 '{}' を優先し、親 '{}' のインライン返信を除外します。".format(
                        reply_id, external_owner_parent_id, parent_id
                    )
                )
                duplicate_inline_reply_count += 1
                continue

            previous_inline = accepted_inline_reply_by_id.get(reply_id)
            if previous_inline is not None:
                previous_parent_id, previous_reply = previous_inline
                if not same_reply_content(previous_reply, inline_reply):
                    logger.warning(
                        "返信ID '{}' のインライン返信重複で内容が一致しません。"
                        "先に出現したレコードを採用します。".format(reply_id)
                    )
                logger.warning(
                    "返信ID '{}' が複数の親コメントまたは同一親内で重複しています。"
                    "先に出現した親 '{}' のインライン返信を採用し、親 '{}' の重複を除外します。".format(
                        reply_id, previous_parent_id, parent_id
                    )
                )
                duplicate_inline_reply_count += 1
                continue

            # 外部Rawにない返信は、最初に出現した親のインライン返信を採用する。
            reply_id_owner[reply_id] = parent_id
            accepted_inline_reply_by_id[reply_id] = (parent_id, inline_reply)
            accepted_inline_replies.append(inline_reply)

    if duplicate_inline_reply_count:
        logger.warning(
            "親スレッドRaw内の返信プレビュー重複または外部Rawとの重複を{}件除外しました。".format(
                duplicate_inline_reply_count
            )
        )

    # 親コメントが欠落している返信RawはHTMLに紐付けられないため、警告して区別する。
    for parent_id in external_replies_by_parent_id:
        if parent_id not in comments_by_parent_id:
            logger.warning("返信Rawの親コメント '{}' がコメントスレッドRawにありません。返信を表示できません。".format(parent_id))

    # 外部返信Rawと親スレッド内の返信プレビューをIDで統合する。
    # 外部Rawが部分保存でも、プレビューにしかない返信を失わない。
    for parent_id, parent_comments in comments_by_parent_id.items():
        external_replies = external_replies_by_parent_id.get(parent_id, [])
        inline_replies = accepted_inline_replies_by_parent_id.get(parent_id, [])
        selected_replies = list(external_replies) + list(inline_replies)
        expected_reply_count = expected_reply_counts_by_parent_id.get(parent_id, 0)
        if expected_reply_count > len(selected_replies):
            logger.warning(
                "親コメント '{}' の返信はAPI記録上{}件ですが、RAWデータから表示できる返信は{}件です。".format(
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
        logger.info(f"HTMLページを生成しました: {output_filepath}")
        return output_filepath
    except Exception as e:
        logger.error(f"HTMLページの生成中に問題が発生しました: {e}")
        return None # エラー発生時はNoneを返す

def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

    # tkinterのルートウィンドウを作成し、非表示にする
    root = tk.Tk()
    root.withdraw()

    print("動画データ（JSONファイル）が格納されているフォルダを選択してください。")
    print("フォルダ名は 'youtube_data_<動画ID>_<YYYY-MM-DD_HH_MM_SS>' の形式です（旧形式のYYYY-MM-DDも読み込み可能です）。")

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
    folder_video_id = get_video_id_from_data_folder(selected_folder_name)
    if not folder_video_id:
        logger.error("選択されたフォルダ名 '{}' は無効な形式です。".format(selected_folder_name))
        logger.error("形式: youtube_data_<動画ID>_<YYYY-MM-DD_HH_MM_SS>（旧形式のYYYY-MM-DDも可）")
        sys.exit(1) # 無効なフォルダ名の場合、エラー終了

    logger.info(f"選択されたフォルダ: {selected_folder_path}")

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
        logger.error("フォルダ名の動画IDとvideo_infoファイル名の動画IDが一致しません。")
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
    try:
        comments_data = load_json_data(comments_json_path)
    except JSONInputError as e:
        logger.error("必須コメントRawを読み込めません。ファイル '{}'、原因: {}: {}".format(
            e.filepath, type(e.cause).__name__, e.cause
        ))
        sys.exit(1)

    # 返信Rawは任意。欠落・読み込み失敗時はインライン返信のみを使用する。
    replies_data = None
    if os.path.exists(replies_json_path):
        try:
            replies_data = load_json_data(replies_json_path)
        except JSONInputError as e:
            logger.warning("返信Rawを読み込めません。ファイル '{}'、原因: {}: {}。インライン返信のみで続行します。".format(
                e.filepath, type(e.cause).__name__, e.cause
            ))
            replies_data = None
    else:
        logger.warning("返信Rawファイルがありません。親スレッドRaw内に含まれる返信のみ表示します。")

    # 動画・チャンネル情報は任意。欠落・読み込み失敗・items構造不正時は空情報として続行する。
    videos_data = load_optional_json_data(videos_json_path)
    if not isinstance(videos_data, dict) or not isinstance(videos_data.get("items"), list):
        logger.warning("動画情報Rawの構造が不正、または情報がありません。動画情報なしで続行します。")
        videos_data = {"items": []}

    channel_data = load_optional_json_data(channel_json_path) if channel_json_path else None
    if not isinstance(channel_data, dict) or not isinstance(channel_data.get("items"), list):
        logger.warning("チャンネル情報Rawの構造が不正、または情報がありません。チャンネル情報なしで続行します。")
        channel_data = {"items": []}

    try:
        processed_comments = process_youtube_comments(comments_data, replies_data)
    except ValueError as e:
        if replies_data is not None:
            logger.warning("返信Rawの構造が不正です: {}。返信Rawを除外し、インライン返信のみで再処理します。".format(e))
            try:
                processed_comments = process_youtube_comments(comments_data, None)
            except ValueError as comments_error:
                logger.error("コメントRawデータの構造が不正です: {}".format(comments_error))
                sys.exit(1)
        else:
            logger.error("コメントRawデータの構造が不正です: {}".format(e))
            sys.exit(1)



    # 使用するテンプレートを指定 (例: 'pager-template.html' または 'example.html')
    template_to_use = 'pager-template.html' 
    output_html_filename = 'index.html'

    # ユーザーの要求に応じて、example.htmlが存在すればそちらを優先的に使用
    # example.htmlはbundledなのでBUNDLED_DATA_ROOT_DIRから探す
    example_template_path = os.path.join(TEMPLATES_DIR, 'example.html')
    if os.path.exists(example_template_path):
        template_to_use = 'example.html'
        logger.info(f"'{example_template_path}' が見つかったため、このテンプレートを使用します。")
    else:
        logger.info(f"'{example_template_path}' が見つかりません。デフォルトの '{template_to_use}' を使用します。")

    # generate_html_page に選択されたフォルダパスを output_dir として渡す
    generated_filepath = generate_html_page(videos_data, processed_comments, channel_data, template_to_use, output_html_filename, output_dir=selected_folder_path)

    if generated_filepath:
        logger.info(f"HTMLページが正常に生成されました: {generated_filepath}")

        # 同梱staticを生成先へ同期し、利用者独自のファイルは保持する
        target_static_dir = os.path.join(selected_folder_path, 'static')
        try:
            logger.info(f"'{STATIC_DIR}' から '{target_static_dir}' へ静的ファイルを反映しています...")
            sync_static_files(STATIC_DIR, target_static_dir)
            logger.info("静的ファイルの反映が完了しました。")
        except (OSError, shutil.Error) as e:
            logger.error(f"静的ファイルの反映中に問題が発生しました: {e}")
            logger.warning("HTMLページの生成は成功しましたが、staticファイルの反映に問題が発生しました。既存ファイルは可能な限り保持しています。")
    else:
        logger.error("HTMLページの生成に失敗しました。")

if __name__ == '__main__':
    main()
