import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from examples.publish_tiktok_via_api import (
    Account,
    build_publish_data,
    get_schedule_delta,
    normalize_hashtags,
    parse_datetime,
    publish_task,
)


class TikTokApiPublishTests(unittest.TestCase):
    def setUp(self):
        self.account = Account(
            id=1,
            type=6,
            filePath="tiktok-cookie.json",
            name="tk-account",
            status=1,
        )
        self.task = SimpleNamespace(
            account_name="tk-account",
            output_path="D:/videos/demo.mp4",
            schedule_time=None,
            video_title="TikTok 标题",
            description="视频描述",
            thumbnail_path="D:/videos/demo.png",
            product_link="1732510820131049700",
            product_name="商品展示名称",
        )

    def test_normalize_hashtags_removes_hashes_and_duplicates(self):
        self.assertEqual(
            normalize_hashtags("#猫 #测试,猫"),
            ["猫", "测试"],
        )

    def test_parse_datetime_uses_real_strptime_format(self):
        self.assertIsNotNone(parse_datetime("2099-07-25 18:30:00"))
        self.assertIsNone(parse_datetime("yyyy-mm-dd hh:MM:ss"))

    def test_schedule_payload_matches_backend_start_days_semantics(self):
        now = datetime(2026, 7, 25, 10, 0)
        target = datetime(2026, 7, 27, 18, 30)

        self.assertEqual(
            get_schedule_delta(target, now=now),
            (1, "18:30"),
        )

    def test_build_publish_data_targets_tiktok_and_includes_product(self):
        payload = build_publish_data(
            self.task,
            self.account,
            "#猫 #首饰",
        )

        self.assertEqual(payload["type"], 6)
        self.assertEqual(payload["title"], "TikTok 标题")
        self.assertEqual(payload["description"], "视频描述")
        self.assertEqual(payload["tags"], ["猫", "首饰"])
        self.assertEqual(payload["fileList"], ["D:/videos/demo.mp4"])
        self.assertEqual(payload["accountList"], ["tiktok-cookie.json"])
        self.assertEqual(payload["productLink"], "1732510820131049700")
        self.assertEqual(payload["productTitle"], "商品展示名称")
        self.assertTrue(payload["isAigc"])

    def test_publish_task_posts_to_backend_tiktok_endpoint(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 200, "msg": "发布任务已提交"}
        session = MagicMock()
        session.post.return_value = response

        result = publish_task(
            self.task,
            [self.account],
            ["猫"],
            api_base="http://127.0.0.1:5409/",
            session=session,
        )

        self.assertTrue(result)
        url = session.post.call_args.args[0]
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(url, "http://127.0.0.1:5409/postVideo")
        self.assertEqual(payload["type"], 6)
        self.assertEqual(payload["accountList"], ["tiktok-cookie.json"])


if __name__ == "__main__":
    unittest.main()
