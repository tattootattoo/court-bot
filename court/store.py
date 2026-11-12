"""تخزين لوحة النقاط وآخر القضايا لكل قروب في ملف JSON (كتابة ذرّية)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

log = logging.getLogger("court.store")
RECENT_KEEP = 6


class Store:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.data: Dict[str, dict] = {"chats": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.data = json.loads(self.path.read_text("utf-8"))
            self.data.setdefault("chats", {})
        except (ValueError, OSError):
            backup = self.path.with_suffix(".corrupt")
            log.error("ملف النقاط تالف؛ سيُحفظ نسخة في %s ويبدأ ملف جديد", backup)
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            self.data = {"chats": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.path)

    def _chat(self, chat_id: int) -> dict:
        return self.data["chats"].setdefault(str(chat_id), {"players": {}, "recent": [], "games": 0})

    def recent_cases(self, chat_id: int) -> List[str]:
        return list(self._chat(chat_id)["recent"])

    def record_game(self, chat_id: int, case_id: str,
                    rows: Iterable[Tuple[int, str, int]]) -> None:
        """rows: (uid, name, points). الفائز = صاحب أعلى نقاط (والتعادل يفوز الجميع)."""
        rows = list(rows)
        chat = self._chat(chat_id)
        chat["games"] += 1
        chat["recent"] = (chat["recent"] + [case_id])[-RECENT_KEEP:]
        best = max((pts for _, _, pts in rows), default=0)
        for uid, name, pts in rows:
            rec = chat["players"].setdefault(str(uid), {"name": name, "points": 0, "games": 0, "wins": 0})
            rec["name"] = name
            rec["points"] += pts
            rec["games"] += 1
            rec["wins"] += 1 if pts == best and best > 0 else 0
        self._save()

    def top(self, chat_id: int, limit: int = 10) -> List[dict]:
        players = self._chat(chat_id)["players"]
        rows = [{"uid": int(u), **rec} for u, rec in players.items()]
        rows.sort(key=lambda r: (-r["points"], -r["wins"], r["name"]))
        return rows[:limit]
