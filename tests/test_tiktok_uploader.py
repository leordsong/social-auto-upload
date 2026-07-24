import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.tk_uploader.main_chrome import (
    CALENDAR_PICKER,
    CAPTION_EDITOR,
    POST_BUTTON,
    QR_CODE_CANVAS,
    QR_LOADING_MASK,
    SCHEDULE_INPUTS,
    SCHEDULE_RADIO,
    TIME_PICKER,
    TIKTOK_UPLOAD_URL,
    VIDEO_INPUT,
    TiktokVideo,
    capture_ready_tiktok_qr,
)
from utils.files_times import generate_schedule_time_next_day


class TiktokUploaderTests(unittest.TestCase):
    def test_upload_url_targets_video_tab(self):
        self.assertEqual(
            TIKTOK_UPLOAD_URL,
            "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video",
        )

    def test_stable_selectors_do_not_depend_on_generated_jsx_classes(self):
        self.assertIn('accept*="video"', VIDEO_INPUT)
        self.assertIn("contenteditable", CAPTION_EDITOR)
        self.assertEqual(POST_BUTTON, 'button[data-e2e="post_video_button"]')

    def test_schedule_selectors_use_stable_input_attributes(self):
        self.assertIn('value="schedule"', SCHEDULE_RADIO)
        self.assertIn("[readonly]", SCHEDULE_INPUTS)
        self.assertEqual(TIME_PICKER, ".tiktok-timepicker-time-picker-container")
        self.assertEqual(CALENDAR_PICKER, "div.calendar-wrapper")

    def test_qr_capture_waits_for_loading_mask_then_uses_real_canvas(self):
        loading_mask = MagicMock()
        loading_mask.count = AsyncMock(return_value=1)
        loading_mask.is_visible = AsyncMock(side_effect=[True, False])
        canvas = MagicMock()
        canvas.count = AsyncMock(return_value=1)
        canvas.is_visible = AsyncMock(return_value=True)
        canvas.get_attribute = AsyncMock(side_effect=["170", "170"])
        canvas.evaluate = AsyncMock(return_value=True)
        canvas.screenshot = AsyncMock(return_value=b"qr-png")
        page = MagicMock()

        def locate(selector):
            query = MagicMock()
            query.first = loading_mask if selector == QR_LOADING_MASK else canvas
            return query

        page.locator.side_effect = locate
        self.assertIsNone(asyncio.run(capture_ready_tiktok_qr(page)))
        self.assertEqual(asyncio.run(capture_ready_tiktok_qr(page)), b"qr-png")
        canvas.screenshot.assert_awaited_once_with(type="png")

    def test_qr_capture_rejects_small_placeholder_canvas(self):
        loading_mask = MagicMock()
        loading_mask.count = AsyncMock(return_value=0)
        canvas = MagicMock()
        canvas.count = AsyncMock(return_value=1)
        canvas.is_visible = AsyncMock(return_value=True)
        canvas.get_attribute = AsyncMock(side_effect=["32", "32"])
        canvas.screenshot = AsyncMock()
        page = MagicMock()

        def locate(selector):
            query = MagicMock()
            query.first = loading_mask if selector == QR_LOADING_MASK else canvas
            return query

        page.locator.side_effect = locate
        self.assertIsNone(asyncio.run(capture_ready_tiktok_qr(page)))
        canvas.screenshot.assert_not_awaited()

    def test_calendar_month_supports_chinese_english_and_numeric_values(self):
        self.assertEqual(TiktokVideo._parse_calendar_month("七月"), 7)
        self.assertEqual(TiktokVideo._parse_calendar_month("十一月"), 11)
        self.assertEqual(TiktokVideo._parse_calendar_month("July"), 7)
        self.assertEqual(TiktokVideo._parse_calendar_month("Sep."), 9)
        self.assertEqual(TiktokVideo._parse_calendar_month("07月"), 7)

    def test_schedule_time_matches_five_minute_picker(self):
        publish_date = datetime(2026, 7, 25, 14, 13)
        self.assertEqual(
            TiktokVideo._schedule_time_parts(publish_date),
            ("14", "10"),
        )

    def test_web_hhmm_schedule_value_reaches_backend_as_datetime(self):
        result = generate_schedule_time_next_day(
            1,
            videos_per_day=1,
            daily_times=["14:30"],
        )
        self.assertEqual((result[0].hour, result[0].minute), (14, 30))

    def test_set_schedule_uses_radio_then_time_and_date_controls(self):
        video = TiktokVideo("标题", "demo.mp4", [], 0, "cookie.json")
        radio = MagicMock()
        radio.wait_for = AsyncMock()
        radio.is_checked = AsyncMock(return_value=False)
        radio.click = AsyncMock()
        radio_query = MagicMock()
        radio_query.first = radio
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = radio_query
        video._confirm_schedule_storage = AsyncMock(return_value=True)
        video._select_schedule_time = AsyncMock()
        video._select_schedule_date = AsyncMock()

        page = MagicMock()
        page.wait_for_timeout = AsyncMock()
        publish_date = datetime(2026, 7, 25, 14, 10)
        asyncio.run(video.set_schedule_time(page, publish_date))

        video.locator_base.locator.assert_called_once_with(SCHEDULE_RADIO)
        radio.click.assert_awaited_once_with(force=True)
        video._confirm_schedule_storage.assert_awaited_once()
        video._select_schedule_time.assert_awaited_once_with(page, publish_date)
        video._select_schedule_date.assert_awaited_once_with(page, publish_date)

    def test_caption_uses_title_newline_description_then_tags(self):
        video = TiktokVideo(
            " 标题 ",
            "demo.mp4",
            ["#cat", "猫", "cat", ""],
            0,
            "cookie.json",
            description="  第一行描述\n第二行描述  ",
        )
        self.assertEqual(
            video.build_caption(),
            "标题\n第一行描述\n第二行描述 #cat #猫",
        )

    def test_caption_without_description_keeps_tags_after_title(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            "cat, dance，旅行",
            0,
            "cookie.json",
        )
        self.assertEqual(video.build_caption(), "标题 #cat #dance #旅行")

    def test_legacy_thumbnail_positional_argument_is_preserved(self):
        video = TiktokVideo(
            "标题", "demo.mp4", [], 0, "cookie.json", "cover.png"
        )
        self.assertEqual(video.thumbnail_path, "cover.png")

    def test_product_link_is_explicitly_reported_as_not_attached(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            product_link="https://shop.example/item",
            product_title="商品",
        )
        with patch("uploader.tk_uploader.main_chrome.tiktok_logger.warning") as warning:
            result = asyncio.run(video.add_product_link())
        self.assertFalse(result)
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
