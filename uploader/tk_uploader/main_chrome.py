# -*- coding: utf-8 -*-
"""TikTok Studio browser uploader.

The TikTok page is localized and its generated ``jsx-*`` class names change
frequently.  Prefer semantic attributes supplied by TikTok (``data-e2e``,
``role`` and input ``accept`` values) and only use stable class fragments as
fallbacks.
"""

import asyncio
import calendar
import os
import re
from time import monotonic

try:
    from patchright.async_api import (
        Playwright,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
except ImportError:  # Backward compatibility for older installations.
    from playwright.async_api import (  # type: ignore[no-redef]
        Playwright,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )

from conf import LOCAL_CHROME_PATH
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.files_times import get_absolute_path
from utils.log import tiktok_logger
from utils.runtime_config import get_local_chrome_headless


TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"
VIDEO_INPUT = 'input[type="file"][accept*="video"]'
CAPTION_EDITOR = (
    'div.public-DraftEditor-content[contenteditable="true"], '
    '[contenteditable="true"][role="combobox"]'
)
POST_BUTTON = 'button[data-e2e="post_video_button"]'
COVER_ENTRY = (
    ".cover-container, "
    "div:has(> img.cover-image):has-text('编辑封面'), "
    "div:has(> img.cover-image):has-text('Edit cover')"
)
COVER_EDITOR = ".cover-editor-container, [class*='cover-editor-container']"
COVER_INPUT = (
    'label[role="button"][aria-label="Upload cover image"] input[type="file"], '
    'label[aria-label="上传封面"] input[type="file"], '
    'input[type="file"][accept*="image/jpeg"], '
    'input[type="file"][accept*="image/png"]'
)
AIGC_CONTAINER = '[data-e2e="aigc_container"]'
ADVANCED_SETTINGS = '[data-e2e="advanced_settings_container"]'
AIGC_CONFIRM_DIALOG = '[role="dialog"]'
ANCHOR_CONTAINER = '[data-e2e="anchor_container"]'
ADD_LINK_DIALOG = (
    '[role="dialog"][title="添加链接"], '
    '[role="dialog"][title="Add link"]'
)
PRODUCT_DIALOG = (
    '[role="dialog"][title="添加商品链接"], '
    '[role="dialog"][title="Add product link"]'
)
PRODUCT_SELECTOR_DIALOG = (
    '[role="dialog"].product-selector-modal[title="添加商品链接"], '
    '[role="dialog"].product-selector-modal[title="Add product link"]'
)
PRODUCT_SEARCH_INPUT = (
    '.product-search-input input[type="text"], '
    'input[placeholder="搜索商品"], '
    'input[placeholder="Search products"], '
    'input[placeholder="Search product"]'
)
PRODUCT_ROW = "tr.product-tb-row"
PRODUCT_SELECTABLE_RADIO = 'input[type="radio"]:not([disabled])'
SCHEDULE_RADIO = 'input[type="radio"][name="postSchedule"][value="schedule"]'
SCHEDULE_INPUTS = 'input.TUXTextInputCore-input[type="text"][readonly]'
TIME_PICKER = ".tiktok-timepicker-time-picker-container"
CALENDAR_PICKER = "div.calendar-wrapper"
QR_CODE_CANVAS = '[data-e2e="qr-code"] canvas'
QR_LOADING_MASK = 'div[class*="DivCodeMask"]'


def _browser_options(headless):
    options = {
        "headless": headless,
        "args": ["--lang=zh-CN", "--disable-blink-features=AutomationControlled"],
    }
    if LOCAL_CHROME_PATH:
        options["executable_path"] = LOCAL_CHROME_PATH
    return options


async def capture_ready_tiktok_qr(page):
    """Return QR PNG bytes only after TikTok's loading mask is gone."""
    loading_mask = page.locator(QR_LOADING_MASK).first
    if await loading_mask.count() and await loading_mask.is_visible():
        return None

    canvas = page.locator(QR_CODE_CANVAS).first
    if not await canvas.count() or not await canvas.is_visible():
        return None

    width = int((await canvas.get_attribute("width")) or 0)
    height = int((await canvas.get_attribute("height")) or 0)
    if width < 100 or height < 100:
        return None

    try:
        is_drawn = await canvas.evaluate(
            """element => {
                const context = element.getContext('2d');
                if (!context) return false;
                const pixels = context.getImageData(
                    0, 0, element.width, element.height
                ).data;
                let dark = 0;
                let light = 0;
                for (let index = 0; index < pixels.length; index += 16) {
                    const average =
                        (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3;
                    if (average < 80 && pixels[index + 3] > 0) dark += 1;
                    if (average > 200 && pixels[index + 3] > 0) light += 1;
                    if (dark > 20 && light > 20) return true;
                }
                return false;
            }"""
        )
        if not is_drawn:
            return None
    except Exception as exc:
        # Dimensions and the data-e2e container still distinguish this canvas
        # from TikTok's 32x32 loading SVG if pixel inspection is unavailable.
        tiktok_logger.debug(f"TikTok QR pixel inspection unavailable: {exc}")

    return await canvas.screenshot(type="png")


async def cookie_auth(account_file):
    """Return whether a storage-state file can open TikTok Studio."""
    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                **_browser_options(get_local_chrome_headless())
            )
            context = await browser.new_context(storage_state=str(account_file))
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60_000)

            try:
                await page.locator(
                    f'{VIDEO_INPUT}, [data-e2e="select_video_container"], {POST_BUTTON}'
                ).first.wait_for(state="attached", timeout=15_000)
                tiktok_logger.success("[+] TikTok cookie valid")
                return True
            except PlaywrightTimeoutError:
                is_login_page = "/login" in page.url or await page.locator(
                    'input[name="username"], [data-e2e*="login"], form[action*="login"]'
                ).count()
                if is_login_page:
                    tiktok_logger.error("[+] TikTok cookie expired")
                    return False
                tiktok_logger.error("[+] TikTok Studio did not become ready")
                return False
    except Exception as exc:
        tiktok_logger.error(f"[+] TikTok cookie validation failed: {exc}")
        return False
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


