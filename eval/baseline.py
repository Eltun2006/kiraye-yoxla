"""Non-LLM baseline: keyword rules. Answers "is the LLM worth its latency and cost?"

The rules were written from the DEV contracts (01–03) only, so on them the baseline is optimistic (it was
fitted to them). The fair comparison is on the HELD-OUT contracts (04–05), written after the rules.
"""
import re

HIGH = [
    r"heç bir halda", r"xəbər vermədən", r"istənilən vaxt", r"birtərəfli", r"məhkəməyə müraciət etməmək",
    r"asılı olmayaraq", r"avtomatik xitam", r"qaytarılmır", r"ev sahibinin qərarı", r"bütün təmir",
    r"şifahi xəbərdarlıq", r"\d+\s*%-i miqdarında cərimə",
]
MEDIUM = [
    r"cərimə", r"dollar", r"məzənnə", r"avtomatik", r"nağd", r"hər dəfə",
    r"icazə", r"qadağan", r"bilməz", r"kirayəçinin hesabına", r"süni intellekt",
]


def classify(text: str) -> str:
    t = text.lower()
    if any(re.search(p, t) for p in HIGH):
        return "high"
    if any(re.search(p, t) for p in MEDIUM):
        return "medium"
    return "low"
