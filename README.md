---
title: KirayəYoxla
emoji: 🏠
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: Kirayə müqaviləsində riskli bəndləri tapır
---

# 🏠 KirayəYoxla

Kirayə müqaviləsini yükləyin. Sistem müqaviləni bəndlərə bölür, hər bəndin kirayəçi üçün riskini qiymətləndirir, sadə dildə izah edir və daha ədalətli alternativ mətn təklif edir. Siz təklifləri qəbul edir, rədd edir və ya redaktə edirsiniz, sonra hesabatı və ev sahibinə göndəriləcək danışıq mesajını ixrac edirsiniz.

> ⚖️ Bu alət məlumat xarakterlidir və hüquqi məsləhət deyil.

Plan, ideyalar və roadmap üçün [docs/LAYIHE_PLANI.md](docs/LAYIHE_PLANI.md) faylına baxın.

## Arxitektura
```
Web UI (HTML/CSS/JS) ──HTTP──▶ FastAPI ──▶ parsing (pypdf / python-docx → bəndlər)
                                 │
                                 ├─▶ retrieval: hər bənd üçün top-5 qanun maddəsi
                                 │     dense: multilingual-e5-base → pgvector (cosine)
                                 │     lexical: BM25 (5 hərfli prefix)   ── RRF ilə birləşdirilir
                                 │
                                 ├─▶ LLM (Gemini / Claude, structured output → Pydantic)
                                 │     <law> maddələr + <contract> bəndlər → risk, izah, təklif, law_refs
                                 │
                                 └─▶ guardrail: hər istinad promptdakı rəsmi mətnə əsaslanmalıdır
                                         │
                          PostgreSQL 16 + pgvector (Docker, Alembic migrasiyaları)
```

## İşə salma (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # GEMINI_API_KEY və ya ANTHROPIC_API_KEY dəyərini yazın

# 0) PostgreSQL (Docker Desktop açıq olmalıdır) → 127.0.0.1:55432
docker compose up -d --wait db

# Qanun bazası (bir dəfə): Mülki Məcəllənin 33-cü fəsli → embedding → law_articles cədvəli
.\.venv\Scripts\python scripts\scrape_law.py        # e-qanun.az-dan yükləyir (data/law/ artıq repoda var)
.\.venv\Scripts\python scripts\ingest_law.py        # migrasiyaları tətbiq edir, 25 maddəni embed edib yazır

# (Gemini) açarı və model adını yoxla
.\.venv\Scripts\python scripts\check_gemini.py

# 1) Spike: terminalda sürətli yoxlama
.\.venv\Scripts\python scripts\spike_analyze.py data\samples\kiraye_synthetic_01.txt

# 2) Tətbiq (backend + UI birlikdə) → http://localhost:8000
.\.venv\Scripts\uvicorn backend.main:app --reload