async def tiktok_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "tk_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        tiktok_logger.info(
            "[+] TikTok cookie is missing or expired. A browser will open for login."
        )
        await get_tiktok_cookie(account_file)
    return True


async def get_tiktok_cookie(account_file):
    """Open a headed login page and persist its authenticated storage state."""
    async with async_playwright() as playwright:
        options = _browser_options(False)
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto(TIKTOK_LOGIN_URL, wait_until="domcontentloaded")
        tiktok_logger.info("[+] Complete TikTok login in the opened browser, then resume Playwright.")
        await page.pause()
        account_dir = os.path.dirname(str(account_file))
        if account_dir:
            os.makedirs(account_dir, exist_ok=True)
        await context.storage_state(path=str(account_file))
        await context.close()
        await browser.close()


class TiktokVideo:
    upload_page = TIKTOK_UPLOAD_URL

    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date,
        account_file,
        thumbnail_path=None,
        description="",
        is_aigc=True,
        product_link="",
        product_title="",
        test_mode=False,
    ):
        self.title = (title or "").strip()
        self.description = (description or "").strip()
        self.file_path = str(file_path)
        self.tags = self._normalize_tags(tags)
        self.publish_date = publish_date
        self.thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        self.is_aigc = bool(is_aigc)
        self.product_link = (product_link or "").strip()
        self.product_title = (product_title or "").strip()
        self.test_mode = bool(test_mode)
        self.account_file = str(account_file)
        self.headless = get_local_chrome_headless()
        self.locator_base = None

    @staticmethod
    def _normalize_tags(tags):
        if not tags:
            return []
        if isinstance(tags, str):
            tags = re.split(r"[,，\s]+", tags)
        normalized = []
        for tag in tags:
            value = str(tag).strip().lstrip("#")
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def build_caption(self):
        """Build title, description and tags in TikTok's single caption field."""
        lines = [self.title]
        if self.description:
            lines.append(self.description)
        caption = "\n".join(lines)
        if self.tags:
            caption = f"{caption} {' '.join(f'#{tag}' for tag in self.tags)}"
        return caption

    async def choose_base_locator(self, page):
        iframe = page.locator(Tk_Locator.tk_iframe)
        if await iframe.count():
            self.locator_base = page.frame_locator(Tk_Locator.tk_iframe)
        else:
            self.locator_base = page.locator(Tk_Locator.default)

    async def upload_video_file(self):
        video_input = self.locator_base.locator(VIDEO_INPUT).first
        await video_input.wait_for(state="attached", timeout=60_000)
        await video_input.set_input_files(self.file_path)

    async def add_title_tags(self, page):
        editor = self.locator_base.locator(CAPTION_EDITOR).first
        await editor.wait_for(state="visible", timeout=120_000)
        caption = self.build_caption()
        try:
            # fill() does not require pointer events, so it still works while
            # TikTok's upload/progress layer overlaps the editor. Clear the
            # filename populated by TikTok before inserting our own caption.
            await editor.fill("", timeout=120_000)
            await editor.fill(caption, timeout=120_000)
        except PlaywrightTimeoutError:
            # Keep a keyboard fallback for DraftJS variants that reject fill().
            await editor.focus(timeout=30_000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.insert_text(caption)

    async def upload_thumbnails(self, page):
        cover = self.locator_base.locator(COVER_ENTRY).first
        await cover.wait_for(state="visible", timeout=120_000)
        await cover.click()

        editor = self.locator_base.locator(COVER_EDITOR).first
        await editor.wait_for(state="visible", timeout=15_000)

        cover_input = editor.locator(COVER_INPUT).first
        await cover_input.wait_for(state="attached", timeout=10_000)
        await cover_input.set_input_files(self.thumbnail_path)

        save_button = editor.get_by_role(
            "button", name=re.compile(r"^(保存|Save|Confirm|确认)$", re.I)
        ).first
        if not await save_button.count():
            save_button = editor.locator(
                "button:has-text('保存'), button:has-text('Save'), "
                "button:has-text('确认'), button:has-text('Confirm'), "
                "div.Button__content:has-text('保存'), "
                "div.Button__content:has-text('Save')"
            ).first
        await save_button.wait_for(state="visible", timeout=15_000)
        await save_button.click()
        await editor.wait_for(state="hidden", timeout=30_000)

    async def set_aigc_content(self):
        container = self.locator_base.locator(AIGC_CONTAINER).first
        if not await container.count() or not await container.is_visible():
            more = self.locator_base.locator(
                f'{ADVANCED_SETTINGS}.collapsed .more-btn, '
                f'{ADVANCED_SETTINGS} :text-is("显示更多"), '
                f'{ADVANCED_SETTINGS} :text-is("Show more")'
            ).first
            if await more.count() and await more.is_visible():
                await more.click()

        await container.wait_for(state="visible", timeout=10_000)
        switch = container.locator('[role="switch"]').first
        checked = await switch.get_attribute("aria-checked")
        if checked is None:
            try:
                checked = "true" if await switch.is_checked() else "false"
            except Exception:
                checked = await container.locator("[data-state]").first.get_attribute("data-state")
                checked = "true" if checked == "checked" else "false"
        if (checked == "true") != self.is_aigc:
            await switch.click(force=True)
            if self.is_aigc:
                await self.confirm_aigc_dialog()

    async def confirm_aigc_dialog(self):
        """Confirm TikTok's optional first-time AI-content disclosure dialog."""
        dialogs = self.locator_base.locator(AIGC_CONFIRM_DIALOG)
        dialog = dialogs.filter(
            has_text=re.compile(
                r"(标记\s*AI\s*生成的内容|Label AI-generated content|"
                r"AI-generated content)",
                re.I,
            )
        ).last
        try:
            await dialog.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError:
            return False

        confirm = dialog.get_by_role(
            "button",
            name=re.compile(r"^(开启|Turn on|Enable)$", re.I),
        ).last
        if not await confirm.count():
            confirm = dialog.locator(
                "button:has-text('开启'), "
                "button:has-text('Turn on'), "
                "button:has-text('Enable')"
            ).last
        await confirm.wait_for(state="visible", timeout=10_000)
        await confirm.click()
        await dialog.wait_for(state="hidden", timeout=30_000)
        return True

    @staticmethod
    def _product_search_value(value):
        """Accept a raw product ID or extract a long numeric ID from a URL."""
        match = re.search(r"(?<!\d)(\d{8,})(?!\d)", value or "")
        return match.group(1) if match else (value or "").strip()

    @staticmethod
    async def _modal_button(modal, names):
        button = modal.get_by_role(
            "button", name=re.compile(rf"^({'|'.join(names)})$", re.I)
        ).first
        await button.wait_for(state="visible", timeout=30_000)
        return button

    async def add_product_link(self):
        """Attach a TikTok Shop product by product ID."""
        if not self.product_link:
            return True

        product_id = self._product_search_value(self.product_link)
        if not product_id:
            raise ValueError("TikTok product ID cannot be empty")

        try:
            anchor = self.locator_base.locator(ANCHOR_CONTAINER).first
            await anchor.wait_for(state="visible", timeout=30_000)
            add_entry = anchor.get_by_role(
                "button", name=re.compile(r"^(添加|Add)$", re.I)
            ).first
            if not await add_entry.count():
                add_entry = anchor.locator(
                    'button:has([data-icon="Plus"]), '
                    'button:has([data-testid="Plus"])'
                ).first
            await add_entry.click()

            add_dialog = self.locator_base.locator(ADD_LINK_DIALOG).last
            await add_dialog.wait_for(state="visible", timeout=30_000)

            link_type = add_dialog.get_by_role("combobox").first
            if await link_type.count() and await link_type.is_visible():
                selected_type = await link_type.inner_text()
                if not re.search(r"(商品|Product)", selected_type, re.I):
                    await link_type.click()
                    product_option = self.locator_base.get_by_role(
                        "option", name=re.compile(r"^(商品|Product)$", re.I)
                    ).first
                    await product_option.click()

            next_button = await self._modal_button(
                add_dialog, ("下一步", "Next")
            )
            await next_button.click()
            await add_dialog.wait_for(state="hidden", timeout=30_000)

            selector_dialog = self.locator_base.locator(
                PRODUCT_SELECTOR_DIALOG
            ).last
            await selector_dialog.wait_for(state="visible", timeout=30_000)

            store_tab = selector_dialog.get_by_role(
                "button",
                name=re.compile(r"^(我的商店|My (shop|store))$", re.I),
            ).first
            if await store_tab.count() and await store_tab.is_visible():
                await store_tab.click()

            search_input = selector_dialog.locator(PRODUCT_SEARCH_INPUT).first
            await search_input.wait_for(state="visible", timeout=30_000)
            await search_input.fill(product_id)
            await search_input.press("Enter")

            matching_rows = selector_dialog.locator(PRODUCT_ROW).filter(
                has_text=product_id
            )
            radio = matching_rows.locator(PRODUCT_SELECTABLE_RADIO).first
            try:
                await radio.wait_for(state="visible", timeout=30_000)
            except PlaywrightTimeoutError as exc:
                raise LookupError(
                    f"TikTok product {product_id} was not found or is unavailable"
                ) from exc
            await radio.click(force=True)

            next_button = await self._modal_button(
                selector_dialog, ("下一步", "Next")
            )
            await next_button.click()
            await selector_dialog.wait_for(state="hidden", timeout=30_000)

            name_dialog = self.locator_base.locator(PRODUCT_DIALOG).last
            await name_dialog.wait_for(state="visible", timeout=30_000)
            if self.product_title:
                name_input = name_dialog.get_by_label(
                    re.compile(r"^(商品名称|Product name)$", re.I)
                ).first
                await name_input.wait_for(state="visible", timeout=30_000)
                await name_input.fill(self.product_title[:30])

            confirm_button = await self._modal_button(
                name_dialog, ("添加", "Add")
            )
            await confirm_button.click()
            await name_dialog.wait_for(state="hidden", timeout=30_000)
            tiktok_logger.info(f"[+] TikTok product attached: {product_id}")
            return True
        except Exception as exc:
            raise RuntimeError(
                f"Failed to attach TikTok product {product_id}: {exc}"
            ) from exc

    async def handle_upload_error(self):
        tiktok_logger.info("[+] Retrying TikTok video file selection")
        await self.upload_video_file()

    async def detect_upload_status(self, timeout=600):
        post_button = self.locator_base.locator(POST_BUTTON).first
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if await post_button.count():
                aria_disabled = await post_button.get_attribute("aria-disabled")
                data_disabled = await post_button.get_attribute("data-disabled")
                if (
                    await post_button.is_visible()
                    and await post_button.is_enabled()
                    and aria_disabled != "true"
                    and data_disabled != "true"
                ):
                    tiktok_logger.info("  [-] TikTok video uploaded")
                    return

            retry_button = self.locator_base.locator(
                'button[aria-label="Select file"], button[aria-label="选择视频"]'
            ).first
            error_text = self.locator_base.get_by_text(
                re.compile(r"(upload failed|重新上传|上传失败|retry)", re.I)
            ).first
            if await retry_button.count() and await error_text.count():
                await self.handle_upload_error()
            await asyncio.sleep(2)
        raise TimeoutError("TikTok video processing timed out before the Post button was enabled")

    @staticmethod
    def _parse_calendar_month(value):
        text = re.sub(r"\s+", "", (value or "")).lower()
        numeric = re.fullmatch(r"0?(\d{1,2})月?", text)
        if numeric:
            month = int(numeric.group(1))
            if 1 <= month <= 12:
                return month

        chinese_months = {
            "一月": 1,
            "二月": 2,
            "三月": 3,
            "四月": 4,
            "五月": 5,
            "六月": 6,
            "七月": 7,
            "八月": 8,
            "九月": 9,
            "十月": 10,
            "十一月": 11,
            "十二月": 12,
        }
        if text in chinese_months:
            return chinese_months[text]

        english_months = {
            name.lower(): month
            for month, name in enumerate(calendar.month_name)
            if name
        }
        english_months.update(
            {
                name.lower(): month
                for month, name in enumerate(calendar.month_abbr)
                if name
            }
        )
        normalized = text.rstrip(".")
        if normalized in english_months:
            return english_months[normalized]
        raise ValueError(f"Unsupported TikTok calendar month: {value!r}")

    @staticmethod
    def _schedule_time_parts(publish_date):
        """TikTok exposes minute options in five-minute increments."""
        rounded_minute = (publish_date.minute // 5) * 5
        return publish_date.strftime("%H"), f"{rounded_minute:02d}"

    async def _find_schedule_input(self, kind):
        inputs = self.locator_base.locator(SCHEDULE_INPUTS)
        pattern = re.compile(r"^\d{2}:\d{2}$" if kind == "time" else r"^\d{4}-\d{2}-\d{2}$")
        for index in range(await inputs.count()):
            candidate = inputs.nth(index)
            value = await candidate.input_value()
            if pattern.fullmatch(value or ""):
                return candidate
        raise RuntimeError(f"TikTok {kind} schedule input was not found")

    async def _confirm_schedule_storage(self):
        """Accept TikTok's optional save-video confirmation in either locale."""
        dialogs = self.locator_base.locator(
            '[role="dialog"]:visible, .common-modal-confirm-modal:visible'
        )
        confirmation = re.compile(
            r"(保存.{0,12}视频|网站.{0,12}保存|save.{0,20}video|store.{0,20}video)",
            re.I,
        )
        for index in range(await dialogs.count()):
            dialog = dialogs.nth(index)
            if not confirmation.search(await dialog.inner_text()):
                continue
            button = dialog.get_by_role(
                "button",
                name=re.compile(r"^(确认|允许|保存|Confirm|Allow|Save)$", re.I),
            ).first
            if not await button.count():
                button = dialog.locator(
                    "button:has-text('确认'), button:has-text('允许'), "
                    "button:has-text('Confirm'), button:has-text('Allow')"
                ).first
            await button.wait_for(state="visible", timeout=5_000)
            await button.click()
            await dialog.wait_for(state="hidden", timeout=10_000)
            return True

        # Older TikTok versions render the Allow button without a dialog role.
        allow = self.locator_base.get_by_role(
            "button", name=re.compile(r"^(确认|允许|Confirm|Allow)$", re.I)
        ).first
        if await allow.count() and await allow.is_visible():
            await allow.click()
            return True
        return False

    async def _select_schedule_time(self, page, publish_date):
        time_input = await self._find_schedule_input("time")
        await time_input.click()
        picker = self.locator_base.locator(TIME_PICKER).first
        await picker.wait_for(state="visible", timeout=10_000)

        hour, minute = self._schedule_time_parts(publish_date)
        if publish_date.minute % 5:
            tiktok_logger.warning(
                f"[!] TikTok schedule minute {publish_date.minute:02d} "
                f"was rounded down to {minute}"
            )
        await picker.locator(
            f"span.tiktok-timepicker-left:text-is('{hour}')"
        ).click()
        await picker.locator(
            f"span.tiktok-timepicker-right:text-is('{minute}')"
        ).click()
        await page.wait_for_timeout(200)

    async def _select_schedule_date(self, page, publish_date):
        date_input = await self._find_schedule_input("date")
        await date_input.click()
        picker = self.locator_base.locator(CALENDAR_PICKER).first
        await picker.wait_for(state="visible", timeout=10_000)

        for _ in range(24):
            month_text = await picker.locator("span.month-title").inner_text()
            year_text = await picker.locator("span.year-title").inner_text()
            current_month = self._parse_calendar_month(month_text)
            current_year = int(re.search(r"\d{4}", year_text).group())
            month_delta = (
                (publish_date.year - current_year) * 12
                + publish_date.month
                - current_month
            )
            if month_delta == 0:
                break
            arrows = picker.locator("span.arrow")
            await arrows.nth(1 if month_delta > 0 else 0).click()
            await page.wait_for_timeout(200)
        else:
            raise RuntimeError(
                f"TikTok schedule month is too far away: {publish_date.date()}"
            )

        valid_days = picker.locator("span.day.valid")
        for index in range(await valid_days.count()):
            day = valid_days.nth(index)
            if (await day.inner_text()).strip() == str(publish_date.day):
                await day.click()
                return
        raise RuntimeError(f"TikTok schedule date is unavailable: {publish_date.date()}")

    async def set_schedule_time(self, page, publish_date):
        """Enable scheduled posting and select TikTok's localized date/time controls."""
        async def accept_native_dialog(dialog):
            await dialog.accept()

        def handle_native_dialog(dialog):
            asyncio.create_task(accept_native_dialog(dialog))

        page.once(
            "dialog",
            handle_native_dialog,
        )
        try:
            schedule = self.locator_base.locator(SCHEDULE_RADIO).first
            await schedule.wait_for(state="attached", timeout=15_000)
            if not await schedule.is_checked():
                await schedule.click(force=True)

            await page.wait_for_timeout(300)
            await self._confirm_schedule_storage()
        finally:
            page.remove_listener("dialog", handle_native_dialog)
        await self._select_schedule_time(page, publish_date)
        await self._select_schedule_date(page, publish_date)

    async def click_publish(self, page):
        button = self.locator_base.locator(POST_BUTTON).first
        await button.wait_for(state="visible", timeout=30_000)
        await button.click()

        success_text = page.get_by_text(
            re.compile(r"(发布成功|posted|uploaded successfully|video is being uploaded)", re.I)
        ).first
        try:
            await page.wait_for_url(re.compile(r"/tiktokstudio/content"), timeout=30_000)
        except PlaywrightTimeoutError:
            try:
                await success_text.wait_for(state="visible", timeout=15_000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(
                    "TikTok did not confirm publication by redirect or success message"
                ) from exc
        tiktok_logger.success("  [-] TikTok video published successfully")

    async def click_discard(self, page):
        """Test mode: discard the prepared upload without publishing it."""
        async def accept_native_dialog(dialog):
            await dialog.accept()

        page.once("dialog", accept_native_dialog)
        discard_name = re.compile(r"^(放弃|Discard)$", re.I)
        button = self.locator_base.get_by_role("button", name=discard_name).first
        if not await button.count():
            button = self.locator_base.get_by_text(discard_name, exact=True).first
        if not await button.count() or not await button.is_visible():
            raise RuntimeError('TikTok test mode could not find the "放弃/Discard" button')

        tiktok_logger.info("[TEST] Clicking TikTok discard button")
        await button.click()
        await page.wait_for_timeout(500)

        dialog = page.locator('[role="dialog"]:visible').last
        if await dialog.count():
            confirm = dialog.get_by_role(
                "button",
                name=re.compile(r"^(放弃|Discard|确认|Confirm)$", re.I),
            ).last
            if await confirm.count() and await confirm.is_visible():
                await confirm.click()

        tiktok_logger.success("[TEST] TikTok upload discarded; nothing was published")

    async def get_last_video_id(self, page):
        links = page.locator(
            'div[data-tt="components_PostInfoCell_Container"] a[href*="/video/"], '
            'a[href*="/video/"]'
        )
        if await links.count():
            href = await links.first.get_attribute("href")
            match = re.search(r"/video/(\d+)", href or "")
            return match.group(1) if match else None
        return None

    async def upload(self, playwright: Playwright):
        tiktok_logger.info(
            f"[+] Launching TikTok upload browser (headless={self.headless})"
        )
        browser = await playwright.chromium.launch(**_browser_options(self.headless))
        context_options = {"storage_state": self.account_file}
        if not self.headless:
            context_options["no_viewport"] = True
        context = await browser.new_context(**context_options)
        context = await set_init_script(context)
        page = await context.new_page()
        if not self.headless:
            await page.bring_to_front()
        try:
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60_000)
            tiktok_logger.info(f"[+] Uploading TikTok video: {self.title}")
            await self.choose_base_locator(page)
            await self.upload_video_file()
            await self.add_title_tags(page)
            await self.detect_upload_status()

            if self.thumbnail_path:
                tiktok_logger.info(f"[+] Uploading TikTok cover: {self.thumbnail_path}")
                await self.upload_thumbnails(page)
            if self.is_aigc:
                await self.set_aigc_content()
            await self.add_product_link()
            if self.publish_date and not self.test_mode:
                await self.set_schedule_time(page, self.publish_date)

            if self.test_mode:
                await self.click_discard(page)
            else:
                await self.click_publish(page)
                video_id = await self.get_last_video_id(page)
                if video_id:
                    tiktok_logger.success(f"video_id: {video_id}")
            await context.storage_state(path=self.account_file)
        finally:
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
