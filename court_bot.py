#!/usr/bin/env python3
"""نقطة تشغيل بوت «محكمة فكّك عقلك».

    BOT_TOKEN=123456:ABC... python3 court_bot.py

أو ضع الإعدادات في ملف .env بجانب هذا الملف (انظر .env.example).
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from court.bot import CourtBot
from court.game import DEFAULT_DURATIONS, Config
from court.store import Store
from court.telegram_api import TelegramAPI, TelegramError, UrllibTransport

ROOT = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    """قراءة بسيطة لملف KEY=VALUE دون مكتبات (لا تستبدل متغيرات موجودة أصلاً)."""
    if not path.is_file():
        return
    for raw in path.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def env_num(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return min(hi, max(lo, float(raw)))
    except ValueError:
        sys.exit(f"قيمة غير صالحة للمتغير {name}: {raw!r}")


def build_config() -> Config:
    scale = env_num("TIME_SCALE", 1.0, 0.05, 10)
    durations = {}
    for phase, default in DEFAULT_DURATIONS.items():
        # يمكن تخصيص كل مرحلة: DUR_PROSECUTION=90 (بالثواني) وإلا تُضرب القيمة الافتراضية في TIME_SCALE
        durations[phase] = env_num(f"DUR_{phase.name}", default * scale, 5, 1800)
    return Config(
        min_players=int(env_num("MIN_PLAYERS", 5, 4, 30)),
        max_players=int(env_num("MAX_PLAYERS", 20, 5, 30)),
        lobby_timeout=env_num("LOBBY_TIMEOUT", 600, 60, 7200),
        vote_grace=env_num("VOTE_GRACE", 8, 1, 60),
        durations=durations,
    )


def main() -> None:
    load_env_file(ROOT / ".env")
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        sys.exit("ضع توكن البوت في المتغير BOT_TOKEN (من @BotFather) أو في ملف .env")
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    bot = CourtBot(TelegramAPI(UrllibTransport(token)), Store(data_dir / "scores.json"), build_config())
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nتم إيقاف البوت.")
    except TelegramError as e:
        if e.code == 401:
            sys.exit("التوكن غير صالح. تأكد من نسخه كاملاً من @BotFather.")
        sys.exit(f"خطأ من تيليجرام: {e}")


if __name__ == "__main__":
    main()
