"""نموذج القضية + تحميل القضايا من ملفات البيانات."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from ._cases_a import CASES_A
from ._cases_b import CASES_B

GUILTY = "guilty"
INNOCENT = "innocent"


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    charge: str
    scene: str
    witness_guilty: str
    witness_innocent: str
    defendant_guilty: str
    defendant_innocent: str
    clues_prosecution: Tuple[str, ...]
    clues_defense: Tuple[str, ...]

    def witness_line(self, truth: str) -> str:
        """ما يقوله الشاهد الذي يرى الحقيقة."""
        return self.witness_guilty if truth == GUILTY else self.witness_innocent

    def false_line(self, truth: str) -> str:
        """رواية الزور: عكس الحقيقة."""
        return self.witness_innocent if truth == GUILTY else self.witness_guilty

    def defendant_story(self, truth: str) -> str:
        return self.defendant_guilty if truth == GUILTY else self.defendant_innocent


def _build(raw: dict) -> Case:
    return Case(
        id=raw["id"], title=raw["title"], charge=raw["charge"], scene=raw["scene"],
        witness_guilty=raw["witness_guilty"], witness_innocent=raw["witness_innocent"],
        defendant_guilty=raw["defendant_guilty"], defendant_innocent=raw["defendant_innocent"],
        clues_prosecution=tuple(raw["clues_prosecution"]),
        clues_defense=tuple(raw["clues_defense"]),
    )


CASES: List[Case] = [_build(r) for r in (*CASES_A, *CASES_B)]
CASES_BY_ID = {c.id: c for c in CASES}


def pick_case(rng: random.Random, recent_ids: Iterable[str] = ()) -> Case:
    """اختيار عشوائي لقضية بعيداً عن آخر القضايا المستعملة في هذا القروب."""
    recent = set(recent_ids)
    pool = [c for c in CASES if c.id not in recent] or CASES
    return rng.choice(pool)


def get_case(case_id: Optional[str]) -> Optional[Case]:
    return CASES_BY_ID.get(case_id) if case_id else None
