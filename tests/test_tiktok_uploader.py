import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

from uploader.tk_uploader.main_chrome import (
    ADD_LINK_DIALOG,
    ADVANCED_SETTINGS,
    AIGC_CONFIRM_DIALOG,
    AIGC_CONTAINER,
    ANCHOR_CONTAINER,
    CALENDAR_PICKER,
    CAPTION_EDITOR,
    COVER_EDITOR,
    COVER_ENTRY,
    COVER_INPUT,
    POST_BUTTON,
    PRODUCT_DIALOG,
    PRODUCT_ROW,
    PRODUCT_SEARCH_INPUT,
    PRODUCT_SELECTABLE_RADIO,
    PRODUCT_SELECTOR_DIALOG,
    PlaywrightTimeoutError,
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
from myUtils.postVideo import post_video_tiktok
from utils.files_times import generate_schedule_time_next_day


class TiktokUploaderTests(unittest.TestCase):
    def test_upload_page_matches_tiktok_studio_url(self):
        self.assertEqual(TiktokVideo.upload_page, TIKTOK_UPLOAD_URL)

    def test_upload_url_targets_video_tab(self):
        self.assertEqual(
            TIKTOK_UPLOAD_URL,
            "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video",
        )

    def test_stable_selectors_do_not_depend_on_generated_jsx_classes(self):
        self.assertIn('accept*="video"', VIDEO_INPUT)
        self.assertIn("contenteditable", CAPTION_EDITOR)
        self.assertEqual(POST_BUTTON, 'button[data-e2e="post_video_button"]')
        self.assertIn(".cover-container", COVER_ENTRY)
        self.assertIn(".cover-editor-container", COVER_EDITOR)
        self.assertIn('aria-label="Upload cover image"', COVER_INPUT)
        self.assertEqual(AIGC_CONTAINER, '[data-e2e="aigc_container"]')
        self.assertEqual(AIGC_CONFIRM_DIALOG, '[role="dialog"]')
        self.assertEqual(
            ADVANCED_SETTINGS,
            '[data-e2e="advanced_settings_container"]',
        )
        self.assertEqual(ANCHOR_CONTAINER, '[data-e2e="anchor_container"]')
        self.assertIn('[role="dialog"]', ADD_LINK_DIALOG)
        self.assertIn("product-selector-modal", PRODUCT_SELECTOR_DIALOG)
        self.assertEqual(PRODUCT_ROW, "tr.product-tb-row")
        self.assertNotIn("jsx-", PRODUCT_SEARCH_INPUT)
        self.assertNotIn("jsx-", PRODUCT_DIALOG)
        for selector in (COVER_ENTRY, COVER_EDITOR, COVER_INPUT):
            self.assertNotIn("jsx-", selector)

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

    def test_video_input_uploads_selected_file(self):
        video = TiktokVideo("标题", "demo.mp4", [], 0, "cookie.json")
        file_input = MagicMock()
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        query = MagicMock()
        query.first = file_input
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = query

        asyncio.run(video.upload_video_file())

        video.locator_base.locator.assert_called_once_with(VIDEO_INPUT)
        file_input.wait_for.assert_awaited_once_with(
            state="attached",
            timeout=60_000,
        )
        file_input.set_input_files.assert_awaited_once_with("demo.mp4")

    def test_caption_editor_receives_combined_caption(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            ["猫"],
            0,
            "cookie.json",
            description="描述",
        )
        editor = MagicMock()
        editor.wait_for = AsyncMock()
        editor.fill = AsyncMock()
        query = MagicMock()
        query.first = editor
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = query
        page = MagicMock()

        asyncio.run(video.add_title_tags(page))

        self.assertEqual(
            editor.fill.await_args_list,
            [
                call("", timeout=120_000),
                call("标题\n描述 #猫", timeout=120_000),
            ],
        )
        page.keyboard.press.assert_not_called()

    def test_caption_editor_uses_keyboard_fallback_when_fill_times_out(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            ["猫"],
            0,
            "cookie.json",
            description="描述",
        )
        editor = MagicMock()
        editor.wait_for = AsyncMock()
        editor.fill = AsyncMock(side_effect=PlaywrightTimeoutError("blocked"))
        editor.focus = AsyncMock()
        query = MagicMock()
        query.first = editor
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = query
        page = MagicMock()
        page.keyboard.press = AsyncMock()
        page.keyboard.insert_text = AsyncMock()

        asyncio.run(video.add_title_tags(page))

        editor.focus.assert_awaited_once_with(timeout=30_000)
        page.keyboard.press.assert_any_await("Control+A")
        page.keyboard.press.assert_any_await("Backspace")
        page.keyboard.insert_text.assert_awaited_once_with("标题\n描述 #猫")

    def test_upload_browser_uses_runtime_headless_config(self):
        with patch(
            "uploader.tk_uploader.main_chrome.get_local_chrome_headless",
            side_effect=[False, True],
        ):
            visible = TiktokVideo(
                "标题", "demo.mp4", [], 0, "cookie.json"
            )
            headless = TiktokVideo(
                "标题",
                "demo.mp4",
                [],
                0,
                "cookie.json",
                test_mode=True,
            )

        self.assertFalse(visible.headless)
        self.assertTrue(headless.headless)

    def test_cover_upload_uses_editor_input_and_button_content_fallback(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            thumbnail_path="cover.png",
        )
        cover = MagicMock()
        cover.wait_for = AsyncMock()
        cover.click = AsyncMock()
        cover_query = MagicMock()
        cover_query.first = cover

        cover_input = MagicMock()
        cover_input.wait_for = AsyncMock()
        cover_input.set_input_files = AsyncMock()
        cover_input_query = MagicMock()
        cover_input_query.first = cover_input

        missing_role_button = MagicMock()
        missing_role_button.count = AsyncMock(return_value=0)
        role_query = MagicMock()
        role_query.first = missing_role_button

        save_button = MagicMock()
        save_button.wait_for = AsyncMock()
        save_button.click = AsyncMock()
        save_query = MagicMock()
        save_query.first = save_button

        editor = MagicMock()
        editor.wait_for = AsyncMock()
        editor.get_by_role.return_value = role_query
        editor.locator.side_effect = (
            lambda selector: cover_input_query
            if selector == COVER_INPUT
            else save_query
        )
        editor_query = MagicMock()
        editor_query.first = editor

        video.locator_base = MagicMock()
        video.locator_base.locator.side_effect = (
            lambda selector: cover_query
            if selector == COVER_ENTRY
            else editor_query
        )
        page = MagicMock()

        asyncio.run(video.upload_thumbnails(page))

        cover.click.assert_awaited_once()
        cover_input.set_input_files.assert_awaited_once_with("cover.png")
        fallback_selector = editor.locator.call_args_list[-1].args[0]
        self.assertIn("div.Button__content", fallback_selector)
        save_button.click.assert_awaited_once()
        editor.wait_for.assert_awaited_with(state="hidden", timeout=30_000)

    def test_aigc_expands_advanced_settings_and_enables_switch(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            is_aigc=True,
        )
        switch = MagicMock()
        switch.get_attribute = AsyncMock(return_value="false")
        switch.click = AsyncMock()
        switch_query = MagicMock()
        switch_query.first = switch

        container = MagicMock()
        container.count = AsyncMock(return_value=1)
        container.is_visible = AsyncMock(return_value=False)
        container.wait_for = AsyncMock()
        container.locator.return_value = switch_query
        container_query = MagicMock()
        container_query.first = container

        more = MagicMock()
        more.count = AsyncMock(return_value=1)
        more.is_visible = AsyncMock(return_value=True)
        more.click = AsyncMock()
        more_query = MagicMock()
        more_query.first = more

        missing_dialog = MagicMock()
        missing_dialog.wait_for = AsyncMock(
            side_effect=PlaywrightTimeoutError("not shown")
        )
        filtered_dialogs = MagicMock()
        filtered_dialogs.last = missing_dialog
        dialogs = MagicMock()
        dialogs.filter.return_value = filtered_dialogs

        video.locator_base = MagicMock()
        video.locator_base.locator.side_effect = lambda selector: {
            AIGC_CONTAINER: container_query,
            AIGC_CONFIRM_DIALOG: dialogs,
        }.get(selector, more_query)

        asyncio.run(video.set_aigc_content())

        more.click.assert_awaited_once()
        switch.click.assert_awaited_once_with(force=True)
        missing_dialog.wait_for.assert_awaited_once_with(
            state="visible",
            timeout=5_000,
        )

    def test_aigc_confirmation_dialog_clicks_enable(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            is_aigc=True,
        )
        confirm = MagicMock()
        confirm.count = AsyncMock(return_value=1)
        confirm.wait_for = AsyncMock()
        confirm.click = AsyncMock()
        confirm_query = MagicMock()
        confirm_query.last = confirm

        dialog = MagicMock()
        dialog.wait_for = AsyncMock()
        dialog.get_by_role.return_value = confirm_query
        filtered_dialogs = MagicMock()
        filtered_dialogs.last = dialog
        dialogs = MagicMock()
        dialogs.filter.return_value = filtered_dialogs
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = dialogs

        result = asyncio.run(video.confirm_aigc_dialog())

        self.assertTrue(result)
        confirm.click.assert_awaited_once()
        self.assertEqual(
            dialog.wait_for.await_args_list,
            [
                call(state="visible", timeout=5_000),
                call(state="hidden", timeout=30_000),
            ],
        )

    def test_aigc_confirmation_handles_multiple_dialogs_in_sequence(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            is_aigc=True,
        )
        video.confirm_aigc_dialog = AsyncMock(
            side_effect=[True, True, False]
        )

        result = asyncio.run(video.confirm_aigc_dialogs())

        self.assertEqual(result, 2)
        self.assertEqual(
            video.confirm_aigc_dialog.await_args_list,
            [
                call(timeout=5_000),
                call(timeout=2_000),
                call(timeout=2_000),
            ],
        )

    def test_product_link_is_added_before_aigc_setting(self):
        publish_date = datetime(2026, 7, 26, 18, 0)
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            publish_date,
            "cookie.json",
            thumbnail_path="cover.png",
            is_aigc=True,
            product_link="1732510820131049700",
        )
        video.upload_thumbnails = AsyncMock()
        video.add_product_link = AsyncMock()
        video.set_aigc_content = AsyncMock()
        video.set_schedule_time = AsyncMock()
        calls = MagicMock()
        calls.attach_mock(video.upload_thumbnails, "cover")
        calls.attach_mock(video.add_product_link, "product")
        calls.attach_mock(video.set_aigc_content, "aigc")
        calls.attach_mock(video.set_schedule_time, "schedule")
        page = MagicMock()

        asyncio.run(video.prepare_post_settings(page))

        self.assertEqual(
            calls.mock_calls,
            [
                call.cover(page),
                call.product(),
                call.aigc(),
                call.schedule(page, publish_date),
            ],
        )

    def test_publish_uses_stable_data_e2e_button(self):
        video = TiktokVideo("标题", "demo.mp4", [], 0, "cookie.json")
        button = MagicMock()
        button.wait_for = AsyncMock()
        button.click = AsyncMock()
        query = MagicMock()
        query.first = button
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = query
        page = MagicMock()
        page.wait_for_url = AsyncMock()

        asyncio.run(video.click_publish(page))

        video.locator_base.locator.assert_called_once_with(POST_BUTTON)
        button.click.assert_awaited_once()

    def test_upload_status_waits_for_enabled_post_button(self):
        video = TiktokVideo("标题", "demo.mp4", [], 0, "cookie.json")
        button = MagicMock()
        button.count = AsyncMock(return_value=1)
        button.get_attribute = AsyncMock(side_effect=["false", "false"])
        button.is_visible = AsyncMock(return_value=True)
        button.is_enabled = AsyncMock(return_value=True)
        query = MagicMock()
        query.first = button
        video.locator_base = MagicMock()
        video.locator_base.locator.return_value = query

        asyncio.run(video.detect_upload_status(timeout=1))

        video.locator_base.locator.assert_called_once_with(POST_BUTTON)

    def test_legacy_thumbnail_positional_argument_is_preserved(self):
        video = TiktokVideo(
            "标题", "demo.mp4", [], 0, "cookie.json", "cover.png"
        )
        self.assertEqual(video.thumbnail_path, "cover.png")

    def test_product_search_value_accepts_id_or_url(self):
        self.assertEqual(
            TiktokVideo._product_search_value("1732510820131049700"),
            "1732510820131049700",
        )
        self.assertEqual(
            TiktokVideo._product_search_value(
                "https://shop.example/product/1732510820131049700?source=video"
            ),
            "1732510820131049700",
        )

    def test_product_link_selects_matching_available_product_and_adds_name(self):
        video = TiktokVideo(
            "标题",
            "demo.mp4",
            [],
            0,
            "cookie.json",
            product_link="1732510820131049700",
            product_title="商品展示名称",
        )

        add_entry = MagicMock()
        add_entry.count = AsyncMock(return_value=1)
        add_entry.click = AsyncMock()
        add_entry_query = MagicMock()
        add_entry_query.first = add_entry
        anchor = MagicMock()
        anchor.wait_for = AsyncMock()
        anchor.get_by_role.return_value = add_entry_query

        link_type = MagicMock()
        link_type.count = AsyncMock(return_value=1)
        link_type.is_visible = AsyncMock(return_value=True)
        link_type.inner_text = AsyncMock(return_value="商品")
        link_type_query = MagicMock()
        link_type_query.first = link_type
        first_next = MagicMock()
        first_next.wait_for = AsyncMock()
        first_next.click = AsyncMock()
        first_next_query = MagicMock()
        first_next_query.first = first_next
        add_dialog = MagicMock()
        add_dialog.wait_for = AsyncMock()
        add_dialog.get_by_role.side_effect = (
            lambda role, **kwargs: link_type_query
            if role == "combobox"
            else first_next_query
        )

        store_tab = MagicMock()
        store_tab.count = AsyncMock(return_value=1)
        store_tab.is_visible = AsyncMock(return_value=True)
        store_tab.click = AsyncMock()
        store_tab_query = MagicMock()
        store_tab_query.first = store_tab
        second_next = MagicMock()
        second_next.wait_for = AsyncMock()
        second_next.click = AsyncMock()
        second_next_query = MagicMock()
        second_next_query.first = second_next
        search_input = MagicMock()
        search_input.wait_for = AsyncMock()
        search_input.fill = AsyncMock()
        search_input.press = AsyncMock()
        search_query = MagicMock()
        search_query.first = search_input
        radio = MagicMock()
        radio.wait_for = AsyncMock()
        radio.click = AsyncMock()
        radio_query = MagicMock()
        radio_query.first = radio
        matching_rows = MagicMock()
        matching_rows.locator.return_value = radio_query
        rows = MagicMock()
        rows.filter.return_value = matching_rows
        selector_dialog = MagicMock()
        selector_dialog.wait_for = AsyncMock()

        def selector_role(role, **kwargs):
            pattern = kwargs["name"].pattern
            return store_tab_query if "我的商店" in pattern else second_next_query

        selector_dialog.get_by_role.side_effect = selector_role
        selector_dialog.locator.side_effect = (
            lambda selector: search_query
            if selector == PRODUCT_SEARCH_INPUT
            else rows
        )

        name_input = MagicMock()
        name_input.wait_for = AsyncMock()
        name_input.fill = AsyncMock()
        name_input_query = MagicMock()
        name_input_query.first = name_input
        confirm = MagicMock()
        confirm.wait_for = AsyncMock()
        confirm.click = AsyncMock()
        confirm_query = MagicMock()
        confirm_query.first = confirm
        name_dialog = MagicMock()
        name_dialog.wait_for = AsyncMock()
        name_dialog.get_by_label.return_value = name_input_query
        name_dialog.get_by_role.return_value = confirm_query

        anchor_query = MagicMock()
        anchor_query.first = anchor
        add_dialog_query = MagicMock()
        add_dialog_query.last = add_dialog
        selector_dialog_query = MagicMock()
        selector_dialog_query.last = selector_dialog
        name_dialog_query = MagicMock()
        name_dialog_query.last = name_dialog
        video.locator_base = MagicMock()

        def locate(selector):
            return {
                ANCHOR_CONTAINER: anchor_query,
                ADD_LINK_DIALOG: add_dialog_query,
                PRODUCT_SELECTOR_DIALOG: selector_dialog_query,
                PRODUCT_DIALOG: name_dialog_query,
            }[selector]

        video.locator_base.locator.side_effect = locate

        result = asyncio.run(video.add_product_link())

        self.assertTrue(result)
        add_entry.click.assert_awaited_once()
        first_next.click.assert_awaited_once()
        store_tab.click.assert_awaited_once()
        search_input.fill.assert_awaited_once_with("1732510820131049700")
        search_input.press.assert_awaited_once_with("Enter")
        rows.filter.assert_called_once_with(has_text="1732510820131049700")
        matching_rows.locator.assert_called_once_with(PRODUCT_SELECTABLE_RADIO)
        radio.click.assert_awaited_once_with(force=True)
        second_next.click.assert_awaited_once()
        name_input.fill.assert_awaited_once_with("商品展示名称")
        confirm.click.assert_awaited_once()

    def test_post_video_helper_forwards_aigc_product_and_test_mode(self):
        app = MagicMock()
        app.main = AsyncMock()
        with patch(
            "myUtils.postVideo.TiktokVideo",
            return_value=app,
        ) as uploader:
            post_video_tiktok(
                title="标题",
                files=["demo.mp4"],
                tags=["猫"],
                account_file=["cookie.json"],
                description="描述",
                is_aigc=True,
                productLink="1732510820131049700",
                productTitle="商品",
                test_mode=True,
            )

        kwargs = uploader.call_args.kwargs
        self.assertEqual(kwargs["description"], "描述")
        self.assertTrue(kwargs["is_aigc"])
        self.assertEqual(kwargs["product_link"], "1732510820131049700")
        self.assertEqual(kwargs["product_title"], "商品")
        self.assertTrue(kwargs["test_mode"])
        app.main.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
