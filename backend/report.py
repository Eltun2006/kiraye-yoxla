"""Markdown export. Plain templating — no AI needed to format a report."""
from .db import Analysis

RISK_LABEL = {"high": "🔴 Yüksək", "medium": "🟡 Orta", "low": "🟢 Aşağı"}


def _final_text(c) -> str | None:
    """The wording the tenant wants to propose, based on their decision."""
    if c.decision == "edited":
        return c.user_text
    if c.decision == "accepted":
        return c.suggestion
    return None


def build_report(a: Analysis, laws: list | None = None) -> str:
    """laws: the cited Civil Code articles (LawOut), appended as a source list."""
    risky = [c for c in a.clauses if c.risk in ("high", "medium")]
    counts = {r: sum(c.risk == r for c in a.clauses) for r in ("high", "medium", "low")}
    lines = [
        f"# Kirayə müqaviləsinin analizi — {a.filename}",
        "",
        "> Bu hesabat məlumat xarakterlidir və hüquqi məsləhət deyil.",
        "",
        f"**Xülasə:** {a.summary}",
        "",
        f"Yüksək: {counts['high']} · Orta: {counts['medium']} · Aşağı: {counts['low']}",
        "",
        "## Riskli bəndlər",
    ]
    for c in risky:
        lines += [
            "",
            f"### Bənd {c.idx} — {RISK_LABEL[c.risk]}",
            f"> {c.text}",
            "",
            f"**Niyə risklidir:** {c.explanation}",
        ]
        if c.law_refs:
            lines.append(f"**Qanun:** Mülki Məcəllə, maddə {', '.join(c.law_refs)}")
        if (t := _final_text(c)):
            lines.append(f"**Təklif olunan mətn:** {t}")

    if laws:
        lines += ["", "## İstinad edilən qanun maddələri", ""]
        lines += [f"- **Maddə {l.id}. {l.title}** — {l.source_url}" for l in laws]
        lines += ["", "_Maddələr avtomatik seçilib; rəsmi mətni e-qanun.az-da yoxlayın._"]

    lines += ["", "## Ev sahibinə danışıq mesajı", "", build_message(a)]
    return "\n".join(lines) + "\n"


def build_message(a: Analysis) -> str:
    """Negotiation message built only from clauses the tenant accepted or edited (human-in-the-loop)."""
    proposals = [(c.idx, _final_text(c)) for c in a.clauses if _final_text(c)]
    if not proposals:
        return "Heç bir təklif qəbul edilməyib. Mesaj yaratmaq üçün riskli bəndlərdə təklifləri qəbul edin və ya redaktə edin."
    lines = ["Salam! Müqaviləni imzalamazdan əvvəl aşağıdakı bəndlərdə dəyişiklik təklif edirəm:", ""]
    lines += [f"• Bənd {i}: {t}" for i, t in proposals]
    lines += ["", "Bu dəyişiklikləri müzakirə edə bilərikmi? Təşəkkür edirəm."]
    return "\n".join(lines)
