import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from myUtils.login import (
    DOUYIN_VERIFICATION_PHONE_SELECTORS,
    extract_douyin_verification_phone,
    parse_douyin_verification_phone,
)


class DouyinVerificationPhoneTests(unittest.TestCase):
    def test_parse_chinese_sms_prompt(self):
        text = "短信已发送至151******50"

        self.assertEqual(parse_douyin_verification_phone(text), "151******50")

    def test_parse_english_sms_prompt_with_country_code(self):
        text = "SMS verification code sent to +86 151******50"

        self.assertEqual(parse_douyin_verification_phone(text), "151******50")

    def test_parse_returns_none_without_masked_phone(self):
        self.assertIsNone(parse_douyin_verification_phone("验证码已发送"))

    def test_extract_phone_from_verification_container(self):
        locator = MagicMock()
        locator.count = AsyncMock(return_value=1)
        locator.inner_text = AsyncMock(return_value="短信已发送至151******50")
        query = MagicMock()
        query.first = locator
        page = MagicMock()
        page.locator.return_value = query

        result = asyncio.run(
            extract_douyin_verification_phone(page, attempts=1, delay=0)
        )

        self.assertEqual(result, "151******50")

    def test_selectors_do_not_depend_on_dynamic_class_suffixes(self):
        selectors = " ".join(DOUYIN_VERIFICATION_PHONE_SELECTORS)

        self.assertNotIn("IDQpSA", selectors)
        self.assertNotIn("SdANMs", selectors)
        self.assertNotIn("ZiPcVi", selectors)


if __name__ == "__main__":
    unittest.main()
