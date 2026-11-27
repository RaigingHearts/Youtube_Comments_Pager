import unittest
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


if __name__ == "__main__":
    unittest.main()
