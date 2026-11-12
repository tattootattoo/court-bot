"""متحكّم البوت: استقبال التحديثات وتوجيه الأوامر والأزرار."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from . import cards, render
from .base import BotBase, CURRENT_THREAD, UI, display_name
from .cases import GUILTY, INNOCENT
from .flow import FlowMixin
from .game import Game, GameError, Phase
from .render import esc
from .telegram_api import Forbidden, NetworkError, TelegramError

log = logging.getLogger("court.bot")
Answer = Optional[Tuple[Optional[str], bool, Optional[str]]]   # (نص، تنبيه منبثق، رابط)

COMMANDS = [
    ("court", "فتح محكمة جديدة ⚖️"),
    ("join", "الانضمام للمحكمة"),
    ("leave", "الانسحاب قبل البدء"),
    ("begin", "بدء الجلسة (للمضيف)"),
    ("status", "حالة المحكمة الحالية"),
    ("top", "لوحة الشرف"),
    ("rules", "شرح اللعبة والأدوار"),
    ("skip", "تخطّي المرحلة (للقاضي)"),
    ("cancel", "إلغاء المحكمة"),
]


class CourtBot(FlowMixin, BotBase):
    # ───────────── التحديثات ─────────────
    async def handle_update(self, upd: dict) -> None:
        src = upd.get("message") or (upd.get("callback_query") or {}).get("message") or {}
        thread = src.get("message_thread_id") if src.get("is_topic_message") else None
        token = CURRENT_THREAD.set(((src.get("chat") or {}).get("id"), thread))
        try:
            if upd.get("message"):
                await self.on_message(upd["message"])
            elif upd.get("callback_query"):
                await self.on_callback(upd["callback_query"])
        except Exception:
            log.exception("فشلت معالجة التحديث")
        finally:
            CURRENT_THREAD.reset(token)

    async def on_message(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        user = msg.get("from") or {}
        if not text.startswith("/") or not user or user.get("is_bot"):
            return
        head, _, arg = text.partition(" ")
        cmd, _, target = head[1:].partition("@")
        if target and self.username and target.lower() != self.username.lower():
            return                                      # أمر موجّه لبوت آخر
        cmd, chat = cmd.lower(), msg["chat"]
        private = chat.get("type") == "private"
        if cmd == "start" and private:
            return await self.cmd_start_private(chat, user, arg.strip())
        if cmd in ("start", "help"):
            return await self.say(chat["id"], cards.private_help(self.username))
        if cmd == "rules":
            return await self.say(chat["id"], cards.rules_text())
        if private:
            return await self.say(chat["id"], "هذا الأمر يعمل داخل القروبات فقط 👥 — أضفني إلى قروبك واكتب /court")
        handler = {
            "court": self.cmd_court, "join": self.cmd_join, "leave": self.cmd_leave,
            "begin": self.cmd_begin, "cancel": self.cmd_cancel, "status": self.cmd_status,
            "top": self.cmd_top, "skip": self.cmd_skip,
        }.get(cmd)
        if handler:
            await handler(chat, user)

    # ───────────── مساعدات ─────────────
    def _lobby_min(self) -> int:
        return max(1, int(self.cfg.lobby_timeout // 60))

    async def refresh_lobby(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        await self.edit(game.chat_id, ui.lobby_msg, render.lobby_text(game, self._lobby_min()),
                        render.lobby_kb(game, self.username))

    async def can_manage(self, game: Game, uid: int) -> bool:
        return uid == game.host_uid or await self.is_admin(game.chat_id, uid)

    async def try_join(self, game: Game, user: dict) -> Tuple[str, Optional[str]]:
        """انضمام لاعب بعد التأكد أن البوت يستطيع مراسلته (وإلا لن تصله بطاقة دوره)."""
        uid = user["id"]
        try:
            game.join(uid, display_name(user))
        except GameError as e:
            return "error", str(e)
        try:
            await self.dm(uid, cards.welcome_dm(game))
        except Forbidden:
            game.leave(uid)
            return "need_start", None
        except TelegramError:
            game.leave(uid)
            return "error", "تعذّر إرسال رسالة خاصة إليك، حاول مرة أخرى."
        game.deadline = self.clock() + self.cfg.lobby_timeout      # نشاط جديد يمدّد المهلة
        await self.refresh_lobby(game)
        return "ok", None

    # ───────────── الأوامر ─────────────
    async def cmd_start_private(self, chat: dict, user: dict, arg: str) -> None:
        uid = chat["id"]
        if not arg.startswith("join_"):
            return await self.say(uid, cards.private_help(self.username))
        try:
            cid = int(arg[5:])
        except ValueError:
            return await self.say(uid, "رابط غير صالح.")
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None or game.phase != Phase.LOBBY:
                return await self.say(uid, "لا توجد ردهة مفتوحة الآن في ذلك القروب 🤷")
            status, why = await self.try_join(game, user)
        if status == "error":
            await self.say(uid, f"⚠️ {why}")

    async def cmd_court(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            if cid in self.games:
                return await self.say(cid, "⚠️ توجد محكمة قائمة بالفعل في هذا القروب. استخدموا /status أو /cancel.")
            game = Game(cid, chat.get("title") or "المحكمة", user["id"], self.cfg, self.clock(),
                        recent_case_ids=self.store.recent_cases(cid), host_name=display_name(user))
            ui = UI()
            ui.lobby_msg = await self.say(cid, render.lobby_text(game, self._lobby_min()),
                                          render.lobby_kb(game, self.username))
            if ui.lobby_msg is None:
                return
            self.games[cid], self.ui[cid] = game, ui
            thread = self.thread_for(cid)
            if thread:
                self.threads[cid] = thread               # كل رسائل الجلسة تبقى في هذا الموضوع
            await self.try_join(game, user)             # المضيف ينضم تلقائياً إن كان البوت يراسله

    async def cmd_join(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None or game.phase != Phase.LOBBY:
                return await self.say(cid, "لا توجد ردهة مفتوحة. ابدأوا بـ /court ⚖️")
            status, why = await self.try_join(game, user)
        name = esc(display_name(user))
        if status == "need_start":
            await self.say(cid, f"{name}، فعّل البوت أولاً ثم اضغط انضم 👇", render.need_start_kb(self.username, cid))
        elif status == "error":
            await self.say(cid, f"{name}: {why}")

    async def cmd_leave(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None:
                return
            try:
                game.leave(user["id"])
            except GameError as e:
                return await self.say(cid, f"{esc(display_name(user))}: {e}")
            await self.refresh_lobby(game)

    async def cmd_begin(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None or game.phase != Phase.LOBBY:
                return await self.say(cid, "لا توجد ردهة مفتوحة. ابدأوا بـ /court ⚖️")
            if not await self.can_manage(game, user["id"]):
                return await self.say(cid, "⛔ بدء الجلسة للمضيف أو لأدمن القروب فقط.")
            err = game.check_start()
            if err:
                return await self.say(cid, f"⚠️ {err}")
            await self.start_game(game)

    async def cmd_cancel(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None:
                return await self.say(cid, "لا توجد محكمة قائمة لإلغائها.")
            if not await self._may_cancel(game, user["id"]):
                return await self.say(cid, "⛔ الإلغاء للمضيف أو القاضي أو أدمن القروب فقط.")
            await self.cancel_game(game, display_name(user))

    async def _may_cancel(self, game: Game, uid: int) -> bool:
        judge = game.first_with("judge")
        return (judge is not None and judge.uid == uid) or await self.can_manage(game, uid)

    async def cmd_status(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        game = self.games.get(cid)
        if game is None:
            return await self.say(cid, "لا توجد محكمة قائمة الآن. ابدأوا بـ /court ⚖️")
        await self.say(cid, render.status_text(game, game.deadline - self.clock()))

    async def cmd_top(self, chat: dict, user: dict) -> None:
        await self.say(chat["id"], render.top_text(self.store.top(chat["id"])))

    async def cmd_skip(self, chat: dict, user: dict) -> None:
        cid = chat["id"]
        async with self.lock(cid):
            game = self.games.get(cid)
            if game is None or game.phase == Phase.LOBBY:
                return await self.say(cid, "لا توجد جلسة جارية لتخطّي مرحلتها.")
            if not await self._may_skip(game, user["id"]):
                return await self.say(cid, "⛔ التخطّي للقاضي أو المضيف أو أدمن القروب فقط.")
            await self.advance(game)

    async def _may_skip(self, game: Game, uid: int) -> bool:
        return await self._may_cancel(game, uid)

    # ───────────── الأزرار ─────────────
    async def on_callback(self, cq: dict) -> None:
        qid, user, data = cq["id"], cq["from"], cq.get("data") or ""
        try:
            kind, cid_s, *args = data.split(":")
            cid = int(cid_s)
        except ValueError:
            return await self.answer(qid)
        msg = cq.get("message") or {}
        async with self.lock(cid):
            game = self.games.get(cid)
            try:
                ans = await self.route_callback(qid, kind, game, user, args, msg)
            except GameError as e:
                ans = (str(e), True, None)
            except (ValueError, IndexError):
                ans = ("طلب غير صالح", True, None)
        if ans is not None:
            await self.answer(qid, *ans)

    async def route_callback(self, qid: str, kind: str, game: Optional[Game], user: dict,
                             args: list, msg: dict) -> Answer:
        uid = user["id"]
        if game is None:
            return ("انتهت هذه المحكمة ⌛", True, None)

        if kind == "join":
            status, why = await self.try_join(game, user)
            if status == "ok":
                return ("✅ انضممتَ للمحكمة! راجع رسائل البوت الخاصة", False, None)
            if status == "need_start":
                link = render.deep_link(self.username, game.chat_id)
                return (None, False, link) if link else ("افتح البوت بالخاص واضغط Start ثم عُد", True, None)
            return (why, True, None)

        if kind == "leave":
            game.leave(uid)
            await self.refresh_lobby(game)
            return ("🚪 انسحبتَ من المحكمة", False, None)

        if kind == "begin":
            if game.phase != Phase.LOBBY:
                return ("بدأت المحكمة بالفعل", True, None)
            if not await self.can_manage(game, uid):
                return ("⛔ البدء للمضيف أو أدمن القروب فقط", True, None)
            err = game.check_start()
            if err:
                return (err, True, None)
            await self.answer(qid, "▶️ جارٍ توزيع الأدوار عشوائياً...")
            await self.start_game(game)
            return None

        if kind == "cancel":
            if not await self._may_cancel(game, uid):
                return ("⛔ الإلغاء للمضيف أو القاضي أو الأدمن فقط", True, None)
            await self.answer(qid, "🛑 تم الإلغاء")
            await self.cancel_game(game, display_name(user))
            return None

        if kind == "skip":
            if int(args[0]) != game.serial:
                return ("هذه المرحلة انتهت بالفعل", False, None)
            if not await self._may_skip(game, uid):
                return ("⛔ للقاضي أو المضيف أو الأدمن فقط", True, None)
            await self.answer(qid, "⏭ المرحلة التالية")
            await self.advance(game)
            return None

        # ── الإجراءات السرّية (تُضغط من الخاص) ──
        mid = msg.get("message_id")
        if kind == "ev":
            side, text = game.reveal_evidence(uid, int(args[0]))
            player = game.players[uid]
            await self.say(game.chat_id, render.evidence_text(side, player, text))
            await self._set_markup(uid, mid, cards.role_markup(game, player))
            return ("🧾 عُرض الدليل في القروب!", False, None)

        if kind == "inv":
            target = int(args[0])
            is_false = game.investigate(uid, target)
            await self._set_markup(uid, mid, None)
            try:
                await self.dm(uid, cards.investigation_text(game.players[target], is_false))
            except TelegramError:
                pass
            return ("🤥 كاذب!" if is_false else "✅ صادق", True, None)

        if kind == "vote":
            if args[0] not in ("g", "i"):
                raise GameError("اختيار غير صالح.")
            game.cast_vote(uid, GUILTY if args[0] == "g" else INNOCENT)
            await self.refresh_vote_panel(game, uid, mid)
            if game.all_voted():
                game.deadline = min(game.deadline, self.clock() + game.cfg.vote_grace)
            await self.refresh_progress(game)
            return ("🗳️ تم تسجيل صوتك", False, None)

        if kind == "fw":
            game.guess_false_witness(uid, int(args[0]))
            await self.refresh_vote_panel(game, uid, mid)
            return ("🤥 سُجّل تخمينك", False, None)
        return None

    async def _set_markup(self, chat_id: int, message_id: Optional[int], markup: Optional[dict]) -> None:
        if message_id is None:
            return
        try:
            await self.api.edit_markup(chat_id, message_id, markup)
        except TelegramError:
            pass

    # ───────────── التشغيل ─────────────
    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                await self.tick()
            except Exception:
                log.exception("ticker error")

    async def _startup(self) -> None:
        """يتحقق من التوكن (يفشل فوراً إن كان خاطئاً) ويصبر على انقطاع الشبكة عند الإقلاع."""
        while True:
            try:
                me = await self.api.call("getMe")
                break
            except NetworkError as e:
                log.warning("لا اتصال بتيليجرام الآن (%s) — إعادة المحاولة بعد 5 ثوانٍ", e)
                await asyncio.sleep(5)
        self.username = me.get("username")
        try:
            # getUpdates لا يعمل مع webhook نشط؛ ونُسقط التحديثات القديمة لأن حالة اللعب في الذاكرة فقط.
            await self.api.call("deleteWebhook", drop_pending_updates=True)
            await self.api.call("setMyCommands",
                                commands=[{"command": c, "description": d} for c, d in COMMANDS])
        except TelegramError as e:
            log.warning("تعذّر ضبط قائمة الأوامر: %s", e)

    async def run(self) -> None:
        await self._startup()
        log.info("البوت يعمل: @%s", self.username)
        ticker = asyncio.create_task(self._ticker())
        pending: set = set()
        offset, backoff = None, 1.0
        try:
            while True:
                try:
                    updates = await self.api.call(
                        "getUpdates", _timeout=45, offset=offset, timeout=30,
                        allowed_updates=["message", "callback_query"])
                    backoff = 1.0
                except TelegramError as e:
                    log.warning("getUpdates فشل: %s — إعادة المحاولة بعد %.0f ثانية", e, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
                for upd in updates or []:
                    offset = upd["update_id"] + 1
                    task = asyncio.create_task(self.handle_update(upd))
                    pending.add(task)
                    task.add_done_callback(pending.discard)
        finally:
            ticker.cancel()
