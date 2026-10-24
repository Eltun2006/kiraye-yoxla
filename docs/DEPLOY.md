# Deploy: Hugging Face Spaces + Neon

```
İstifadəçi ──► Hugging Face Space (Docker, FastAPI + frontend, e5 modeli)
                    │  DATABASE_URL            │  GEMINI_API_KEY
                    ▼                          ▼
               Neon PostgreSQL (pgvector)   Google Gemini API
```

Hər ikisi pulsuzdur, kart tələb etmir. Açarları (key, şifrə) **heç vaxt** koda və ya git-ə yazmırıq — yalnız Space-in
"Secrets" bölməsinə.

## 1. Neon — verilənlər bazası (~5 dəq)

1. https://neon.tech → **Sign up** (GitHub və ya Google hesabı ilə ən asanıdır).
2. **Create project**:
   - Project name: `kiraye-yoxla`
   - Postgres version: 16 və ya 17 (fərq etmir)
   - Region: **AWS Europe Central (Frankfurt)** — Azərbaycana ən yaxın
3. Layihə açılanda **Connect** düyməsini basın → `Connection string` görünəcək, belə bir şey:
   `postgresql://neondb_owner:****@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
   - "Show password" basıb **tam sətri kopyalayın** və müvəqqəti bir yerdə saxlayın (3-cü addımda lazım olacaq).
   - Bu sətirdə şifrə var — heç kimə göndərməyin, çata yapışdırmayın.

pgvector-u əl ilə qoşmaq lazım deyil: tətbiq ilk açılışda `CREATE EXTENSION vector` miqrasiyasını özü işlədir.

## 2. Hugging Face — hesab və Space (~5 dəq)

1. https://huggingface.co/join → hesab açın, e-poçtu təsdiqləyin.
2. Sağ yuxarı **+ New → Space**:
   - Space name: `kiraye-yoxla`
   - License: `mit` (və ya boş)
   - SDK: **Docker** → template: **Blank**
   - Hardware: **CPU basic · 2 vCPU · 16 GB · FREE**
   - Visibility: **Public** (müəllimin linklə aça bilməsi üçün)
   - **Create Space**
3. Token: https://huggingface.co/settings/tokens → **Create new token** → Token type: **Write** → ad: `kiraye-push`
   → kopyalayın. (Bu, git push üçün "şifrə" olacaq.)

## 3. Space-ə açarları əlavə edin

Space səhifəsi → **Settings** → aşağıda **Variables and secrets** → **New secret**:

| Ad | Dəyər |
|---|---|
| `DATABASE_URL` | Neon-dan kopyaladığınız sətir |
| `GEMINI_API_KEY` | Gemini açarınız (https://aistudio.google.com/apikey) |

`LLM_PROVIDER=gemini`, `TRUST_PROXY=true`, `AUTO_INGEST_LAW=true` artıq Dockerfile-dadır, əlavə etmək lazım deyil.

## 4. Kodu göndərin (öz terminalınızda)

`USERNAME` yerinə Hugging Face istifadəçi adınızı yazın:

```bash
cd C:\Users\FinalProject
git remote add space https://huggingface.co/spaces/USERNAME/kiraye-yoxla
git push --force space main
```

- Login pəncərəsi açılsa: username = HF istifadəçi adı, password = 2-ci addımdakı **token** (hesab şifrəsi yox).
- `--force` lazımdır, çünki yeni Space-də HF-in özünün yaratdığı bir commit var; biz onu öz kodumuzla əvəz edirik.

## 5. Gözləyin və yoxlayın

- Space səhifəsində **Building** (~8–12 dəq: torch + model image-ə yazılır) → **Running**.
- **Logs** tabında bunları görməlisiniz:
  - `Running upgrade -> 0001 ... 0003` (Neon-da cədvəllər yaradıldı)
  - `[law] law table empty, auto-ingested 25 articles` (~1 dəq sonra)
- **App** tabında saytı açın → nümunə müqavilə ilə analiz edin → bəndlərdə § qanun nişanları görünməlidir.

## Bilmək lazım olanlar

- **Yuxu rejimi:** pulsuz Space 48 saat istifadə olunmasa yatır; ilk açılış ~1 dəq çəkir. Neon da 5 dəq
  boş qalanda dayanır, ilk sorğu bir neçə saniyə gecikir. Təqdimatdan 5 dəq əvvəl saytı bir dəfə açın.
- **Gemini limiti:** pulsuz plan gündə 20 sorğu. Tətbiq özü gündə 15 analizdən sonra dayanır (`DAILY_ANALYSIS_LIMIT`).
  Təqdimat günü eval işlətməyin — eyni kvotanı yeyir.
- **Yeniləmə:** kodu dəyişdikdən sonra `git commit` + `git push space main` → Space avtomatik yenidən qurulur.
- **Layihədən sonra:** Gemini açarını və HF tokenini silin/yeniləyin.
