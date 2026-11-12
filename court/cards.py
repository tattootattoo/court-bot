"""الرسائل الخاصة (DM): بطاقة الدور السرّية، لوحة التصويت، شرح اللعبة."""
from __future__ import annotations

from typing import Optional, Tuple

from . import roles as R
from .cases import GUILTY, INNOCENT
from .game import Game, Player
from .render import btn, esc, kb
from .scoring import POINTS


def truth_word(truth: str) -> str:
    return "مذنب" if truth == GUILTY else "بريء"


def welcome_dm(game: Game) -> str:
    return (f"✅ تم تسجيلك في محكمة «{esc(game.title)}».\n"
            "انتظر بدء الجلسة — دورك السرّي سيصل إلى هنا 🔒\n"
            "لا تحذف هذه المحادثة ولا تكتم البوت!")


def _head(game: Game, p: Player) -> str:
    emoji, name = R.ROLE_NAMES[p.role]
    return f"{emoji} <b>دورك السرّي: {name}</b>\n🏛️ محكمة «{esc(game.title)}»"


def _case(game: Game) -> str:
    c = game.case
    return f"\n\n📂 <b>القضية:</b> {esc(c.title)}\n⚖️ <b>التهمة:</b> {esc(c.charge)}"


def _numbered(items) -> str:
    return "\n".join(f"{i}) {esc(t)}" for i, t in enumerate(items, 1))


def role_card(game: Game, p: Player) -> Tuple[str, Optional[dict]]:
    """نص بطاقة الدور وأزرارها (إن وُجدت أزرار لهذا الدور)."""
    role, t = p.role, game.truth
    out = _head(game, p) + _case(game) + "\n\n"
    if role == R.JUDGE:
        out += (f"🎯 <b>مهمتك:</b> أدِر الجلسة بحكمة (أو بمرح!)، استجوب الشهود وسيّر النقاش. "
                f"صوتك يحسم التعادل، وتكسب {POINTS['judge_correct']} نقاط إن طابق الحكم الحقيقة.\n\n"
                f"💡 <b>أسئلة مقترحة:</b>\n{_numbered(game.judge_questions)}\n\n"
                "⏭️ يمكنك تخطّي أي مرحلة بزر «المرحلة التالية» في القروب.")
    elif role in (R.PROSECUTOR, R.DEFENSE):
        goal = ("إقناع المحلّفين <b>بإدانة</b> المتهم" if role == R.PROSECUTOR
                else "إقناع المحلّفين <b>ببراءة</b> المتهم")
        pts = POINTS["prosecutor_win" if role == R.PROSECUTOR else "defense_win"]
        out += (f"🎯 <b>مهمتك:</b> {goal} (+{pts} نقاط عند الفوز).\n\n"
                f"🧾 <b>أدلتك السرّية:</b>\n{_numbered(game.evidence_for(role))}\n\n"
                f"اضغط زر الدليل لعرضه علناً في القروب (من بداية المرافعات). "
                f"يمكنك عرض {game.cfg.max_reveals} أدلة فقط — اختر بحكمة!")
    elif role == R.DEFENDANT:
        mood = ("😈 أنت <b>مذنب فعلاً</b>" if t == GUILTY else "😇 أنت <b>بريء</b>")
        tip = ("أنكر بذكاء وتجنّب التناقض؛ فقد يفضحك شاهد عيان صادق."
               if t == GUILTY else "دافع عن نفسك بهدوء؛ فقد يشهد ضدك كاذب!")
        out += (f"{mood} — ولا يعلم بذلك غيرك (وشاهد العيان).\n"
                f"📖 <b>الحقيقة كما حدثت:</b> {esc(game.secret_story(p))}\n\n"
                f"🎯 <b>مهمتك:</b> أن تُبرَّأ! {tip}")
    elif role == R.WITNESS_TRUE:
        out += (f"🔓 <b>الحقيقة:</b> المتهم <b>{truth_word(t)}</b>.\n"
                f"👁️ <b>ما رأيتَه:</b> «{esc(game.secret_story(p))}»\n\n"
                f"🎯 <b>مهمتك:</b> قل الحقيقة وأقنع المحكمة بها (+{POINTS['witness_true_ok']} إن صدر الحكم الصحيح).\n"
                "⚠️ قد يكون في القاعة شاهد زور يروي عكس ذلك — افضحه بالأسئلة والتفاصيل!")
    elif role == R.WITNESS_FALSE:
        out += (f"🔓 <b>الحقيقة:</b> المتهم <b>{truth_word(t)}</b> — لكنك ستقول العكس!\n"
                f"🎭 <b>روايتك الكاذبة:</b> «{esc(game.secret_story(p))}»\n\n"
                f"🎯 <b>مهمتك:</b> أقنع المحلّفين بروايتك (+{POINTS['witness_false_ok']} إن خُدعت المحكمة). "
                "تفادَ التناقض في التفاصيل؛ فقد يفضحك شاهد آخر!")
    elif role == R.BRIBED:
        want = "مذنب" if game.bribe_dir == GUILTY else "بريء"
        out += (f"💰 وصلك ظرف مليء بالنقود 😏 مقابل أن يصدر الحكم النهائي <b>«{want}»</b> "
                f"تنال +{POINTS['bribed_bonus']} نقاط.\n"
                f"لكنك ما زلت تكسب +{POINTS['juror_correct']} إن صوّتَّ بما يطابق الحقيقة. "
                "فهل تختار المال أم العدل؟ ولا تفضح نفسك!")
    else:
        out += (f"🎯 <b>مهمتك:</b> اسمع المرافعات وحلّل: من يقول الحقيقة؟ ثم صوّت بما تراه صحيحاً "
                f"(+{POINTS['juror_correct']} لكل تصويت يطابق الحقيقة).\n"
                f"🔎 وفي التصويت يمكنك تخمين <b>شاهد الزور</b> (+{POINTS['guess_correct']}).")
        if role == R.DETECTIVE:
            out += ("\n\n🕵️ <b>قوتك الخاصة:</b> فحص واحد! اختر شاهداً لتعرف إن كان صادقاً أم كاذباً. "
                    "النتيجة لك وحدك — أقنع الآخرين دون أن تفضح نفسك.")
    out += "\n\n🔒 <i>لا تُرِ هذه الرسالة لأحد!</i>"
    return out, role_markup(game, p)


