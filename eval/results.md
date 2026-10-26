# Qiymətləndirmə nəticələri

Dataset: 23 bənd, 2 / 5 sintetik müqavilə (gold: high 9, medium 0, low 14). LLM rejimləri hər müqavilə üzrə 2 dəfə işlədilib; rəqəmlər qaçışların ortalamasıdır. Etiketlər: `eval/dataset.jsonl`.

> ⚠️ **İlkin nəticə:** qiymətləndirmə hələ tamamlanmayıb (Gemini pulsuz limiti). Bütün üsullar eyni müqavilə və qaçışlar üzərində müqayisə olunur.

## Bütün dataset

| Metrika | Açar söz baseline | LLM (RAG-sız) | LLM + qanun RAG |
|---|---|---|---|
| Accuracy (qəbul edilən cavab) | 96% | 100% | 98% |
| Yüksək riskin tapılması (high → high) | 89% | 100% | 100% |
| Riskli bəndə xəbərdarlıq (medium/high → medium/high) | 100% | 100% | 100% |
| Yalançı həyəcan (yalnız low olan bəndlər) | 8% | 0% | 4% |
| Xəbərdarlıqların dəqiqliyi (precision) | 91% | 100% | 95% |
| Stabillik (bütün qaçışlarda eyni cavab) | 100% | 96% | 91% |
| Gözlənilən qanun maddəsinə istinad | — | 0% | 100% |
| Əsaslandırılmamış maddə istinadları (cəmi) | — | 0 | 0 |
| Orta gecikmə, s | ~0 | 22.2 | 38.9 |
| Orta input / output token | — | 1104 / 4818 | 15243 / 8815 |
| Accuracy diapazonu (min–max qaçış) | 96%–96% | 100%–100% | 96%–100% |

## Held-out: 04 və 05

Hələ işlədilməyib.

## Səhv və sərhəd hallar (çoxluq səsi qəbul edilən dəstdə deyil)

| Bənd | Gold | Açar söz baseline | LLM (RAG-sız) | LLM + qanun RAG | Qeyd |
|---|---|---|---|---|---|
| 01.txt #3 | low | **medium** | low | low | ödəniş qaydası (nağd, amma qəbzdən söz yoxdur) |
