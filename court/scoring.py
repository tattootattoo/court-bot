"""احتساب الحكم والنقاط عند نهاية المحكمة. غيّر أرقام POINTS لتعديل التوازن."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import roles as R
from .cases import GUILTY, INNOCENT
from .lines import TIE_NOTE_JUDGE, TIE_NOTE_PRESUMPTION

POINTS = {
    "participation": 1,        # كل من لعب
    "judge_correct": 3,        # حكم يطابق الحقيقة
    "prosecutor_win": 4,       # صدر حكم بالإدانة
    "defense_win": 4,          # صدر حكم بالبراءة
    "defendant_acquitted": 4,  # تبرئة المتهم
    "defendant_escaped": 2,    # مكافأة المذنب الذي نجا
    "defendant_wronged": 1,    # بريء أُدين ظلماً (عزاء)
    "witness_true_ok": 3,      # الشاهد الصادق والحكم صحيح
    "witness_false_ok": 4,     # شاهد الزور وخدع المحكمة
    "juror_correct": 2,        # محلّف صوّت بما يطابق الحقيقة
    "bribed_bonus": 3,         # المرتشي والحكم وافق الرشوة
    "guess_correct": 1,        # كشف شاهد الزور (أو أنه لا يوجد)
}


@dataclass
class Award:
    uid: int
    points: int = 0
    reasons: List[str] = field(default_factory=list)

    def give(self, pts: int, why: str) -> None:
        self.points += pts
        self.reasons.append(why)


@dataclass
class Results:
    verdict: str
    truth: str
    guilty: List[int]
    innocent: List[int]
    abstained: List[int]
    decided_by: str                      # majority | judge | presumption
    tie_note: Optional[str]
    awards: Dict[int, Award]
    false_witness: Optional[int]
    honest_witness: Optional[int]
    correct_guessers: List[int]
    bribe_dir: Optional[str]

    @property
    def correct(self) -> bool:
        return self.verdict == self.truth


def decide(votes: Dict[int, str], judge_uid: Optional[int]) -> Tuple[str, str, Optional[str]]:
    """الأغلبية تحسم؛ وعند التعادل يحسم صوت القاضي؛ ولو لم يصوّت فالأصل البراءة."""
    g = sum(1 for v in votes.values() if v == GUILTY)
    i = sum(1 for v in votes.values() if v == INNOCENT)
    if g > i:
        return GUILTY, "majority", None
    if i > g:
        return INNOCENT, "majority", None
    jv = votes.get(judge_uid) if judge_uid is not None else None
    if jv in (GUILTY, INNOCENT):
        return jv, "judge", TIE_NOTE_JUDGE
    return INNOCENT, "presumption", TIE_NOTE_PRESUMPTION


def score(game) -> Results:
    ps = game.players
    voters = game.voters()
    votes = {p.uid: p.vote for p in voters if p.vote in (GUILTY, INNOCENT)}
    judge = game.first_with(R.JUDGE)
    verdict, decided_by, note = decide(votes, judge.uid if judge else None)
    truth = game.truth
    correct = verdict == truth
    awards = {uid: Award(uid) for uid in ps}

    for p in ps.values():
        awards[p.uid].give(POINTS["participation"], "مشاركة")

    for p in ps.values():
        a, role = awards[p.uid], p.role
        if role == R.JUDGE and correct:
            a.give(POINTS["judge_correct"], "حكم صائب")
        elif role == R.PROSECUTOR and verdict == GUILTY:
            a.give(POINTS["prosecutor_win"], "كسب الإدانة")
        elif role == R.DEFENSE and verdict == INNOCENT:
            a.give(POINTS["defense_win"], "كسب البراءة")
        elif role == R.DEFENDANT:
            if verdict == INNOCENT:
                a.give(POINTS["defendant_acquitted"], "تبرئة")
                if truth == GUILTY:
                    a.give(POINTS["defendant_escaped"], "نجا بفعلته 😏")
            elif truth == INNOCENT:
                a.give(POINTS["defendant_wronged"], "أُدين ظلماً")
        elif role == R.WITNESS_TRUE and correct:
            a.give(POINTS["witness_true_ok"], "شهادة الحق أثمرت")
        elif role == R.WITNESS_FALSE and not correct:
            a.give(POINTS["witness_false_ok"], "نجح التزوير 🤥")
        if role in R.JUROR_ROLES and votes.get(p.uid) == truth:
            a.give(POINTS["juror_correct"], "صوّت بما يطابق الحقيقة")
        if role == R.BRIBED and verdict == game.bribe_dir:
            a.give(POINTS["bribed_bonus"], "الرشوة أتت أُكلها 💰")

    false_w = game.first_with(R.WITNESS_FALSE)
    honest_w = game.first_with(R.WITNESS_TRUE)
    correct_guessers: List[int] = []
    for p in voters:
        if p.role in R.WITNESS_ROLES or p.guess is None:
            continue
        expected = false_w.uid if false_w else 0
        if p.guess == expected:
            correct_guessers.append(p.uid)
            awards[p.uid].give(POINTS["guess_correct"],
                               "كشف شاهد الزور" if false_w else "أدرك أن لا زور هنا")

    return Results(
        verdict=verdict, truth=truth,
        guilty=[u for u, v in votes.items() if v == GUILTY],
        innocent=[u for u, v in votes.items() if v == INNOCENT],
        abstained=[p.uid for p in voters if p.uid not in votes],
        decided_by=decided_by, tie_note=note, awards=awards,
        false_witness=false_w.uid if false_w else None,
        honest_witness=honest_w.uid if honest_w else None,
        correct_guessers=correct_guessers, bribe_dir=game.bribe_dir,
    )