# 3) Testlər (oflayn, LLM mock edilir). Default olaraq müvəqqəti SQLite istifadə olunur.
.\.venv\Scripts\python -m pytest -q
# Eyni testlər PostgreSQL üzərində (test bazası bir dəfə yaradılır):
docker compose exec db psql -U kiraye -c "CREATE DATABASE kiraye_test;"
$env:TEST_DATABASE_URL="postgresql+psycopg2://kiraye:kiraye@127.0.0.1:55432/kiraye_test"; .\.venv\Scripts\python -m pytest -q
```

UI build tələb etmir: `frontend/` qovluğundakı `index.html`, `styles.css` və `app.js` fayllarını FastAPI birbaşa təqdim edir. Açıq və qaranlıq rejimi, mobil görünüşü dəstəkləyir.

### PostgreSQL qeydləri
- Host portu **55432**-dir, çünki 5432 və 5433 portlarını çox vaxt Windows-da quraşdırılmış PostgreSQL və ya WSL tutur. Port yalnız `127.0.0.1`-ə bağlanır, ona görə şəbəkədən görünmür.
- `DATABASE_URL`-də `localhost` əvəzinə `127.0.0.1` yazın. Windows `localhost`-u IPv6 `::1` kimi aça bilər və bağlantı başqa serverə gedər.
- Docker yoxdursa, `.env` faylında SQLite sətrini aktiv edin. Kod hər iki bazada işləyir.
- Köhnə SQLite məlumatlarını köçürmək üçün: `python scripts/sqlite_to_postgres.py kiraye.db`
- Sxem **Alembic** ilə idarə olunur (`migrations/versions/`). App açılanda `alembic upgrade head` avtomatik işləyir. `create_all` ilə yaradılmış köhnə baza əvvəlcə `0001` kimi qeyd olunur (stamp), sonra yenilənir. SQLite-da (testlər) cədvəllər birbaşa yaradılır.

## LLM provayderi
`.env` faylındakı `LLM_PROVIDER` dəyəri ilə seçilir. Hər iki provayder eyni prompt-u alır və eyni Pydantic sxemini qaytarmalıdır, ona görə nəticələri müqayisə etmək olur.

| `LLM_PROVIDER` | Model | Qeyd |
|---|---|---|
| `gemini` | `GEMINI_MODEL` (default `gemini-2.5-flash`) | Pulsuz limiti var, inkişaf zamanı test üçün uyğundur. Açarı https://aistudio.google.com/apikey ünvanından almaq olar |
| `anthropic` | `LLM_MODEL` (default `claude-opus-5-5`) | Ödənişlidir, istifadəyə görə hesablanır |

> Gemini-nin pulsuz tierində göndərilən məlumat Google tərəfindən məhsulun təkmilləşdirilməsi üçün istifadə oluna bilər. Bu tierdə yalnız synthetic və ya şəxsi məlumat olmayan müqavilələrdən istifadə edin.

## Qanun maddələri (RAG)
Hər bəndin yanında Mülki Məcəllənin uyğun maddəsi göstərilir (§ 688). Detal panelində rəsmi mətn görünür və izahda adı çəkilən bəndlər (məs. 688.2) vurğulanır.

- **Mənbə:** [e-qanun.az/framework/46944](https://e-qanun.az/framework/46944), 33-cü fəsil "Əmlak kirayəsi", maddə 675–699 → `data/law/mulki_mecelle_fesil33.json`. Sayt JavaScript ilə işləyir, statik fayl isə brauzer olmayan sorğulara 403 qaytarır. Ona görə rəsmi səhifə headless Chrome ilə bir dəfə açılır, mətn keşlənir (`--from-raw` ilə oflayn yenidən parse olunur).
- **Retrieval seçimi ölçülərək edilib** (`eval/retrieval_eval.py`, 20 etiketlənmiş bənd):

| Üsul (bütöv maddə) | hit@1 | hit@3 | hit@5 |
|---|---|---|---|
| BM25 | 60% | 70% | 75% |
| BM25 + 5 hərfli stem | 55% | 80% | 85% |
| e5-small (dense) | 30% | 50% | 60% |
| e5-base (dense) | 25% | 55% | 70% |
| **hibrid e5-base + BM25s (RRF)** | 40% | **85%** | **90%** |

  Embedding tək başına BM25-dən zəifdir, hibrid isə hər ikisindən yaxşıdır. Maddələri bəndlərə (688.1, 688.2…) bölmək kömək etmədi (hibrid hit@5 85%).
- **Uydurma istinada qarşı guardrail** (`analyzer.enforce_citations`): LLM yalnız promptdakı `<law>` blokunda olan maddələrə istinad edə bilər. Blokda olmayan istinad atılır və `invalid_refs` metrikasında sayılır (hədəf 0). İzahda adı çəkilən, blokda olan maddə isə avtomatik `law_refs`-ə əlavə olunur ki, istifadəçi mənbəni görsün.
- Qanun cədvəli boşdursa və ya retrieval xəta verirsə, analiz istinadsız davam edir.

## Təhlükəsizlik
Analiz ID-ləri təxmin edilə bilmir və tarixçə yalnız brauzerdə saxlanılır. Limitlər: IP başına saatda 5 analiz, servis üzrə gündə 15. Fayllar yoxlanılır, analizlər silinə bilər, 30 gündən sonra avtomatik silinir. Ətraflı təhdid modeli: [docs/SECURITY.md](docs/SECURITY.md).

## API
| Method | Path | Təsvir |
|---|---|---|
| POST | `/analyses` | `file` və ya `text`. Analiz fonda başlayır (202) |
| GET | `/analyses?ids=a,b` | Yalnız göstərilən ID-lərin xülasəsi (brauzerin tarixçəsi üçün; qlobal siyahı yoxdur) |
| GET | `/analyses/{id}` | Status, bəndlər (`law_refs` ilə) və istinad edilən maddələrin mətni (`laws`) |
| DELETE | `/analyses/{id}` | Analizi və müqaviləni birdəfəlik silir |
| PATCH | `/analyses/{id}/clauses/{clause_id}` | `{"decision": "accepted"\|"rejected"\|"edited", "user_text": "..."}` |
| GET | `/analyses/{id}/report.md` | Markdown hesabatı |
| GET | `/analyses/{id}/message` | Ev sahibinə danışıq mesajı (yalnız qəbul edilmiş və ya redaktə edilmiş bəndlərdən) |
| GET | `/samples`, `/samples/{name}` | Synthetic nümunə müqavilələr |

## Data
`data/samples/` qovluğundakı müqavilələr **synthetic** nümunələrdir və real şəxslərə aid deyil:

| Fayl | Nə yoxlanılır |
|---|---|
| `kiraye_synthetic_01.txt` | Sadə nömrələnmiş mətn, çoxlu açıq-aşkar risk |
| `kiraye_synthetic_02.docx` | Word-un avtomatik nömrələməsi, imza sətri, ədalətli və ədalətsiz bəndlərin qarışığı |
| `kiraye_synthetic_03.pdf` | 2 səhifə, "Səhifə N / M" footer-i, **prompt injection** bəndi (11) |

DOCX və PDF faylları `python scripts/make_sample_files.py` əmri ilə yenidən yaradılır.

## Parser necə işləyir
- **DOCX:** Word-un avtomatik nömrələməsi paragraf mətnində olmur. Ona görə `numbering.xml` oxunur: yuxarı səviyyəli nömrələnmiş elementlər bənd sayılır, alt səviyyələr və bullet-lər öz bəndinin içində qalır.
- **PDF:** "Səhifə 1 / 2", "Page 3 of 5" kimi header və footer sətirləri silinir.
- **Hamısı:** Son bənddən sonrakı imza bloku ("Tərəflərin imzaları", `____`) bəndə qoşulmur. Skan edilmiş, zədələnmiş və ya şifrəli fayllar üçün aydın xəta mesajı göstərilir.
