import unittest

from main import process_youtube_comments


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
            ["reply-1", "reply-2"],
        )
        self.assertEqual(
            [item["id"] for item in result[1]["replies"]],
            ["reply-3"],
        )
        self.assertNotIn("reply-inline", [item["id"] for item in result[0]["replies"]])

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
