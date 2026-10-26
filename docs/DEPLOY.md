# Deploy: Render + Neon (pulsuz)

```
İstifadəçi ──► Render web service (FastAPI + frontend, 512 MB, Frankfurt)
                    │  DATABASE_URL                │  GEMINI_API_KEY
                    ▼                              ▼
               Neon PostgreSQL (pgvector)      Gemini API (analiz + embedding)
```

Niyə Hugging Face deyil: 2026-cı ilin iyulundan Docker Space-lər pulsuz hesablara bağlıdır (PRO $9/ay).
Lokal e5 modeli ~1.5 GB RAM istədiyi üçün 512 MB-lıq pulsuz serverə sığmırdı. Ona görə deploy-da embedding-i
Gemini API edir (`EMBED_PROVIDER=gemini`), bu da retrieval eval-da daha yaxşı nəticə verdi (hit@5 100%).

Açarları (şifrə, key) **heç vaxt** koda, git-ə və ya çata yazmırıq. Yalnız Render-in öz formasına.

## 1. Neon — verilənlər bazası
1. https://console.neon.tech → `kiraye-yoxla` layihəsi.
2. **Roles** → `neondb_owner` → **Reset password** (köhnə şifrə çatda göründüyü üçün).
3. **Connect** → **Show password** → sətrin hamısını kopyala, Notepad-də saxla.

pgvector-u əl ilə qoşmaq lazım deyil: tətbiq ilk açılışda `CREATE EXTENSION vector` miqrasiyasını özü işlədir.

## 2. Render — hesab
1. https://render.com → **Get Started** → **GitHub ilə** daxil ol (kod GitHub-dadır, belə ən asandır).
2. Render GitHub-a giriş icazəsi istəyəndə `kiraye-yoxla` reposunu seç (və ya "All repositories").

## 3. Blueprint ilə servisi yarat
1. Render dashboard → **New +** → **Blueprint**.
2. `kiraye-yoxla` reposunu seç → **Connect**. Render `render.yaml` faylını özü oxuyur.
3. İki dəyər soruşacaq:
   - `DATABASE_URL` → Neon-dan kopyaladığın sətir
   - `GEMINI_API_KEY` → Gemini açarın
4. **Apply** / **Deploy Blueprint**.

`LLM_PROVIDER`, `EMBED_PROVIDER`, `TRUST_PROXY`, `AUTO_INGEST_LAW`, Python versiyası artıq `render.yaml`-dadır.

## 4. Gözlə və yoxla
- Build ~3–5 dəq. **Logs**-da görməlisən:
  - `Running upgrade ... -> 0004` (Neon-da cədvəllər yaradıldı)
  - `[law] no vectors for gemini-embedding-001, auto-ingested 25 articles` (1–2 dəq sonra)
- Sayt ünvanı: `https://kiraye-yoxla.onrender.com` (ad tutulubsa, Render sonuna hərf əlavə edir).
- Nümunə müqavilə ilə analiz et → bəndlərdə § qanun nişanları görünməlidir.

## Bilmək lazım olanlar
- **Yuxu rejimi:** pulsuz servis 15 dəq boş qalanda yatır, ilk açılış ~1 dəq çəkir. Neon da 5 dəq sonra
  dayanır. Təqdimatdan 5 dəq əvvəl saytı bir dəfə aç.
- **Gemini limitləri (pulsuz):** analiz modeli gündə 20 sorğu. Tətbiq gündə 15 analizdən sonra özü dayanır.
  Embedding ayrıca limitdir (dəqiqədə 30k token). Təqdimat günü eval işlətmə, eyni kvotanı yeyir.
- **Yeniləmə:** `git push` → Render avtomatik yenidən deploy edir.
- **Layihədən sonra:** Gemini açarını və Neon şifrəsini yenilə.
