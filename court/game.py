"""محرك اللعبة: حالة وقواعد فقط، بلا أي اتصال بتيليجرام ولا انتظار زمني.

المتحكّم (bot.py) يستدعي هذه الدوال ويمرّر الوقت الحالي، فيسهل اختبار كل شيء.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from . import roles as R
from .cases import GUILTY, INNOCENT, Case, pick_case
from .lines import JUDGE_QUESTIONS
from .scoring import Results, score


class Phase(str, Enum):
    LOBBY = "lobby"
    ROLES = "roles"
    PROSECUTION = "prosecution"
    DEFENSE = "defense"
    WITNESSES = "witnesses"
    LAST_WORD = "last_word"
    DELIBERATION = "deliberation"
    VOTING = "voting"
    ENDED = "ended"
    CANCELLED = "cancelled"


TRIAL_ORDER = (Phase.ROLES, Phase.PROSECUTION, Phase.DEFENSE, Phase.WITNESSES,
               Phase.LAST_WORD, Phase.DELIBERATION, Phase.VOTING)
# المراحل التي يُسمح فيها بعرض الأدلة وفحص المحقق.
ACTION_PHASES = (Phase.PROSECUTION, Phase.DEFENSE, Phase.WITNESSES,
                 Phase.LAST_WORD, Phase.DELIBERATION)

DEFAULT_DURATIONS = {
    Phase.ROLES: 30, Phase.PROSECUTION: 75, Phase.DEFENSE: 75,
    Phase.WITNESSES: 120, Phase.LAST_WORD: 40, Phase.DELIBERATION: 90,
    Phase.VOTING: 60,
}


class GameError(Exception):
    """خطأ موجّه للاعب: الرسالة بالعربية وتُعرض كما هي."""


@dataclass
class Config:
    min_players: int = 5
    max_players: int = 20
    lobby_timeout: float = 600.0
    vote_grace: float = 8.0
    max_reveals: int = 2
    durations: Dict[Phase, float] = field(default_factory=lambda: dict(DEFAULT_DURATIONS))
    rng: random.Random = field(default_factory=random.SystemRandom)

    def duration(self, phase: Phase) -> float:
        return self.durations.get(phase, 60.0)


@dataclass
class Player:
    uid: int
    name: str
    role: Optional[str] = None
    reveals: List[int] = field(default_factory=list)   # أدلة عرضها المحامي
    investigated: Optional[int] = None                  # هدف فحص المحقق
    vote: Optional[str] = None
    guess: Optional[int] = None                         # من يظنه شاهد زور (0 = لا أحد)


class Game:
    def __init__(self, chat_id: int, title: str, host_uid: int, cfg: Config,
                 now: float, recent_case_ids=(), host_name: str = ""):
        self.chat_id = chat_id
        self.title = title
        self.host_uid = host_uid
        self.host_name = host_name
        self.cfg = cfg
        self.players: Dict[int, Player] = {}
        self.phase = Phase.LOBBY
        self.serial = 0                      # يزداد مع كل مرحلة (لإبطال أزرار قديمة)
        self.deadline = now + cfg.lobby_timeout
        self.case: Optional[Case] = None
        self.truth: Optional[str] = None
        self.bribe_dir: Optional[str] = None
        self.judge_questions: List[str] = []
        self.public_evidence: List[Tuple[str, int, str]] = []   # (side, idx, text)
        self.results: Optional[Results] = None
        self.recent = list(recent_case_ids)
        self.all_voted_at: Optional[float] = None

    # ───────────── الاستعلامات ─────────────
    def first_with(self, role: str) -> Optional[Player]:
        return next((p for p in self.players.values() if p.role == role), None)

    def with_roles(self, *roles: str) -> List[Player]:
        return [p for p in self.players.values() if p.role in roles]

    def voters(self) -> List[Player]:
        return self.with_roles(*R.VOTER_ROLES)

    def witnesses(self) -> List[Player]:
        return self.with_roles(*R.WITNESS_ROLES)

    def public_roster(self) -> Dict[str, List[Player]]:
        out: Dict[str, List[Player]] = {g: [] for g in R.PUBLIC_ORDER}
        for p in self.players.values():
            out[R.public_group(p.role)].append(p)
        return out

    def evidence_for(self, role: str) -> Tuple[str, ...]:
        if role == R.PROSECUTOR:
            return self.case.clues_prosecution
        if role == R.DEFENSE:
            return self.case.clues_defense
        return ()

    def knows_truth(self, role: str) -> bool:
        return role in (R.DEFENDANT, R.WITNESS_TRUE, R.WITNESS_FALSE)

    def secret_story(self, p: Player) -> Optional[str]:
        """نص الرواية السرّية الخاص بدور اللاعب (إن وُجد)."""
        if p.role == R.DEFENDANT:
            return self.case.defendant_story(self.truth)
        if p.role == R.WITNESS_TRUE:
            return self.case.witness_line(self.truth)
        if p.role == R.WITNESS_FALSE:
            return self.case.false_line(self.truth)
        return None

    def ranking(self) -> List[Tuple[Player, int]]:
        order = {uid: i for i, uid in enumerate(self.players)}
        rows = [(p, self.results.awards[p.uid].points) for p in self.players.values()]
        return sorted(rows, key=lambda r: (-r[1], order[r[0].uid]))

    # ───────────── الردهة ─────────────
    def join(self, uid: int, name: str) -> Player:
        if self.phase != Phase.LOBBY:
            raise GameError("بدأت المحكمة بالفعل، انتظر الجلسة القادمة.")
        if uid in self.players:
            raise GameError("أنت منضم بالفعل ✅")
        if len(self.players) >= self.cfg.max_players:
            raise GameError(f"المحكمة ممتلئة ({self.cfg.max_players} لاعباً).")
        taken = {p.name for p in self.players.values()}
        base, n = name.strip() or "لاعب", 2
        unique = base
        while unique in taken:
            unique, n = f"{base} ({n})", n + 1
        self.players[uid] = Player(uid, unique)
        return self.players[uid]

    def leave(self, uid: int) -> None:
        if self.phase != Phase.LOBBY:
            raise GameError("لا يمكن الانسحاب بعد بدء المحكمة.")
        if uid not in self.players:
            raise GameError("لست ضمن اللاعبين.")
        del self.players[uid]

    def check_start(self) -> Optional[str]:
        if self.phase != Phase.LOBBY:
            return "المحكمة بدأت بالفعل."
        need = max(self.cfg.min_players, R.MIN_PLAYERS_ABS)
        if len(self.players) < need:
            return f"نحتاج {need} لاعبين على الأقل (المنضمون الآن: {len(self.players)})."
        return None

    def start(self, now: float) -> None:
        err = self.check_start()
        if err:
            raise GameError(err)
        rng = self.cfg.rng
        for uid, role in R.assign_roles(list(self.players), rng).items():
            self.players[uid].role = role
        self.truth = rng.choice([GUILTY, INNOCENT])
        self.bribe_dir = rng.choice([GUILTY, INNOCENT])
        self.case = pick_case(rng, self.recent)
        self.judge_questions = rng.sample(JUDGE_QUESTIONS, 3)
        self._set_phase(Phase.ROLES, now)

    # ───────────── المراحل ─────────────
    def _set_phase(self, phase: Phase, now: float) -> None:
        self.phase = phase
        self.serial += 1
        self.all_voted_at = None
        self.deadline = now + self.cfg.duration(phase)

    def next_phase(self, now: float) -> Phase:
        if self.phase not in TRIAL_ORDER:
            raise GameError("لا توجد مرحلة تالية.")
        i = TRIAL_ORDER.index(self.phase)
        if i + 1 < len(TRIAL_ORDER):
            self._set_phase(TRIAL_ORDER[i + 1], now)
        else:
            self.finish()
        return self.phase

    def finish(self) -> Results:
        self.results = score(self)
        self.phase = Phase.ENDED
        self.serial += 1
        return self.results

    def cancel(self) -> None:
        self.phase = Phase.CANCELLED
        self.serial += 1

    # ───────────── إجراءات اللاعبين السرّية ─────────────
    def _player(self, uid: int) -> Player:
        p = self.players.get(uid)
        if p is None:
            raise GameError("أنت لست ضمن هذه المحكمة.")
        return p

    def reveal_evidence(self, uid: int, idx: int) -> Tuple[str, str]:
        """المحامي يعرض دليلاً علناً. يرجع (الجهة، نص الدليل)."""
        p = self._player(uid)
        if p.role not in (R.PROSECUTOR, R.DEFENSE):
            raise GameError("عرض الأدلة للمدّعي العام ومحامي الدفاع فقط.")
        if self.phase not in ACTION_PHASES:
            raise GameError("لا يمكن عرض الأدلة في هذه المرحلة.")
        clues = self.evidence_for(p.role)
        if not 0 <= idx < len(clues):
            raise GameError("هذا الدليل غير موجود.")
        if idx in p.reveals:
            raise GameError("عرضتَ هذا الدليل من قبل.")
        if len(p.reveals) >= self.cfg.max_reveals:
            raise GameError(f"استهلكتَ أدلتك المسموحة ({self.cfg.max_reveals}).")
        p.reveals.append(idx)
        side = "prosecution" if p.role == R.PROSECUTOR else "defense"
        self.public_evidence.append((side, idx, clues[idx]))
        return side, clues[idx]

    def investigate(self, uid: int, target_uid: int) -> bool:
        """المحقق يفحص شاهداً مرة واحدة. يرجع True إن كان شاهد زور."""
        p = self._player(uid)
        if p.role != R.DETECTIVE:
            raise GameError("الفحص للمحلّف المحقق فقط.")
        if self.phase not in ACTION_PHASES:
            raise GameError("لا يمكن الفحص في هذه المرحلة.")
        if p.investigated is not None:
            raise GameError("استعملتَ فحصك الوحيد من قبل.")
        target = self.players.get(target_uid)
        if target is None or target.role not in R.WITNESS_ROLES:
            raise GameError("يمكنك فحص الشهود فقط.")
        p.investigated = target_uid
        return target.role == R.WITNESS_FALSE

    def cast_vote(self, uid: int, verdict: str) -> None:
        p = self._player(uid)
        if self.phase != Phase.VOTING:
            raise GameError("التصويت غير مفتوح الآن.")
        if p.role not in R.VOTER_ROLES:
            raise GameError("لا يحق لك التصويت في هذا الدور.")
        if verdict not in (GUILTY, INNOCENT):
            raise GameError("اختيار غير صالح.")
        p.vote = verdict

    def guess_false_witness(self, uid: int, target_uid: int) -> None:
        p = self._player(uid)
        if self.phase != Phase.VOTING:
            raise GameError("التصويت غير مفتوح الآن.")
        if p.role not in R.VOTER_ROLES or p.role in R.WITNESS_ROLES:
            raise GameError("التخمين لهيئة المحلّفين والقاضي فقط.")
        if target_uid != 0 and (target_uid not in self.players
                                or self.players[target_uid].role not in R.WITNESS_ROLES):
            raise GameError("اختر أحد الشهود أو «لا أحد».")
        p.guess = target_uid

    def votes_cast(self) -> Tuple[int, int]:
        voters = self.voters()
        return sum(1 for v in voters if v.vote), len(voters)

    def all_voted(self) -> bool:
        cast, total = self.votes_cast()
        return total > 0 and cast == total
