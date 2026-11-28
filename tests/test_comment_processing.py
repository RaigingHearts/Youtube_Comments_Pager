import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
from main import get_video_id_from_data_folder, process_youtube_comments


def make_comment(comment_id, text, author="TestUser"):
    return {
        "id": comment_id,
        "snippet": {
            "authorDisplayName": author,
            "authorProfileImageUrl": "https://example.com/avatar.png",
            "textDisplay": text,
            "publishedAt": "2026-01-01T00:00:00Z",
            "likeCount": 1,
        },
    }


def make_thread(comment_id, inline_replies=None):
    item = {
        "snippet": {
            "topLevelComment": make_comment(comment_id, "parent-" + comment_id),
            "totalReplyCount": len(inline_replies or []),
        }
    }
    if inline_replies is not None:
        item["replies"] = {"comments": inline_replies}
    return item


def make_thread_page(*items):
    return {"items": list(items)}


def make_reply_page(*items):
    return {"items": list(items)}


class JSONInputLoadingTests(unittest.TestCase):
    def test_loads_valid_empty_json_list(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
            file.write("[]")
            filepath = file.name
        try:
            self.assertEqual(main.load_json_data(filepath), [])
        finally:
            os.remove(filepath)

    def test_missing_json_raises_with_path_and_cause(self):
        filepath = os.path.join(tempfile.gettempdir(), "pager-missing-input-test.json")
        if os.path.exists(filepath):
            os.remove(filepath)
        with self.assertRaises(main.JSONInputError) as raised:
            main.load_json_data(filepath)
        self.assertEqual(raised.exception.filepath, filepath)
        self.assertIsInstance(raised.exception.cause, FileNotFoundError)

    def test_invalid_json_raises_with_path_and_cause(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
            file.write("{invalid json")
            filepath = file.name
        try:
            with self.assertRaises(main.JSONInputError) as raised:
                main.load_json_data(filepath)
            self.assertEqual(raised.exception.filepath, filepath)
            self.assertIsInstance(raised.exception.cause, json.JSONDecodeError)
        finally:
            os.remove(filepath)


class DataFolderNameTests(unittest.TestCase):
    def test_extracts_video_id_from_current_timestamp_folder(self):
        self.assertEqual(
            get_video_id_from_data_folder("youtube_data_9SAhwYXG4Uc_2026-11-27_01_46_19"),
            "9SAhwYXG4Uc",
        )

    def test_accepts_legacy_date_only_folder(self):
        self.assertEqual(
            get_video_id_from_data_folder("youtube_data_9SAhwYXG4Uc_2026-11-27"),
            "9SAhwYXG4Uc",
        )

    def test_rejects_invalid_folder_name(self):
        self.assertIsNone(get_video_id_from_data_folder("youtube_data_invalid_2026-11-27"))


class ProcessYoutubeCommentsTests(unittest.TestCase):
    def test_reads_all_thread_pages_and_all_reply_pages_by_parent_id(self):
        inline = make_comment("reply-inline", "inline-preview")
        comments_data = [
            make_thread_page(make_thread("parent-1", [inline])),
            make_thread_page(make_thread("parent-2")),
        ]
        replies_data = [
            {
                "parent_id": "parent-1",
                "raw_responses": [
                    make_reply_page(make_comment("reply-1", "reply-page-1")),
                    make_reply_page(make_comment("reply-2", "reply-page-2")),
                ],
            },
            {
                "parent_id": "parent-2",
                "raw_responses": [
                    make_reply_page(make_comment("reply-3", "reply-page-3")),
                ],
            },
        ]

        result = process_youtube_comments(comments_data, replies_data)

        self.assertEqual([item["id"] for item in result], ["parent-1", "parent-2"])
        self.assertEqual(
            [item["id"] for item in result[0]["replies"]],
            ["reply-1", "reply-2", "reply-inline"],
        )
        self.assertEqual(
            [item["id"] for item in result[1]["replies"]],
            ["reply-3"],
        )
        self.assertIn("reply-inline", [item["id"] for item in result[0]["replies"]])

    def test_uses_inline_replies_when_separate_reply_data_is_missing(self):
        inline = make_comment("reply-inline", "available-inline-reply")
        result = process_youtube_comments(
            [make_thread_page(make_thread("parent-1", [inline]))],
            None,
        )

        self.assertEqual([item["id"] for item in result[0]["replies"]], ["reply-inline"])

    def test_uses_inline_replies_when_reply_record_has_no_items(self):
        inline = make_comment("reply-inline", "available-inline-reply")
        replies_data = [
            {"parent_id": "parent-1", "raw_responses": [make_reply_page()]}
        ]
        result = process_youtube_comments(
            [make_thread_page(make_thread("parent-1", [inline]))],
            replies_data,
        )

        self.assertEqual([item["id"] for item in result[0]["replies"]], ["reply-inline"])

    def test_deduplicates_duplicate_parent_and_reply_ids(self):
        inline_1 = make_comment("inline-1", "inline-preview-1")
        inline_2 = make_comment("inline-2", "inline-preview-2")
        comments_data = [
            make_thread_page(make_thread("parent-1", [inline_1])),
            make_thread_page(make_thread("parent-1", [inline_1, inline_2]), make_thread("parent-2")),
        ]
        replies_data = [
            {"parent_id": "parent-1", "raw_responses": [make_reply_page(make_comment("reply-1", "reply-1"))]},
            {"parent_id": "parent-1", "raw_responses": [make_reply_page(make_comment("reply-1", "duplicate-reply-1"), make_comment("reply-2", "reply-2"))]},
        ]

        with self.assertLogs("main", level="WARNING") as captured:
            result = process_youtube_comments(comments_data, replies_data)

        self.assertEqual([item["id"] for item in result], ["parent-1", "parent-2"])
        self.assertEqual([item["id"] for item in result[0]["replies"]], ["reply-1", "reply-2", "inline-1", "inline-2"])
        self.assertTrue(any("重複ID" in message for message in captured.output))

    def test_deduplicates_inline_reply_id_across_different_parents(self):
        shared_reply = make_comment("shared-inline", "first-parent-copy")
        comments_data = [
            make_thread_page(make_thread("parent-1", [shared_reply])),
            make_thread_page(make_thread("parent-2", [
                make_comment("shared-inline", "second-parent-copy")
            ])),
        ]

        with self.assertLogs("main", level="WARNING") as captured:
            result = process_youtube_comments(comments_data)

        self.assertEqual([item["id"] for item in result[0]["replies"]], ["shared-inline"])
        self.assertEqual(result[0]["replies"][0]["textDisplay"], "first-parent-copy")
        self.assertEqual(result[1]["replies"], [])
        self.assertTrue(any("複数の親コメント" in message or "重複" in message
                            for message in captured.output))

    def test_external_reply_raw_wins_over_different_inline_copy(self):
        inline_copy = make_comment("reply-shared", "inline-different-content")
        comments_data = [
            make_thread_page(make_thread("parent-1")),
            make_thread_page(make_thread("parent-2", [inline_copy])),
        ]
        replies_data = [
            {
                "parent_id": "parent-1",
                "raw_responses": [make_reply_page(
                    make_comment("reply-shared", "external-authoritative-content")
                )],
            }
        ]

        with self.assertLogs("main", level="WARNING") as captured:
            result = process_youtube_comments(comments_data, replies_data)

        self.assertEqual(
            [item["id"] for item in result[0]["replies"]],
            ["reply-shared"],
        )
        self.assertEqual(
            result[0]["replies"][0]["textDisplay"],
            "external-authoritative-content",
        )
        self.assertEqual(result[1]["replies"], [])
        log_output = "\\n".join(captured.output)
        self.assertIn("外部Rawとインライン返信で内容が一致しません", log_output)
        self.assertIn("外部返信Rawですでに採用済み", log_output)

    def test_warns_when_last_saved_raw_page_has_next_page_token(self):
        comments_data = [{"items": [make_thread("parent-1")], "nextPageToken": "more-comments"}]
        replies_data = [{"parent_id": "parent-1", "raw_responses": [{"items": [make_comment("reply-1", "reply-1")], "nextPageToken": "more-replies"}]}]

        with self.assertLogs("main", level="WARNING") as captured:
            process_youtube_comments(comments_data, replies_data)

        log_output = "\n".join(captured.output)
        self.assertIn("最後の親コメントRawページにnextPageToken", log_output)
        self.assertIn("最後の返信RawページにnextPageToken", log_output)
        self.assertIn("取得状態の判定ではありません", log_output)


    def test_warns_when_reply_count_exceeds_available_partial_raw_replies(self):
        inline_replies = [
            make_comment("reply-{}".format(index), "inline-{}".format(index))
            for index in range(1, 6)
        ]
        thread = make_thread("parent-partial", inline_replies)
        thread["snippet"]["totalReplyCount"] = 6
        replies_data = [{
            "parent_id": "parent-partial",
            "raw_responses": [make_reply_page(*inline_replies)],
        }]

        with self.assertLogs("main", level="WARNING") as captured:
            result = process_youtube_comments(
                [make_thread_page(thread)],
                replies_data,
            )

        self.assertEqual(len(result[0]["replies"]), 5)
        self.assertTrue(any("API記録上6件" in message and "表示できる返信は5件" in message
                            for message in captured.output))

    def test_valid_empty_thread_list_is_not_treated_as_missing(self):
        self.assertEqual(process_youtube_comments([]), [])

    def test_rejects_non_list_thread_data(self):
        with self.assertRaises(ValueError):
            process_youtube_comments(None)

    def test_rejects_thread_page_without_items(self):
        with self.assertRaises(ValueError):
            process_youtube_comments([{}])

    def test_rejects_malformed_reply_raw_data(self):
        with self.assertRaises(ValueError):
            process_youtube_comments(
                [make_thread_page(make_thread("parent-1"))],
                [{"parent_id": "parent-1", "raw_responses": [{}]}],
            )


class ExternalReplyCrossParentDedupTests(unittest.TestCase):
    def test_duplicate_external_reply_id_keeps_first_parent_and_warns(self):
        duplicate_reply = make_comment("reply-duplicate", "same-reply")
        comments_data = [
            make_thread_page(make_thread("parent-first")),
            make_thread_page(make_thread("parent-later")),
        ]
        replies_data = [
            {
                "parent_id": "parent-first",
                "raw_responses": [make_reply_page(duplicate_reply)],
            },
            {
                "parent_id": "parent-later",
                "raw_responses": [make_reply_page(duplicate_reply)],
            },
        ]

        with self.assertLogs("main", level="WARNING") as captured:
            result = process_youtube_comments(comments_data, replies_data)

        self.assertEqual(
            [reply["id"] for reply in result[0]["replies"]],
            ["reply-duplicate"],
        )
        self.assertEqual(result[1]["replies"], [])
        self.assertTrue(
            any("先に出現した親 'parent-first'" in message
                and "親 'parent-later' の重複を除外" in message
                for message in captured.output),
            captured.output,
        )


class MainVideoIdValidationTests(unittest.TestCase):
    def test_exits_when_folder_and_video_info_filename_ids_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder_path = os.path.join(
                temp_dir,
                "youtube_data_9SAhwYXG4Uc_2026-11-27_01_46_19",
            )
            os.makedirs(folder_path)
            mismatched_video_info = os.path.join(
                folder_path,
                "video_info_raw_AAAAAAAAAAA.json",
            )
            with open(mismatched_video_info, "w", encoding="utf-8"):
                pass

            with patch("main.tk.Tk"):
                with patch(
                    "main.filedialog.askdirectory",
                    return_value=folder_path,
                ):
                    with patch("main.load_json_data") as load_json_data:
                        with self.assertRaises(SystemExit) as raised:
                            main.main()

            self.assertEqual(raised.exception.code, 1)
            load_json_data.assert_not_called()

class MainRequiredInputTests(unittest.TestCase):
    def test_exits_with_filename_and_cause_when_required_comments_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder_path = os.path.join(
                temp_dir,
                "youtube_data_9SAhwYXG4Uc_2026-11-27_01_46_19",
            )
            os.makedirs(folder_path)
            with patch("main.tk.Tk"):
                with patch("main.filedialog.askdirectory", return_value=folder_path):
                    with self.assertLogs("main", level="ERROR") as captured:
                        with self.assertRaises(SystemExit) as raised:
                            main.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertTrue(any("comments_raw_9SAhwYXG4Uc.json" in message
                                and "FileNotFoundError" in message
                                for message in captured.output), captured.output)


if __name__ == "__main__":
    unittest.main()
