# Evaluation qeydləri (manual müşahidələr)

4-cü həftədə `eval/dataset.jsonl` test set-i bu qeydlər əsasında qurulacaq. Hər sətir bir bəndin gözlənilən risk səviyyəsini göstərir.

## 2026-10-24: Gemini 2.5 Flash, ilk real analizlər

| Nümunə | Bənd | Gözlənilən | Model | Qeyd |
|---|---|---|---|---|
| 01.txt | 4, 5, 7, 8, 10 | high | high ✓ | Bütün açıq-aşkar ədalətsiz bəndlər tapıldı |
| 01.txt | 6 (10% gündəlik cərimə) | high | high ✓ | |
| 01.txt | 11 (ev heyvanı qadağası) | low / medium? | low | **Sərhəd halı.** Qanunidir, amma kirayəçi üçün məhdudiyyətdir. Etalonu müəyyənləşdirmək lazımdır |
| 02.docx | 6, 7, 9 | high | high ✓ | Qonaq icazəsi, divarların məcburi rənglənməsi, məhkəmə hüququndan imtina |
| 02.docx | 4 (depozit 10 gündə qaytarılır) | low | medium ✗ | **False positive.** Bənd ədalətlidir. Prompt-a ədalətli depozit nümunəsi əlavə edilə bilər |
| 03.pdf | 2, 3, 4, 5, 9 | high/medium | high ✓ | USD-yə bağlı qiymət və 7 günlük boşaltma tapıldı |
| 03.pdf | 5 (5 gündən sonra 1%) | medium? | high | Bəlkə də həddindən artıq sərtdir. Etalonu müəyyənləşdirmək lazımdır |
| 03.pdf | 11 (prompt injection) | medium | low → **medium ✓** | Prompt-a qayda əlavə ediləndən sonra düzəldi. Injection digər bəndlərin qiymətinə təsir etmədi |

## Sabitlik (non-determinism)
- 02.docx bənd 8 ("24 saat əvvəl xəbər verir", ədalətli bənd) birinci analizdə **low**, ikinci analizdə (#4) **medium** aldı. Eyni giriş fərqli nəticə verdi.
- 4-cü həftədə hər test müqaviləsi **3 dəfə** işlədiləcək və "sabitlik" metrikası ölçüləcək: neçə faiz bənd hər üç cəhddə eyni risk səviyyəsini alır.

## Ümumi müşahidələr
- **Recall** (riskli bəndləri tapmaq) yüksəkdir. **Precision**-da kiçik problem var: ədalətli bəndləri bəzən "medium" kimi qiymətləndirir.
- Gecikmə 16–27 saniyədir (10–13 bənd).
- Parser: TXT, DOCX (Word auto-numbering daxil) və PDF (2 səhifə, footer ilə) düzgün bölündü.

## 2026-10-25: Qanun RAG (3-cü həftə)

**Retrieval** (`eval/retrieval_eval.py`, 20 bənd, nəticələr `retrieval_results.json`-da): istehsalda hibrid e5-base + BM25s, bütöv maddələr, hit@5 = 90%. Qaçırılan hallar: "xəbərsiz mənzilə daxil olma" → 678 (qanunda "giriş" sözü yoxdur), "qonaq qəbulu" → 683.

**Grounded analiz, 01.txt** (Gemini 2.5 Flash, 39 s, ~15k input token):
- 5 (depozit) → 688. İzahda 688.2 (təminat ≤ 2 aylıq haqq, bankda, faiz kirayəçiyə) və 688.3 (yaşayış kirayəsində kirayəçinin ziyanına kənaraçıxma etibarsızdır) düzgün, rəsmi mətnə sadiq şəkildə göstərildi ✓
- 8 (bütün təmir kirayəçidə) → 680, 682 ✓
- 10 (3 günlük şifahi ləğv) → 691, 692 ✓
- 6 (gündəlik 10% cərimə) → 688.4 "dəbbə pulu barədə razılaşmanın qüvvəsi yoxdur". Mətn düzgün sitat gətirilib, amma **gecikmə cəriməsinin "dəbbə pulu" sayılması hüquqi cəhətdən mübahisəlidir**. Hüquqşünasla yoxlanmalıdır.
- 4 və 7 (birtərəfli artım, xəbərsiz giriş) → istinad yoxdur. Fəsildə birbaşa uyğun maddə tapılmadı, model uydurmadı ✓
- `invalid_refs` = 0. Birinci cəhddə sərt qayda ilə (yalnız həmin bəndin namizədləri) 5 idi, amma hamısı başqa bəndin namizədindən götürülmüş real maddələr idi. Qayda "promptdakı rəsmi mətnə əsaslanma" kimi dəqiqləşdirildi.

**4-cü həftə üçün:** citation precision (göstərilən maddə həqiqətən uyğundurmu?) üçün manual etiket; "uydurma istinad 0%" meyarı `invalid_refs` ilə avtomatik ölçülür.

**Grounded analiz, 02.docx, PostgreSQL + pgvector** (#6, 28.5 s, `invalid_refs` = 0):
- 4 (depozit 10 gündə, zərərlər çıxılmaqla qaytarılır): əvvəl **medium** (false positive), indi **high** idi, § 688, 682. Model real məqam tapdı: 688.2-yə görə depozit bankda faizlə saxlanmalıdır, müqavilədə bu yoxdur; "vurduğu zərərlər" ifadəsi isə qeyri-müəyyəndir. Amma bunun üçün "high" həddən artıq sərtdir. **Hipotez: qanun konteksti modeli daha sərt edir (recall ↑, precision ↓).** 4-cü həftədə eyni dataset RAG ilə və RAG-sız müqayisə edilməlidir.
- 8 (24 saat əvvəl xəbərdarlıq): bu dəfə **low** ✓ (əvvəlki qaçışlarda low/medium arasında dəyişirdi).
- 6 (qonaq icazəsi) → § 683, 7 → § 682, 9 (məhkəmədən imtina) → istinad yoxdur. 696 namizəd olsa da model onu bu bəndə bağlamadı.

## 2026-10-25: Gemini pulsuz limiti (4-cü həftə)
- `gemini-2.5-flash` pulsuz tier: **gündə 20 sorğu** (`GenerateRequestsPerDayPerProjectPerModel`, quotaValue 20). Limit model üzrə hesablanır və təxminən 9.5 saatdan sonra sıfırlanır.
- Tam qiymətləndirmə (5 müqavilə × 3 qaçış × 2 rejim) 30 çağırış tələb edir, yəni bir günə sığmır. 10 nəticə hazırdır (`eval/runs/`), qalan 20-si növbəti gün tamamlanacaq (runner hazır nəticələri ötürür).
- **Demo riski:** app eyni limitdən istifadə edir. Müdafiə günü səhər limiti boş saxlamaq və ya ödənişli açar/Claude-a keçmək lazımdır (5-ci həftə).
