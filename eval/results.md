# Qiymətləndirmə nəticələri

Dataset: 61 bənd, 5 / 5 sintetik müqavilə (gold: high 15, medium 8, low 38). LLM rejimləri hər müqavilə üzrə 1 dəfə işlədilib; rəqəmlər qaçışların ortalamasıdır. Etiketlər: `eval/dataset.jsonl`.

> ⚠️ **İlkin nəticə:** qiymətləndirmə hələ tamamlanmayıb (Gemini pulsuz limiti). Bütün üsullar eyni müqavilə və qaçışlar üzərində müqayisə olunur.

## Bütün dataset

| Metrika | Açar söz baseline | LLM (RAG-sız) | LLM + qanun RAG |
|---|---|---|---|
| Accuracy (qəbul edilən cavab) | 85% | 98% | 89% |
| Yüksək riskin tapılması (high → high) | 67% | 93% | 100% |
| Riskli bəndə xəbərdarlıq (medium/high → medium/high) | 83% | 100% | 100% |
| Yalançı həyəcan (yalnız low olan bəndlər) | 15% | 3% | 21% |
| Xəbərdarlıqların dəqiqliyi (precision) | 81% | 96% | 79% |
| Stabillik (bütün qaçışlarda eyni cavab) | 100% | 100% | 100% |
| Gözlənilən qanun maddəsinə istinad | — | 0% | 100% |
| Əsaslandırılmamış maddə istinadları (cəmi) | — | 0 | 0 |
| Orta gecikmə, s | ~0 | 24.6 | 40.8 |
| Orta input / output token | — | 1162 / 5190 | 15277 / 8566 |
| Accuracy diapazonu (min–max qaçış) | 85%–85% | 98%–98% | 89%–89% |

## Held-out: 04 və 05 (25 bənd)

Prompt və baseline qaydaları 01–03-ə baxaraq hazırlanıb; 04–05 sonradan yazılıb. Ədalətli müqayisə budur.

| Metrika | Açar söz baseline | LLM (RAG-sız) | LLM + qanun RAG |
|---|---|---|---|
| Accuracy (qəbul edilən cavab) | 72% | 100% | 84% |
| Yüksək riskin tapılması (high → high) | 0% | 50% | 100% |
| Riskli bəndə xəbərdarlıq (medium/high → medium/high) | 50% | 100% | 100% |
| Yalançı həyəcan (yalnız low olan bəndlər) | 20% | 0% | 27% |
| Xəbərdarlıqların dəqiqliyi (precision) | 62% | 100% | 69% |
| Stabillik (bütün qaçışlarda eyni cavab) | 100% | 100% | 100% |
| Gözlənilən qanun maddəsinə istinad | — | 0% | 100% |

## Səhv və sərhəd hallar (çoxluq səsi qəbul edilən dəstdə deyil)

| Bənd | Gold | Açar söz baseline | LLM (RAG-sız) | LLM + qanun RAG | Qeyd |
|---|---|---|---|---|---|
| 01.txt #3 | low | **medium** | low | low | ödəniş qaydası (nağd, amma qəbzdən söz yoxdur) |
| 03.pdf #6 | low | **medium** | low | **medium** | subkirayə üçün razılıq — standart |
| 03.pdf #7 | low | low | **medium** | low | kiçik/əsaslı təmir bölgüsü — standart |
| 03.pdf #8 | low | low | low | **medium** | ayda 1 dəfə, 24 saat xəbərdarlıq |
| 03.pdf #10 | low | low | low | **medium** | kirayəçinin ləğv hüququ |
| 04.txt #2 | low | low | low | **medium** | razılıqla uzadılma |
| 04.txt #5 | low | low | low | **medium** | 1 aylıq depozit, bankda, 7 gün, köhnəlmə istisna |
| 04.txt #7 | low | **medium** | low | low | ədalətli təmir bölgüsü |
| 04.txt #9 | low | **medium** | low | **medium** | subkirayə üçün razılıq |
| 04.txt #11 | low | **medium** | low | low | ev heyvanı — əsassız rədd edilə bilməz |
| 05.txt #4 | medium/high | **low** | medium | high | 3 aylıq təminat > 688.2 həddi (2 ay); 688.3 ilə etibarsız |
| 05.txt #5 | medium/high | **low** | high | high | sabit ödəniş, birtərəfli dəyişə bilər |
| 05.txt #6 | medium/high | **low** | high | high | əşyaları saxlamaq hüququ (girov, 698) |
| 05.txt #9 | medium/high | **low** | high | high | şəxsi ehtiyac əsaslı ola bilər (692), amma 1 ay < 3 ay (691) |
| 05.txt #10 | low | low | low | **medium** | dəyişiklik üçün razılıq — standart |
