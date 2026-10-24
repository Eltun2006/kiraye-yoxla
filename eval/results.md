# Qiymətləndirmə nəticələri

Dataset: 61 bənd, 5 sintetik müqavilə (gold: high 15, medium 8, low 38). LLM rejimləri hər müqavilə üzrə 1 dəfə işlədilib; rəqəmlər qaçışların ortalamasıdır. Etiketlər: `eval/dataset.jsonl`.

| Metrika | Açar söz baseline |
|---|---|
| Accuracy (qəbul edilən cavab) | 90% |
| Yüksək riskin tapılması (high → high) | 67% |
| Riskli bəndə xəbərdarlıq (medium/high → medium/high) | 96% |
| Yalançı həyəcan (yalnız low olan bəndlər) | 15% |
| Xəbərdarlıqların dəqiqliyi (precision) | 83% |
| Stabillik (bütün qaçışlarda eyni cavab) | 100% |
| Gözlənilən qanun maddəsinə istinad | — |
| Əsaslandırılmamış maddə istinadları (cəmi) | — |
| Orta gecikmə, s | ~0 |
| Orta input / output token | — |
| Accuracy diapazonu (min–max qaçış) | 90%–90% |

## Səhv və sərhəd hallar (çoxluq səsi qəbul edilən dəstdə deyil)

| Bənd | Gold | Açar söz baseline | Qeyd |
|---|---|---|---|
| 01.txt #3 | low | **medium** | ödəniş qaydası (nağd, amma qəbzdən söz yoxdur) |
| 03.pdf #6 | low | **medium** | subkirayə üçün razılıq — standart |
| 04.txt #7 | low | **medium** | ədalətli təmir bölgüsü |
| 04.txt #9 | low | **medium** | subkirayə üçün razılıq |
| 04.txt #11 | low | **medium** | ev heyvanı — əsassız rədd edilə bilməz |
| 05.txt #9 | medium/high | **low** | şəxsi ehtiyac əsaslı ola bilər (692), amma 1 ay < 3 ay (691) |