def role_markup(game: Game, p: Player) -> Optional[dict]:
    """أزرار الإجراء السرّي حسب الدور (تُحدَّث بعد كل استعمال)."""
    cid = game.chat_id
    if p.role in (R.PROSECUTOR, R.DEFENSE):
        if len(p.reveals) >= game.cfg.max_reveals:
            return None
        row = [btn(f"🧾 الدليل {i + 1}", f"ev:{cid}:{i}")
               for i in range(len(game.evidence_for(p.role))) if i not in p.reveals]
        return kb([row]) if row else None
    if p.role == R.DETECTIVE and p.investigated is None:
        return kb([[btn(f"🔍 افحص: {w.name}", f"inv:{cid}:{w.uid}")] for w in game.witnesses()])
    return None


def investigation_text(target: Player, is_false: bool) -> str:
    verdict = "🤥 <b>كاذب!</b> إنه شاهد زور" if is_false else "✅ <b>صادق</b> — يقول الحقيقة"
    return f"🕵️ <b>نتيجة فحصك:</b> الشاهد «{esc(target.name)}» {verdict}.\nلا تفضح مصدرك!"


def vote_panel(game: Game, p: Player) -> Tuple[str, dict]:
    cid = game.chat_id
    mark = lambda cond: "✅ " if cond else ""  # noqa: E731
    rows = [[btn(f"{mark(p.vote == GUILTY)}⚖️ مذنب", f"vote:{cid}:g"),
             btn(f"{mark(p.vote == INNOCENT)}🕊️ بريء", f"vote:{cid}:i")]]
    c = game.case
    text = (f"🗳️ <b>حان وقت التصويت!</b>\n📂 {esc(c.title)}\n⚖️ {esc(c.charge)}\n\n"
            f"1️⃣ <b>ما حكمك؟</b> "
            + ({GUILTY: "اخترتَ: ⚖️ مذنب", INNOCENT: "اخترتَ: 🕊️ بريء"}.get(p.vote, "لم تختر بعد"))
            + "\n")
    if p.role not in R.WITNESS_ROLES:
        for w in game.witnesses():
            rows.append([btn(f"{mark(p.guess == w.uid)}🤥 الكاذب: {w.name}", f"fw:{cid}:{w.uid}")])
        rows.append([btn(f"{mark(p.guess == 0)}👍 لا أحد يكذب", f"fw:{cid}:0")])
        text += "2️⃣ <b>من تظنه شاهد الزور؟</b> (اختياري، +%d إن أصبت)" % POINTS["guess_correct"]
        if p.guess is not None:
            who = "لا أحد" if p.guess == 0 else game.players[p.guess].name
            text += f"\nاخترتَ: {esc(who)}"
        text += "\n"
    text += "\n🔒 صوتك سرّي حتى إعلان النتيجة، ويمكنك تغييره قبل انتهاء الوقت."
    return text, kb(rows)


