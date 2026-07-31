import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from uploader.bilibili_uploader.main import BilibiliVideo
from uploader.douyin_uploader.main import DouYinVideo
from uploader.ks_uploader.main import KSVideo
from uploader.tencent_uploader.main import TencentVideo
from uploader.tk_uploader.main_chrome import TiktokVideo


def build_page_with_action_button():
    button = MagicMock()
    button.count = AsyncMock(return_value=1)
    button.is_visible = AsyncMock(return_value=True)
    button.click = AsyncMock()

    empty_dialog = MagicMock()
    empty_dialog.count = AsyncMock(return_value=0)

    page = MagicMock()
    page.once = MagicMock()
    page.wait_for_timeout = AsyncMock()

    def locate(selector):
        query = MagicMock()
        if selector == '[role="dialog"]:visible':
            query.last = empty_dialog
        else:
            query.first = button
            query.last = button
        return query

    page.locator.side_effect = locate
    return page, button


class UploaderTestModeTests(unittest.TestCase):
    def test_douyin_test_mode_clicks_save_and_exit(self):
        app = DouYinVideo.__new__(DouYinVideo)
        page, button = build_page_with_action_button()

        asyncio.run(app.save_test_draft(page))

        button.click.assert_awaited_once()

    def test_kuaishou_test_mode_clicks_cancel(self):
        app = KSVideo.__new__(KSVideo)
        page, button = build_page_with_action_button()

        asyncio.run(app.cancel_test_upload(page))

        button.click.assert_awaited_once()

    def test_bilibili_test_mode_clicks_save_draft(self):
        app = BilibiliVideo.__new__(BilibiliVideo)
        page, button = build_page_with_action_button()

        asyncio.run(app._save_draft(page))

        button.click.assert_awaited_once()

    def test_tencent_test_mode_clicks_save_draft(self):
        app = TencentVideo.__new__(TencentVideo)
        app.is_draft = True
        page, button = build_page_with_action_button()

        asyncio.run(app.submit_publish(page))

        button.click.assert_awaited_once()

    def test_tiktok_test_mode_clicks_discard(self):
        app = TiktokVideo(
            "title",
            "video.mp4",
            [],
            0,
            "account.json",
            test_mode=True,
        )
        page, button = build_page_with_action_button()
        role_query = MagicMock()
        role_query.first = button
        app.locator_base = MagicMock()
        app.locator_base.get_by_role.return_value = role_query

        asyncio.run(app.click_discard(page))

        self.assertTrue(app.test_mode)
        button.click.assert_awaited_once()

    def test_tencent_test_mode_forces_draft(self):
        app = TencentVideo(
            "title",
            "video.mp4",
            [],
            0,
            "account.json",
            test_mode=True,
        )

        self.assertTrue(app.test_mode)
        self.assertTrue(app.is_draft)


if __name__ == "__main__":
    unittest.main()
