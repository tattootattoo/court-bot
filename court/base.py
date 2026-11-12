"""أساس المتحكّم: حالة المحاكم، الأقفال، وإرسال/تعديل الرسائل بأمان."""
from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .game import Config, Game
from .store import Store
from .telegram_api import BadRequest, Forbidden, TelegramAPI, TelegramError

log = logging.getLogger("court.bot")
# (chat_id, thread_id) للتحديث الجاري معالجته: لنرد داخل نفس «الموضوع» في القروبات ذات المواضيع.
CURRENT_THREAD: ContextVar[Optional[Tuple[int, Optional[int]]]] = ContextVar("court_thread", default=None)


@dataclass
class UI:
    """معرّفات الرسائل المرتبطة بمحكمة واحدة (للتعديل والإزالة لاحقاً)."""
    lobby_msg: Optional[int] = None
    phase_msg: Optional[int] = None
    vote_msgs: Dict[int, int] = field(default_factory=dict)   # لاعب ← رسالة لوحة التصويت
    card_msgs: Dict[int, int] = field(default_factory=dict)   # لاعب ← رسالة بطاقة الدور
    reminded: bool = False
    errors: int = 0


def display_name(user: dict) -> str:
    full = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x).strip()
    return (full or user.get("username") or "لاعب")[:30]


class BotBase:
    def __init__(self, api: TelegramAPI, store: Store, cfg: Config, clock=time.monotonic):
        self.api, self.store, self.cfg, self.clock = api, store, cfg, clock
        self.games: Dict[int, Game] = {}
        self.ui: Dict[int, UI] = {}
        self.username: Optional[str] = None
        self.threads: Dict[int, int] = {}          # قروب ← موضوع (Topic) اللعبة الجارية
        self._locks: Dict[int, asyncio.Lock] = {}

    def lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    def drop(self, chat_id: int) -> None:
        self.games.pop(chat_id, None)
        self.ui.pop(chat_id, None)
        self.threads.pop(chat_id, None)

    def thread_for(self, chat_id: int) -> Optional[int]:
        """موضوع القروب الذي يجب الرد فيه: موضوع التحديث الحالي، وإلا موضوع اللعبة المحفوظ."""
        if chat_id >= 0:
            return None
        cur = CURRENT_THREAD.get()
        if cur and cur[0] == chat_id and cur[1]:
            return cur[1]
        return self.threads.get(chat_id)

    # ── إرسال آمن: لا نترك خطأ شبكة يوقف اللعبة ──
    async def say(self, chat_id: int, text: str, markup: Optional[dict] = None) -> Optional[int]:
        try:
            sent = await self.api.send_message(chat_id, text, markup, self.thread_for(chat_id))
            return sent["message_id"]
        except TelegramError as e:
            log.warning("sendMessage(%s) failed: %s", chat_id, e)
            return None

    async def dm(self, uid: int, text: str, markup: Optional[dict] = None) -> int:
        """رسالة خاصة؛ ترفع TelegramError (مثل Forbidden) ليقرر المستدعي."""
        return (await self.api.send_message(uid, text, markup))["message_id"]

    async def edit(self, chat_id: int, message_id: Optional[int], text: str,
                   markup: Optional[dict] = None) -> None:
        if message_id is None:
            return
        try:
            await self.api.edit_text(chat_id, message_id, text, markup)
        except (BadRequest, Forbidden):          # «not modified» أو الرسالة حُذفت
            pass
        except TelegramError as e:
            log.warning("edit failed: %s", e)

    async def strip_markup(self, chat_id: int, message_id: Optional[int]) -> None:
        if message_id is None:
            return
        try:
            await self.api.edit_markup(chat_id, message_id)
        except TelegramError:
            pass

    async def answer(self, query_id: str, text: Optional[str] = None, alert: bool = False,
                     url: Optional[str] = None) -> None:
        try:
            await self.api.answer_callback(query_id, text, alert, url)
        except BadRequest:
            if url:                                  # بعض العملاء لا يقبلون الرابط
                try:
                    await self.api.answer_callback(query_id, "افتح البوت واضغط Start أولاً 🔗", True)
                except TelegramError:
                    pass
        except TelegramError as e:
            log.debug("answerCallbackQuery failed: %s", e)

    async def is_admin(self, chat_id: int, uid: int) -> bool:
        try:
            m = await self.api.call("getChatMember", chat_id=chat_id, user_id=uid)
            return m.get("status") in ("creator", "administrator")
        except TelegramError:
            return False