def non_voter_text(p: Player) -> str:
    emoji, name = R.ROLE_NAMES[p.role]
    return (f"🗳️ بدأ التصويت! لكن بصفتك {emoji} <b>{name}</b> لا يحق لك التصويت — "
            "الحكم للقاضي والشهود والمحلّفين.\nانتظر إعلان الحكم في القروب 👀")


def vote_closed_text(game: Game, p: Player) -> str:
    chosen = {GUILTY: "⚖️ مذنب", INNOCENT: "🕊️ بريء"}.get(p.vote, "لم تصوّت")
    return f"🔒 انتهى التصويت.\nصوتك المسجَّل: {chosen}\nالنتيجة في القروب 👇"


def rules_text() -> str:
    p = POINTS
    return (
        "⚖️ <b>محكمة فكّك عقلك — طريقة اللعب</b>\n\n"
        "<b>الفكرة:</b> قضية طريفة، ومتهم قد يكون مذنباً وقد يكون بريئاً — الحقيقة يعرفها قلّة فقط! "
        "تتم المرافعات علناً في القروب، أما <b>أسرار الأدوار</b> فتصلك عند البوت في الخاص.\n\n"
        "<b>الأدوار (تُوزَّع عشوائياً):</b>\n"
        "👨‍⚖️ القاضي — يدير الجلسة وصوته يحسم التعادل\n"
        "🗣️ المدّعي العام — يريد الإدانة ويملك أدلة سرّية\n"
        "🛡️ محامي الدفاع — يريد البراءة ويملك أدلة سرّية\n"
        "🔒 المتهم — يعرف إن كان مذنباً أم بريئاً\n"
        "👁️ شاهد صادق — يعرف الحقيقة ويقولها\n"
        "🤥 شاهد زور — يعرف الحقيقة ويقول عكسها!\n"
        "👥 المحلّفون — يسمعون ويصوّتون، ومنهم 🕵️ محقق سرّي و💰 مرتشٍ\n\n"
        "<b>مراحل الجلسة:</b> توزيع الأدوار ← مرافعة الادعاء ← مرافعة الدفاع ← استجواب الشهود ← "
        "كلمة المتهم الأخيرة ← مداولة ← تصويت سرّي ← كشف الحقيقة والنقاط.\n\n"
        "<b>الحكم:</b> أغلبية أصوات (القاضي والشهود والمحلّفون). عند التعادل يحسم القاضي، "
        "وإن لم يصوّت فالأصل البراءة.\n\n"
        "<b>النقاط:</b>\n"
        f"▫️ المشاركة: {p['participation']}\n"
        f"▫️ قاضٍ أصاب الحقيقة: +{p['judge_correct']}\n"
        f"▫️ مدّعٍ كسب الإدانة: +{p['prosecutor_win']} — محامٍ كسب البراءة: +{p['defense_win']}\n"
        f"▫️ متهم تبرّأ: +{p['defendant_acquitted']} (ومذنب نجا بفعلته: +{p['defendant_escaped']} إضافية)\n"
        f"▫️ شاهد صادق والحكم صحيح: +{p['witness_true_ok']} — شاهد زور خدع المحكمة: +{p['witness_false_ok']}\n"
        f"▫️ محلّف صوّت بما يطابق الحقيقة: +{p['juror_correct']}\n"
        f"▫️ كشف شاهد الزور: +{p['guess_correct']} — مرتشٍ وافق الحكم رشوته: +{p['bribed_bonus']}\n\n"
        "<b>الأوامر:</b> /court فتح محكمة · /join انضمام · /leave انسحاب · /begin بدء · "
        "/status الحالة · /top لوحة الشرف · /cancel إلغاء"
    )


def private_help(username: Optional[str]) -> str:
    return (
        "👋 أهلاً! أنا بوت <b>محكمة فكّك عقلك</b> ⚖️\n\n"
        "أضفني إلى قروبك واكتب /court لفتح محكمة جديدة. بعد التوزيع العشوائي "
        "سيصلك دورك السرّي <b>هنا</b> وتمارس صلاحياته (عرض الأدلة، الفحص، التصويت السرّي).\n\n"
        "اكتب /rules لشرح اللعبة."
    )
