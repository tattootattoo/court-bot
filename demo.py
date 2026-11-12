"""عرض تجريبي: يلعب محكمة كاملة بلاعبين وهميين ويطبع ما يظهر في القروب وفي الخاص.

لا يحتاج إنترنت ولا توكن:  python demo.py            (7 لاعبين)
                            python demo.py -n 9 --dm  (9 لاعبين + كل الرسائل الخاصة)
"""
import argparse
import asyncio
import html
import random
import re
import tempfile
import os

from court.bot import CourtBot
from court.fake_telegram import FakeTelegram, Sim
from court.game import Config, DEFAULT_DURATIONS
from court.store import Store
from court.telegram_api import TelegramAPI

CID = -1001
NAMES = ["سالم", "منى", "خالد", "ليلى", "عمر", "هدى", "يوسف", "سلمى", "طارق", "نور",
         "ماجد", "ريم", "أنس", "دانة", "بدر", "لينا", "فهد", "جود", "زياد", "مها"]


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def main(n: int, seed: int, show_dm: bool) -> None:
    fake, now = FakeTelegram(), [0.0]
    cfg = Config(min_players=5, vote_grace=2, rng=random.Random(seed),
                 durations={p: 10 for p in DEFAULT_DURATIONS})
    with tempfile.TemporaryDirectory() as tmp:
        bot = CourtBot(TelegramAPI(fake), Store(os.path.join(tmp, "s.json")), cfg, clock=lambda: now[0])
        bot.username = "CourtBot"
        sim = Sim(bot, fake)
        shown = 0

        def flush(title: str = "") -> None:
            nonlocal shown
            for chat_id, mid in fake.log[shown:]:
                text = plain(fake.msgs[(chat_id, mid)]["text"])
                if chat_id == CID:
                    print(f"\n┌─ القروب {title}\n" + "\n".join("│ " + ln for ln in text.splitlines()))
                elif show_dm or "دورك السرّي:" in text and chat_id <= 2:
                    who = NAMES[chat_id - 1]
                    print(f"\n┌─ [خاص ← {who}]\n" + "\n".join("│ " + ln for ln in text.splitlines()))
            shown = len(fake.log)

        users = list(range(1, n + 1))
        fake.started.update(users)
        await sim.command(CID, 1, "/court", name=NAMES[0])
        lobby = fake.find_msg(CID, "المنضمّون")
        for uid in users[1:]:
            await sim.press(uid, CID, lobby, f"join:{CID}", name=NAMES[uid - 1])
        await sim.command(CID, 1, "/begin", name=NAMES[0])
        game = bot.games[CID]
        flush()
        while game.phase.value != "voting":
            now[0] += 11
            await bot.tick()
            flush()
        rng = random.Random(seed + 1)
        for p in game.voters():
            mid = bot.ui[CID].vote_msgs[p.uid]
            await sim.press(p.uid, p.uid, mid, f"vote:{CID}:{rng.choice('gi')}", name=NAMES[p.uid - 1])
        now[0] += cfg.vote_grace + 1
        await bot.tick()
        flush("— النتائج")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=7, help="عدد اللاعبين (5-20)")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--dm", action="store_true", help="اعرض كل الرسائل الخاصة")
    a = ap.parse_args()
    asyncio.run(main(max(5, min(20, a.n)), a.seed, a.dm))
