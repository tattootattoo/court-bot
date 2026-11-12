"""عميل صغير لـ Telegram Bot API بالمكتبة القياسية فقط — لا يحتاج تثبيت أي شيء.

يمكن استبدال النقل (transport) بنقل وهمي في الاختبارات.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

log = logging.getLogger("court.tg")


class TelegramError(Exception):
    def __init__(self, description: str, code: Optional[int] = None, retry_after: float = 0):
        super().__init__(description)
        self.description, self.code, self.retry_after = description, code, retry_after


class Forbidden(TelegramError):      # 403: المستخدم لم يبدأ البوت أو حظره
    pass


class BadRequest(TelegramError):     # 400
    pass


class RetryAfter(TelegramError):     # 429
    pass


class NetworkError(TelegramError):
    pass


def classify(data: Dict[str, Any]) -> TelegramError:
    code, desc = data.get("error_code"), data.get("description", "")
    if code == 429:
        return RetryAfter(desc, code, float((data.get("parameters") or {}).get("retry_after", 1)))
    if code == 403:
        return Forbidden(desc, code)
    if code == 400:
        return BadRequest(desc, code)
    return TelegramError(desc, code)


class UrllibTransport:
    """HTTP عبر urllib داخل خيط مستقل حتى لا تتجمّد حلقة asyncio."""

    def __init__(self, token: str, base: str = "https://api.telegram.org"):
        self._base = f"{base}/bot{token}/"

    def _post(self, method: str, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            self._base + method, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:          # تيليجرام يرد بـ JSON حتى عند الخطأ
            body = e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # لا نمرّر نص الاستثناء: قد يحتوي الرابط وفيه التوكن.
            raise NetworkError(f"network error: {type(e).__name__}") from None
        try:
            return json.loads(body)
        except ValueError:
            raise NetworkError("bad response") from None

    async def request(self, method: str, payload: dict, timeout: float) -> dict:
        return await asyncio.to_thread(self._post, method, payload, timeout)


class TelegramAPI:
    def __init__(self, transport):
        self.transport = transport

    async def call(self, method: str, _timeout: float = 30.0, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        for attempt in range(4):
            data = await self.transport.request(method, params, _timeout)
            if data.get("ok"):
                return data.get("result")
            err = classify(data)
            if isinstance(err, RetryAfter) and attempt < 3:
                log.warning("flood control: sleeping %.1fs", err.retry_after)
                await asyncio.sleep(min(err.retry_after + 0.5, 30))
                continue
            raise err

    # ── اختصارات ──
    async def send_message(self, chat_id: int, text: str, markup: Optional[dict] = None,
                           thread_id: Optional[int] = None):
        return await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                               disable_web_page_preview=True, reply_markup=markup,
                               message_thread_id=thread_id)

    async def edit_text(self, chat_id: int, message_id: int, text: str, markup: Optional[dict] = None):
        return await self.call("editMessageText", chat_id=chat_id, message_id=message_id,
                               text=text, parse_mode="HTML", disable_web_page_preview=True,
                               reply_markup=markup)

    async def edit_markup(self, chat_id: int, message_id: int, markup: Optional[dict] = None):
        return await self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                               reply_markup=markup or {"inline_keyboard": []})

    async def answer_callback(self, query_id: str, text: Optional[str] = None,
                              alert: bool = False, url: Optional[str] = None):
        return await self.call("answerCallbackQuery", callback_query_id=query_id,
                               text=text, show_alert=alert or None, url=url)
