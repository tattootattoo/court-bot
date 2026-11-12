"""نصوص ولوحات الأزرار العلنية (التي تظهر في القروب). لا تكشف أي سرّ."""
from __future__ import annotations

import html
from typing import Iterable, List, Optional

from . import roles as R
from .cases import GUILTY
from .game import Game, Phase, Player
from .lines import GUILTY_SENTENCES, INNOCENT_SENTENCES

SINGULAR = {"witness": "الشاهد", "juror": "المحلّف"}
MEDALS = ["🥇", "🥈", "🥉"]
PHASE_INFO = {
    Phase.PROSECUTION: ("🗣️", "مرافعة الادعاء"),
    Phase.DEFENSE: ("🛡️", "مرافعة الدفاع"),
    Phase.WITNESSES: ("👁️", "استجواب الشهود"),
    Phase.LAST_WORD: ("🔒", "كلمة المتهم الأخيرة"),
    Phase.DELIBERATION: ("👥", "مداولة هيئة المحلّفين"),
    Phase.VOTING: ("🗳️", "التصويت السرّي"),
}


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def mention(p: Player) -> str:
    return f'<a href="tg://user?id={p.uid}">{esc(p.name)}</a>'


def mentions(ps: Iterable[Player]) -> str:
    return "، ".join(mention(p) for p in ps) or "—"


def verdict_label(v: str) -> str:
    return "⚖️ مذنب" if v == GUILTY else "🕊️ بريء"


