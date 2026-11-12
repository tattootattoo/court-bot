"""محاكاة تيليجرام للاختبارات والعرض التجريبي — لا تحتاج إنترنت ولا توكن.

تفرض القيود الحقيقية المهمة: لا يمكن مراسلة من لم يبدأ البوت (403)، وحدّ طول الرسالة 4096،
ورفض التعديل بلا تغيير (400 not modified).
"""
from __future__ import annotations

import itertools
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

BOT_USERNAME = "CourtTestBot"
_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code",
                 "pre", "tg-spoiler", "blockquote"}


class _TagCheck(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: List[str] = []
        self.problem: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            self.problem = f"unsupported tag <{tag}>"
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.problem = f"mismatched </{tag}>"
        else:
            self.stack.pop()


def html_problem(text: str) -> Optional[str]:
    """يحاكي صرامة تيليجرام مع parse_mode=HTML: وسوم مدعومة ومتوازنة وحروف خاصة مهرّبة."""
    if re.search(r"&(?!(amp|lt|gt|quot|#\d+);)", text):
        return "unescaped &"
    if re.search(r"<(?![a-zA-Z/])", text):
        return "unescaped <"
    p = _TagCheck()
    p.feed(text)
    p.close()
    return p.problem or ("unclosed tag" if p.stack else None)


def markup_problem(markup: Optional[dict]) -> Optional[str]:
    """حدود لوحة الأزرار: callback_data ≤ 64 بايت، وزر واحد = إجراء واحد."""
    if not markup:
        return None
    n = 0
    for row in markup.get("inline_keyboard", []):
        for b in row:
            n += 1
            if ("callback_data" in b) == ("url" in b):
                return "button needs exactly one of callback_data/url"
            if len(b.get("callback_data", "").encode()) > 64:
                return "callback_data too long"
            if not b.get("text"):
                return "empty button text"
    return "too many buttons" if n > 100 else None


class FakeTelegram:
    def __init__(self) -> None:
        self._ids = itertools.count(1000)
        self.started: set = set()        # من ضغط Start مع البوت (يمكن مراسلته)
        self.blocked: set = set()        # من حظر البوت
        self.admins: set = set()
        self.log: List[Tuple[int, int]] = []              # (chat_id, message_id) بالترتيب
        self.msgs: Dict[Tuple[int, int], dict] = {}
        self.answers: Dict[str, dict] = {}
        self.calls: List[Tuple[str, dict]] = []

    # ── واجهة النقل التي يستعملها TelegramAPI ──
    async def request(self, method: str, payload: dict, timeout: float) -> dict:
        self.calls.append((method, dict(payload)))
        fn = getattr(self, "m_" + method, None)
        return fn(**payload) if fn else {"ok": True, "result": True}

    @staticmethod
    def _err(code: int, desc: str) -> dict:
        return {"ok": False, "error_code": code, "description": desc}

    @staticmethod
    def _ok(result) -> dict:
        return {"ok": True, "result": result}

    # ── طرق Bot API المحاكاة ──
    def m_getMe(self, **kw):
        return self._ok({"id": 999, "is_bot": True, "username": BOT_USERNAME})

    def _validate(self, text, markup, parse_mode):
        if len(text) > 4096:
            return self._err(400, "Bad Request: message is too long")
        if parse_mode == "HTML":
            bad = html_problem(text)
            if bad:
                return self._err(400, f"Bad Request: can't parse entities: {bad}")
        bad = markup_problem(markup)
        return self._err(400, f"Bad Request: {bad}") if bad else None

    def m_sendMessage(self, chat_id, text, reply_markup=None, parse_mode=None,
                      message_thread_id=None, **kw):
        err = self._validate(text, reply_markup, parse_mode)
        if err:
            return err
        if chat_id > 0:
            if chat_id in self.blocked:
                return self._err(403, "Forbidden: bot was blocked by the user")
            if chat_id not in self.started:
                return self._err(403, "Forbidden: bot can't initiate conversation with a user")
        mid = next(self._ids)
        self.msgs[(chat_id, mid)] = {"text": text, "markup": reply_markup, "thread": message_thread_id}
        self.log.append((chat_id, mid))
        return self._ok({"message_id": mid, "chat": {"id": chat_id}})

    def m_editMessageText(self, chat_id, message_id, text, reply_markup=None, parse_mode=None, **kw):
        rec = self.msgs.get((chat_id, message_id))
        if rec is None:
            return self._err(400, "Bad Request: message to edit not found")
        err = self._validate(text, reply_markup, parse_mode)
        if err:
            return err
        if rec["text"] == text and rec["markup"] == reply_markup:
            return self._err(400, "Bad Request: message is not modified")
        rec["text"], rec["markup"] = text, reply_markup
        return self._ok(True)

    def m_editMessageReplyMarkup(self, chat_id, message_id, reply_markup=None, **kw):
        rec = self.msgs.get((chat_id, message_id))
        if rec is None:
            return self._err(400, "Bad Request: message to edit not found")
        empty = not (reply_markup or {}).get("inline_keyboard")
        rec["markup"] = None if empty else reply_markup
        return self._ok(True)

    def m_answerCallbackQuery(self, callback_query_id, text=None, show_alert=None, url=None, **kw):
        self.answers[callback_query_id] = {"text": text, "alert": bool(show_alert), "url": url}
        return self._ok(True)

    def m_getChatMember(self, chat_id, user_id, **kw):
        return self._ok({"status": "administrator" if user_id in self.admins else "member"})

    # ── أدوات الفحص ──
    def texts(self, chat_id: int) -> List[str]:
        return [self.msgs[k]["text"] for k in self.log if k[0] == chat_id]

    def last_text(self, chat_id: int) -> str:
        t = self.texts(chat_id)
        return t[-1] if t else ""

    def find_msg(self, chat_id: int, contains: str) -> Optional[int]:
        for k in reversed(self.log):
            if k[0] == chat_id and contains in self.msgs[k]["text"]:
                return k[1]
        return None

    def buttons(self, chat_id: int, message_id: int) -> List[dict]:
        markup = self.msgs[(chat_id, message_id)]["markup"] or {}
        return [b for row in markup.get("inline_keyboard", []) for b in row]

    def callback_data(self, chat_id: int, message_id: int) -> List[str]:
        return [b["callback_data"] for b in self.buttons(chat_id, message_id) if "callback_data" in b]


class Sim:
    """يمثّل لاعبين يرسلون أوامر ويضغطون أزراراً."""

    def __init__(self, bot, fake: FakeTelegram) -> None:
        self.bot, self.fake = bot, fake
        self._q = itertools.count(1)

    @staticmethod
    def user(uid: int, name: Optional[str] = None) -> dict:
        return {"id": uid, "first_name": name or f"لاعب{uid}", "is_bot": False}

    @staticmethod
    def _topic(thread: Optional[int]) -> dict:
        return {"message_thread_id": thread, "is_topic_message": True} if thread else {}

    async def command(self, chat_id: int, uid: int, text: str, name: Optional[str] = None,
                      title: str = "قروب الأصدقاء", thread: Optional[int] = None) -> None:
        chat = ({"id": chat_id, "type": "supergroup", "title": title} if chat_id < 0
                else {"id": chat_id, "type": "private"})
        await self.bot.handle_update({"update_id": 0, "message": {
            "message_id": 1, "chat": chat, "from": self.user(uid, name), "text": text,
            **self._topic(thread)}})

    async def press(self, uid: int, chat_id: int, message_id: int, data: str,
                    name: Optional[str] = None, thread: Optional[int] = None) -> Optional[dict]:
        qid = f"q{next(self._q)}"
        await self.bot.handle_update({"update_id": 0, "callback_query": {
            "id": qid, "from": self.user(uid, name), "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat_id}, **self._topic(thread)}}})
        return self.fake.answers.get(qid)
