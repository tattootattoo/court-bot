"""الأدوار وتوزيعها العشوائي — منطق نقي بلا أي إدخال/إخراج.

كل لاعب له دور «علني» يراه الجميع في القروب (قاضٍ، مدّعٍ، محامٍ، متهم، شاهد، محلّف)
ودور «سرّي» لا يعرفه إلا صاحبه عبر رسالة البوت الخاصة (شاهد صادق/شاهد زور،
محقق، مرتشٍ ...).
"""
from __future__ import annotations

import random
from typing import Dict, List, Sequence

JUDGE = "judge"
PROSECUTOR = "prosecutor"
DEFENSE = "defense"
DEFENDANT = "defendant"
WITNESS_TRUE = "witness_true"
WITNESS_FALSE = "witness_false"
JUROR = "juror"
DETECTIVE = "detective"
BRIBED = "bribed"

ALL_ROLES = (JUDGE, PROSECUTOR, DEFENSE, DEFENDANT, WITNESS_TRUE,
             WITNESS_FALSE, JUROR, DETECTIVE, BRIBED)

WITNESS_ROLES = (WITNESS_TRUE, WITNESS_FALSE)
JUROR_ROLES = (JUROR, DETECTIVE, BRIBED)
# من يحق له التصويت على الحكم: القاضي + الشهود + هيئة المحلّفين.
VOTER_ROLES = (JUDGE,) + WITNESS_ROLES + JUROR_ROLES

MIN_PLAYERS_ABS = 4      # أقل عدد تقني (للتجربة)، والافتراضي للعبة الحقيقية أعلى
MAX_PLAYERS_ABS = 30

# الاسم والرمز العلني لكل مجموعة (هذا ما يظهر في القروب — لا يكشف الأدوار السرّية).
PUBLIC_GROUPS = {
    "judge": ("👨‍⚖️", "القاضي"),
    "prosecutor": ("🗣️", "المدّعي العام"),
    "defense": ("🛡️", "محامي الدفاع"),
    "defendant": ("🔒", "المتهم"),
    "witness": ("👁️", "الشهود"),
    "juror": ("👥", "هيئة المحلّفين"),
}
PUBLIC_ORDER = ("judge", "prosecutor", "defense", "defendant", "witness", "juror")

# الاسم الكامل (يُعرض لصاحب الدور فقط، أو عند الكشف في النهاية).
ROLE_NAMES = {
    JUDGE: ("👨‍⚖️", "القاضي"),
    PROSECUTOR: ("🗣️", "المدّعي العام"),
    DEFENSE: ("🛡️", "محامي الدفاع"),
    DEFENDANT: ("🔒", "المتهم"),
    WITNESS_TRUE: ("👁️", "شاهد عيان صادق"),
    WITNESS_FALSE: ("🤥", "شاهد زور"),
    JUROR: ("👥", "محلّف"),
    DETECTIVE: ("🕵️", "المحلّف المحقق"),
    BRIBED: ("💰", "المحلّف المرتشي"),
}


def public_group(role: str) -> str:
    """المجموعة العلنية للدور (الشاهد الصادق والكاذب كلاهما «witness»)."""
    if role in WITNESS_ROLES:
        return "witness"
    if role in JUROR_ROLES:
        return "juror"
    return role


def composition(n: int, rng: random.Random) -> List[str]:
    """قائمة الأدوار (غير مرتبة) لعدد لاعبين n.

    n=4: قاضٍ، مدّعٍ، محامٍ، متهم (وضع تجريبي)
    n=5: + شاهد واحد (صادق أو كاذب بالقرعة)
    n=6: + شاهدان (واحد صادق وواحد زور)
    n>=7: + محلّفون؛ محقق واحد من 2 محلّفين، ومرتشٍ من 4، وثانٍ من 8.
    """
    if n < MIN_PLAYERS_ABS:
        raise ValueError(f"أقل عدد لاعبين هو {MIN_PLAYERS_ABS}")
    roles = [DEFENDANT, JUDGE, PROSECUTOR, DEFENSE]
    if n == 5:
        roles.append(rng.choice([WITNESS_TRUE, WITNESS_FALSE]))
    elif n >= 6:
        roles += [WITNESS_TRUE, WITNESS_FALSE]
    jurors = max(0, n - 6)
    detective = 1 if jurors >= 2 else 0
    bribed = 0 if jurors < 4 else (1 if jurors < 8 else 2)
    roles += [DETECTIVE] * detective + [BRIBED] * bribed
    roles += [JUROR] * (jurors - detective - bribed)
    assert len(roles) == n
    return roles


def assign_roles(uids: Sequence[int], rng: random.Random) -> Dict[int, str]:
    """توزيع عشوائي منتظم (Fisher–Yates) للأدوار على اللاعبين.

    لا يتأثر بترتيب الانضمام ولا بمن فتح اللعبة: كل لاعب له نفس الاحتمال
    لكل دور. نمرّر rng حتى نستعمل SystemRandom في الإنتاج وrandom.Random(seed) في الاختبار.
    """
    uids = list(uids)
    if len(set(uids)) != len(uids):
        raise ValueError("لاعب مكرّر")
    roles = composition(len(uids), rng)
    rng.shuffle(roles)
    return dict(zip(uids, roles))