def clock(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def btn(text: str, data: Optional[str] = None, url: Optional[str] = None) -> dict:
    b = {"text": text}
    if url:
        b["url"] = url
    else:
        b["callback_data"] = data
    return b


def kb(rows: List[List[dict]]) -> dict:
    return {"inline_keyboard": rows}


def deep_link(username: Optional[str], chat_id: int) -> Optional[str]:
    return f"https://t.me/{username}?start=join_{chat_id}" if username else None


# ───────────── الردهة ─────────────
def lobby_text(game: Game, lobby_minutes: int) -> str:
    need = max(game.cfg.min_players, R.MIN_PLAYERS_ABS)
    lines = [
        "⚖️ <b>محكمة فكّك عقلك</b>", "",
        "قاعة المحكمة مفتوحة! الأدوار تُوزَّع <b>عشوائياً</b> وتصل كل لاعب <b>سرّاً</b> في الخاص مع البوت 🔒",
        "", f"👥 <b>المنضمّون ({len(game.players)}/{game.cfg.max_players})</b>",
    ]
    if game.players:
        lines += [f"{i}. {mention(p)}" for i, p in enumerate(game.players.values(), 1)]
    else:
        lines.append("— لا أحد بعد —")
    lines += ["", f"▫️ الحد الأدنى للبدء: <b>{need}</b> لاعبين",
              f"▫️ المضيف: <b>{esc(game.host_name or 'المضيف')}</b>",
              f"⏳ تُغلق الردهة تلقائياً بعد {lobby_minutes} دقائق من الخمول."]
    return "\n".join(lines)


def lobby_kb(game: Game, username: Optional[str]) -> dict:
    cid = game.chat_id
    first = [btn("✋ انضم للمحكمة", f"join:{cid}")]
    link = deep_link(username, cid)
    if link:
        first.append(btn("🔗 فعّل البوت أولاً", url=link))
    return kb([first,
               [btn("🚪 انسحاب", f"leave:{cid}")],
               [btn("▶️ ابدأ المحكمة", f"begin:{cid}"), btn("❌ إلغاء", f"cancel:{cid}")]])


def need_start_kb(username: Optional[str], chat_id: int) -> Optional[dict]:
    link = deep_link(username, chat_id)
    return kb([[btn("🔗 افتح البوت واضغط Start", url=link)]]) if link else None


# ───────────── المراحل ─────────────
def roster_text(game: Game, seconds: float) -> str:
    lines = ["🔔 <b>افتُتحت الجلسة!</b>", "",
             "وُزِّعت الأدوار <b>عشوائياً</b> ووصل كل لاعب دوره <b>سرّاً</b> في الخاص 🔒",
             "اقرأ دورك ولا تُرِه لأحد!", ""]
    roster = game.public_roster()
    for g in R.PUBLIC_ORDER:
        ps = roster[g]
        if not ps:
            continue
        emoji, name = R.PUBLIC_GROUPS[g]
        if len(ps) == 1 and g in SINGULAR:
            name = SINGULAR[g]
        lines.append(f"{emoji} <b>{name}:</b> {mentions(ps)}")
    lines += ["", f"📂 يُعرض ملف القضية بعد {clock(seconds)} (وقت لقراءة الأدوار)"]
    return "\n".join(lines)


def case_block(game: Game) -> str:
    c = game.case
    return f"📂 <b>{esc(c.title)}</b>\n⚖️ <b>التهمة:</b> {esc(c.charge)}\n📖 {esc(c.scene)}"


def phase_text(game: Game, phase: Phase, seconds: float) -> str:
    r = game.public_roster()
    emoji, title = PHASE_INFO[phase]
    head = f"{emoji} <b>{title}</b> — ⏱️ {clock(seconds)}"
    if phase == Phase.PROSECUTION:
        body = (f"{case_block(game)}\n\n{head}\n"
                f"{mentions(r['prosecutor'])}، تفضّل بعرض الاتهام أمام المحكمة. "
                "يمكنك عرض أدلتك من رسالتك الخاصة مع البوت 🧾")
    elif phase == Phase.DEFENSE:
        body = (f"{head}\n{mentions(r['defense'])}، تفضّل بالرد على الاتهام. "
                f"و{mentions(r['defendant'])} يستمع بهدوء 😌")
    elif phase == Phase.WITNESSES:
        body = (f"{head}\n{mentions(r['witness'])} أمام المنصّة.\n"
                f"يا {mentions(r['judge'])}: استجوبهم! ولكل عضو في المحكمة حق السؤال.\n"
                "تذكّروا: قد يكون بينهم من يكذب 🤥")
    elif phase == Phase.LAST_WORD:
        body = f"{head}\n{mentions(r['defendant'])}، هذه فرصتك الأخيرة لإقناع المحكمة."
    elif phase == Phase.DELIBERATION:
        body = (f"{head}\nناقشوا بصوت عالٍ: من يقول الحقيقة؟ ومن المذنب فعلاً؟\n"
                "بعدها يصلكم التصويت السرّي في الخاص مع البوت.")
    else:
        cast, total = game.votes_cast()
        body = (f"{head}\nافتحوا محادثة البوت وصوّتوا سرّاً: <b>مذنب</b> أم <b>بريء</b>؟\n"
                "(التصويت للقاضي والشهود والمحلّفين)\n"
                f"🗳️ صوّت <b>{cast}</b> من <b>{total}</b>")
        if game.all_voted():
            body += "\n✅ اكتمل التصويت — يُعلَن الحكم خلال لحظات (يمكنكم تغيير أصواتكم حتى ذلك الحين)"
    return body


def vote_progress_text(game: Game, seconds: float) -> str:
    return phase_text(game, Phase.VOTING, seconds)


def skip_kb(game: Game) -> dict:
    return kb([[btn("⏭ المرحلة التالية (للقاضي أو المضيف)", f"skip:{game.chat_id}:{game.serial}")]])


def evidence_text(side: str, presenter: Player, text: str) -> str:
    who = "الادعاء" if side == "prosecution" else "الدفاع"
    return f"🧾 <b>دليل جديد من {who}</b> — قدّمه {mention(presenter)}\n«{esc(text)}»"


# ───────────── النتائج ─────────────
def results_text(game: Game) -> str:
    r = game.results
    ps = game.players
    pick = lambda uids: mentions(ps[u] for u in uids)  # noqa: E731
    rng = game.cfg.rng
    lines = [f"🔔 <b>الحكم: {verdict_label(r.verdict)}!</b>"]
    votes = f"🗳️ الأصوات: مذنب {len(r.guilty)} — بريء {len(r.innocent)}"
    if r.abstained:
        votes += f" — امتنع {len(r.abstained)}"
    lines.append(votes)
    if r.tie_note:
        lines.append(f"🔨 {r.tie_note}")
    defendant = game.first_with(R.DEFENDANT)
    lines += ["", f"🔓 <b>الحقيقة:</b> كان المتهم {mention(defendant)} "
                  f"<b>{'مذنباً' if r.truth == GUILTY else 'بريئاً'}</b>",
              f"📜 {esc(game.secret_story(defendant))}",
              "✅ أصابت المحكمة!" if r.correct else "❌ أخطأت المحكمة!", "",
              "🎭 <b>الأدوار السرّية:</b>"]
    for role in (R.WITNESS_TRUE, R.WITNESS_FALSE, R.DETECTIVE, R.BRIBED):
        ps_role = game.with_roles(role)
        if ps_role:
            emoji, name = R.ROLE_NAMES[role]
            extra = f" (رُشي لصالح «{'مذنب' if r.bribe_dir == GUILTY else 'بريء'}»)" if role == R.BRIBED else ""
            lines.append(f"{emoji} {name}: {mentions(ps_role)}{extra}")
    if r.guilty or r.innocent:
        parts = []
        if r.guilty:
            parts.append(f"⚖️ مذنب: {pick(r.guilty)}")
        if r.innocent:
            parts.append(f"🕊️ بريء: {pick(r.innocent)}")
        lines += ["", "🗳️ <b>من صوّت بماذا:</b>"] + parts
    lines += ["", "🏆 <b>النقاط:</b>"]
    for i, (p, pts) in enumerate(game.ranking()):
        medal = MEDALS[i] if i < len(MEDALS) else "▫️"
        emoji, name = R.ROLE_NAMES[p.role]
        why = "، ".join(r.awards[p.uid].reasons[1:])
        lines.append(f"{medal} {mention(p)} — <b>{pts}</b>  ({emoji} {name}{': ' + why if why else ''})")
    sentence = rng.choice(GUILTY_SENTENCES if r.verdict == GUILTY else INNOCENT_SENTENCES)
    lines += ["", f"🎭 <b>حكم المحكمة الساخر:</b> {sentence}", "", "🔁 لعبة جديدة: /court"]
    return "\n".join(lines)


def split_message(text: str, limit: int = 3900) -> List[str]:
    """تقسيم الرسائل الطويلة عند حدود الأسطر (حد تيليجرام 4096 حرفاً)."""
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def status_text(game: Game, seconds_left: float) -> str:
    names = {Phase.LOBBY: "🚪 الردهة (التسجيل)", Phase.ROLES: "🔔 توزيع الأدوار"}
    label = names.get(game.phase) or "{} {}".format(*PHASE_INFO[game.phase])
    return (f"📌 <b>حالة المحكمة</b>\nالمرحلة: {label}\n"
            f"اللاعبون: {len(game.players)}\nالوقت المتبقي للمرحلة: {clock(seconds_left)}")


def top_text(rows: List[dict]) -> str:
    if not rows:
        return "لا توجد نقاط بعد في هذا القروب. ابدأوا محكمة بـ /court ⚖️"
    lines = ["🏆 <b>لوحة شرف المحكمة</b>", ""]
    for i, r in enumerate(rows):
        medal = MEDALS[i] if i < len(MEDALS) else f"{i + 1}."
        lines.append(f"{medal} {esc(r['name'])} — <b>{r['points']}</b> نقطة "
                     f"({r['games']} جلسة، فاز {r['wins']})")
    return "\n".join(lines)
