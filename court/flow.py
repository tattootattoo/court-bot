"""دورة حياة المحكمة: البدء، المراحل، التصويت، النتائج، والمؤقّت الدوري."""
from __future__ import annotations

import logging

from . import cards, render
from .game import Game, Phase
from .render import esc, mentions
from .telegram_api import TelegramError

log = logging.getLogger("court.flow")
REMIND_AT = 15.0        # ثوانٍ متبقية لتذكير من لم يصوّت
MAX_TICK_ERRORS = 3


class FlowMixin:
    # ───────────── البدء ─────────────
    async def start_game(self, game: Game) -> bool:
        """يوزّع الأدوار عشوائياً ويرسل البطاقات السرّية. يُستدعى والقفل ممسوك."""
        ui = self.ui[game.chat_id]
        game.start(self.clock())
        failed = []
        for p in game.players.values():
            text, markup = cards.role_card(game, p)
            try:
                ui.card_msgs[p.uid] = await self.dm(p.uid, text, markup)
            except TelegramError as e:
                log.warning("card DM to %s failed: %s", p.uid, e)
                failed.append(p)
        if failed:
            game.cancel()
            await self.strip_markup(game.chat_id, ui.lobby_msg)
            self.drop(game.chat_id)
            await self.say(game.chat_id,
                           f"⚠️ تعذّر إرسال الأدوار إلى: {mentions(failed)}\n"
                           "أُلغيت المحكمة. اطلبوا منهم فتح البوت والضغط على Start ثم أعيدوا /court.")
            return False
        await self.strip_markup(game.chat_id, ui.lobby_msg)
        log.info("بدأت محكمة في %s: %d لاعباً، القضية %s", game.chat_id, len(game.players), game.case.id)
        await self.enter_phase(game)
        return True

    # ───────────── المراحل ─────────────
    async def enter_phase(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        left = game.deadline - self.clock()
        if game.phase == Phase.ROLES:
            text = render.roster_text(game, left)
        else:
            text = render.phase_text(game, game.phase, left)
        if game.phase == Phase.VOTING:
            await self.send_vote_panels(game)
        ui.phase_msg = await self.say(game.chat_id, text, render.skip_kb(game))
        ui.reminded = False

    async def advance(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        await self.strip_markup(game.chat_id, ui.phase_msg)
        game.next_phase(self.clock())
        if game.phase == Phase.ENDED:
            await self.publish_results(game)
        else:
            await self.enter_phase(game)

    # ───────────── التصويت ─────────────
    async def send_vote_panels(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        voters = {p.uid for p in game.voters()}
        for p in game.players.values():
            try:
                if p.uid in voters:
                    text, markup = cards.vote_panel(game, p)
                    ui.vote_msgs[p.uid] = await self.dm(p.uid, text, markup)
                else:                                   # المتهم والمحاميان: لا تصويت لهم
                    await self.dm(p.uid, cards.non_voter_text(p))
            except TelegramError as e:
                log.warning("vote DM to %s failed: %s", p.uid, e)

    async def refresh_vote_panel(self, game: Game, uid: int, message_id: int) -> None:
        text, markup = cards.vote_panel(game, game.players[uid])
        await self.edit(uid, message_id, text, markup)

    async def refresh_progress(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        text = render.vote_progress_text(game, game.deadline - self.clock())
        await self.edit(game.chat_id, ui.phase_msg, text, render.skip_kb(game))

    async def remind_voters(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        ui.reminded = True
        for p in game.voters():
            if p.vote is None:
                try:
                    await self.dm(p.uid, "⏰ باقي أقل من 15 ثانية على إغلاق التصويت! اختر حكمك الآن 👆")
                except TelegramError:
                    pass

    # ───────────── النهاية ─────────────
    async def strip_role_cards(self, game: Game) -> None:
        """إزالة أزرار بطاقات الأدوار القديمة حتى لا تُضغط بعد انتهاء الجلسة."""
        ui = self.ui.get(game.chat_id)
        for uid, mid in (ui.card_msgs.items() if ui else ()):
            await self.strip_markup(uid, mid)

    async def publish_results(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        await self.strip_role_cards(game)
        for uid, mid in ui.vote_msgs.items():
            await self.edit(uid, mid, cards.vote_closed_text(game, game.players[uid]), None)
        for part in render.split_message(render.results_text(game)):
            await self.say(game.chat_id, part)
        try:
            self.store.record_game(game.chat_id, game.case.id,
                                   [(p.uid, p.name, pts) for p, pts in game.ranking()])
        except OSError as e:
            log.error("تعذّر حفظ النقاط: %s", e)
        log.info("انتهت محكمة %s: الحكم %s والحقيقة %s", game.chat_id,
                 game.results.verdict, game.results.truth)
        self.drop(game.chat_id)

    async def cancel_game(self, game: Game, by: str) -> None:
        ui = self.ui.get(game.chat_id)
        game.cancel()
        if ui:
            await self.strip_markup(game.chat_id, ui.lobby_msg)
            await self.strip_markup(game.chat_id, ui.phase_msg)
            await self.strip_role_cards(game)
            for uid, mid in ui.vote_msgs.items():
                await self.strip_markup(uid, mid)
        self.drop(game.chat_id)
        await self.say(game.chat_id, f"🛑 أُلغيت المحكمة بواسطة {esc(by)}. لعبة جديدة: /court")

    async def expire_lobby(self, game: Game) -> None:
        ui = self.ui[game.chat_id]
        await self.strip_markup(game.chat_id, ui.lobby_msg)
        self.drop(game.chat_id)
        await self.say(game.chat_id, "⌛ أُغلقت الردهة لعدم البدء في الوقت المحدد. لعبة جديدة: /court")

    # ───────────── المؤقّت الدوري ─────────────
    async def tick(self) -> None:
        """يُستدعى كل ثانية تقريباً: ينقل المراحل المنتهية ويغلق الردهات الخاملة."""
        for chat_id in list(self.games):
            async with self.lock(chat_id):
                game = self.games.get(chat_id)
                if game is None:
                    continue
                try:
                    await self._tick_game(game)
                except Exception:
                    log.exception("tick failed for chat %s", chat_id)
                    ui = self.ui.get(chat_id)
                    if ui is not None:
                        ui.errors += 1
                        if ui.errors >= MAX_TICK_ERRORS:
                            await self.cancel_game(game, "النظام (خطأ متكرر)")

    async def _tick_game(self, game: Game) -> None:
        now = self.clock()
        if game.phase == Phase.LOBBY:
            if now >= game.deadline:
                await self.expire_lobby(game)
            return
        if game.phase == Phase.VOTING:
            left = game.deadline - now
            ui = self.ui[game.chat_id]
            if 0 < left <= REMIND_AT and not ui.reminded:
                await self.remind_voters(game)
        if now >= game.deadline:
            await self.advance(game)
