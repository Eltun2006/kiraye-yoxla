"""Download the Civil Code (Mülki Məcəllə) from e-qanun.az and extract the rent chapter as JSON.

The site is a JS app and its static text file refuses non-browser requests (403), so we open the
official viewer page in a real (headless) Chrome via Selenium — exactly what a visitor does — once,
and cache the raw text locally. Re-parsing works offline with --from-raw.

Usage:
  python scripts/scrape_law.py             # download (one request) + parse
  python scripts/scrape_law.py --from-raw  # parse the cached raw text only
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAW_DIR = ROOT / "data" / "law"
RAW = LAW_DIR / "raw" / "mulki_mecelle.txt"
OUT = LAW_DIR / "mulki_mecelle_fesil33.json"

SOURCE_URL = "https://e-qanun.az/framework/46944"
CHAPTER_START, CHAPTER_END = "33-cü fəsil.", "34-cü fəsil."

_ARTICLE = re.compile(r"^Maddə (\d+(?:-\d+)?)\.\s*(.*)$")
_POINT = re.compile(r"^(\d+(?:-\d+)?\.\d+(?:\.\d+)?)\.\s+")
_FOOTNOTE = re.compile(r"\[\d+\]")


def download() -> str:
    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(SOURCE_URL)
        # The document text is injected by JavaScript; wait until the rent chapter is present.
        WebDriverWait(driver, 90).until(lambda d: CHAPTER_END in d.execute_script("return document.body.innerText"))
        return driver.execute_script("return document.body.innerText")
    finally:
        driver.quit()


def parse(raw: str) -> list[dict]:
    lines = [l.strip() for l in raw.splitlines()]
    lines = [l for l in lines if l]
    start = lines.index(CHAPTER_START)
    end = lines.index(CHAPTER_END, start)
    chapter_title = f"{CHAPTER_START} {lines[start + 1]}"

    articles, current = [], None
    for line in lines[start + 2: end]:
        line = _FOOTNOTE.sub("", line).strip()
        m = _ARTICLE.match(line)
        if m:
            current = {"article": m.group(1), "title": m.group(2).strip(), "paragraphs": []}
            articles.append(current)
        elif current is not None and line:
            current["paragraphs"].append(line)

    out = []
    for a in articles:
        text = "\n".join(a["paragraphs"])
        out.append({
            "id": f"MM-{a['article']}",
            "article": a["article"],
            "title": a["title"],
            "text": text,
            # sub-points like "684.1" help cite precisely and chunk long articles later
            "points": [p.split(" ", 1)[0].rstrip(".") for p in a["paragraphs"] if _POINT.match(p)],
            "chapter": chapter_title,
            "source_url": SOURCE_URL,
            "retrieved_at": date.today().isoformat(),
        })
    return out


def main() -> None:
    if "--from-raw" in sys.argv:
        raw = RAW.read_text(encoding="utf-8")
    else:
        print(f"Yüklənir: {SOURCE_URL} ...")
        raw = download()
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_text(raw, encoding="utf-8")

    articles = parse(raw)
    if not articles:
        sys.exit("Maddə tapılmadı — saytın strukturu dəyişmiş ola bilər.")
    OUT.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    sizes = sorted(len(a["text"]) for a in articles)
    print(f"{len(articles)} maddə yazıldı → {OUT.relative_to(ROOT)}")
    print(f"Maddələr: {articles[0]['article']}–{articles[-1]['article']} | uzunluq (simvol): "
          f"min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}")


if __name__ == "__main__":
    main()
