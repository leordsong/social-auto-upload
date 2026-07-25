"""Call the social-auto-upload HTTP API to publish a TikTok video.

This module intentionally uses a small protocol for ``task`` so callers can
pass an existing state object (for example ``AutomationState``) without making
this project depend on that application's package.

The video and thumbnail paths must be readable by the machine running
``sau_backend.py``.

Typical integration with the state objects from the reference code::

    api_base = get_settings().publish_api
    accounts = reload_accounts(api_base=api_base)
    publish_task(
        task,
        accounts,
        hashtags="#jewelry #tiktokshop",
        api_base=api_base,
    )
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, Sequence

import requests


logger = logging.getLogger(__name__)

PUBLISH_API = os.environ.get(
    "PUBLISH_API", "http://127.0.0.1:5409"
).rstrip("/")
TIKTOK_PLATFORM_TYPE = 6
MIN_SCHEDULE_LEAD = timedelta(hours=3)


class TikTokTask(Protocol):
    account_name: str
    output_path: str
    schedule_time: datetime | None
    video_title: str
    thumbnail_path: str | None
    product_link: str
    product_name: str


@dataclass(frozen=True)
class Account:
    id: int
    type: int
    filePath: str
    name: str
    status: int
    last_login_time: str | None = None

    @classmethod
    def from_array(cls, item):
        if len(item) < 5:
            raise ValueError(f"Invalid account payload: {item!r}")
        return cls(
            id=int(item[0]),
            type=int(item[1]),
            filePath=str(item[2]),
            name=str(item[3]),
            status=int(item[4]),
            last_login_time=str(item[5]) if len(item) > 5 and item[5] else None,
        )


def _api_url(path: str, api_base: str = PUBLISH_API) -> str:
    return f"{api_base.rstrip('/')}/{path.lstrip('/')}"


def get_accounts_map(prefix="", **kwargs):
    return {
        prefix + account.name: account
        for account in get_available_accounts(**kwargs)
    }


def get_available_accounts(
    api="getAccounts",
    *,
    api_base=PUBLISH_API,
    timeout=10,
    session=requests,
) -> list[Account]:
    """Return TikTok accounts from the backend account endpoint."""
    try:
        response = session.get(_api_url(api, api_base), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        accounts = [
            Account.from_array(item)
            for item in payload.get("data", [])
            if int(item[1]) == TIKTOK_PLATFORM_TYPE
        ]
        logger.info("Fetched %d TikTok accounts from API", len(accounts))
        return accounts
    except (requests.RequestException, ValueError, TypeError, KeyError):
        logger.exception("Error fetching TikTok accounts from API")
        return []


def _reload_valid_accounts(
    number_of_accounts,
    *,
    api_base=PUBLISH_API,
    session=requests,
):
    accounts = get_available_accounts(
        "getValidAccounts",
        api_base=api_base,
        timeout=max(number_of_accounts * 10, 10),
        session=session,
    )
    for account in accounts:
        if account.status != 1:
            logger.warning("TikTok account %s is invalid", account.name)
    logger.info("Background TikTok account reload finished")


def reload_accounts(*, api_base=PUBLISH_API, session=requests):
    """Return cached accounts immediately and validate them in the background."""
    accounts = get_available_accounts(api_base=api_base, session=session)
    thread = threading.Thread(
        target=_reload_valid_accounts,
        kwargs={
            "number_of_accounts": len(accounts),
            "api_base": api_base,
            "session": session,
        },
        daemon=True,
    )
    thread.start()
    return accounts


def parse_datetime(time_str):
    """Parse ``YYYY-MM-DD HH:MM:SS`` and convert it to API schedule fields."""
    try:
        target_datetime = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return get_schedule_delta(target_datetime)


def get_schedule_delta(
    target_datetime: datetime,
    *,
    now: datetime | None = None,
    minimum_lead: timedelta = MIN_SCHEDULE_LEAD,
):
    """Return ``(startDays, HH:MM)`` expected by ``/postVideo``."""
    current_datetime = now or datetime.now()
    if target_datetime < current_datetime + minimum_lead:
        logger.warning(
            "TikTok schedule time must be at least %s in the future",
            minimum_lead,
        )
        return None

    days = (target_datetime.date() - current_datetime.date()).days
    return days - 1, target_datetime.strftime("%H:%M")


def normalize_hashtags(hashtags: str | Sequence[str]) -> list[str]:
    if isinstance(hashtags, str):
        values = re.split(r"[\s,，]+", hashtags)
    else:
        values = hashtags
    return list(
        dict.fromkeys(
            value
            for item in values
            if (value := str(item).strip().lstrip("#"))
        )
    )


def build_publish_data(
    task: TikTokTask,
    account: Account,
    hashtags: str | Sequence[str],
    *,
    is_aigc=True,
    test_mode=False,
    now: datetime | None = None,
):
    """Build the JSON payload accepted by the backend TikTok uploader."""
    output_path = str(task.output_path)
    title = str(getattr(task, "video_title", "") or "").strip()
    if not title:
        title = Path(output_path).stem

    schedule_time = getattr(task, "schedule_time", None)
    schedule = (
        get_schedule_delta(schedule_time, now=now)
        if schedule_time and not test_mode
        else None
    )
    description = str(
        getattr(task, "description", "")
        or getattr(task, "video_description", "")
        or ""
    ).strip()

    return {
        "type": TIKTOK_PLATFORM_TYPE,
        "title": title,
        "description": description,
        "desc": description,
        "tags": normalize_hashtags(hashtags),
        "fileList": [output_path],
        "accountList": [account.filePath],
        "enableTimer": 1 if schedule else 0,
        "videosPerDay": 1,
        "dailyTimes": [schedule[1]] if schedule else ["10:00"],
        "startDays": schedule[0] if schedule else 0,
        "category": 0,
        "thumbnail": str(getattr(task, "thumbnail_path", "") or ""),
        "isAigc": bool(getattr(task, "is_aigc", is_aigc)),
        "productLink": str(getattr(task, "product_link", "") or "").strip(),
        "productTitle": str(getattr(task, "product_name", "") or "").strip(),
        "testMode": bool(getattr(task, "test_mode", test_mode)),
    }


def publish_task(
    task: TikTokTask,
    accounts: Sequence[Account],
    hashtags: str | Sequence[str],
    *,
    api_base=PUBLISH_API,
    is_aigc=True,
    test_mode=False,
    timeout=900,
    session=requests,
):
    """Submit one TikTok publishing task to ``POST /postVideo``."""
    account = next(
        (item for item in accounts if item.name == task.account_name),
        None,
    )
    if not account:
        logger.warning(
            "Account %s not found in available TikTok accounts",
            task.account_name,
        )
        return False
    account_type = getattr(account, "type", TIKTOK_PLATFORM_TYPE)
    if str(account_type).lower() not in {"6", "tiktok"}:
        logger.warning("Account %s is not a TikTok account", account.name)
        return False

    publish_data = build_publish_data(
        task,
        account,
        hashtags,
        is_aigc=is_aigc,
        test_mode=test_mode,
    )
    logger.info(
        "Publishing TikTok video %s for account %s",
        task.output_path,
        task.account_name,
    )

    try:
        response = session.post(
            _api_url("postVideo", api_base),
            json=publish_data,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") == 200:
            logger.info(
                "TikTok publish task completed for %s",
                task.output_path,
            )
            return True
        logger.error("TikTok publish failed: %s", payload.get("msg", payload))
    except (requests.RequestException, ValueError):
        logger.exception("Error calling TikTok publish API")
    return False


if __name__ == "__main__":
    raise SystemExit(
        "Import publish_task() from your automation service; "
        "see this module's docstring for the required task fields."
    )
