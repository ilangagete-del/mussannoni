# Fidelity report — measured, not claimed

Generated 2026-09-24 16:59 UTC by `tools/fidelity_report.py` from `tools/fidelity_gate.py` output.

* gate: **100% visible-pixel match on every page of every report**, rasterised at 2x, visible = max RGB channel delta <= 8
* result: **PASS 0/19**, worst page across all reports **90.9330% visible**

`visible` is the gate's criterion; `exact` (zero delta on every channel) is shown as well, because the gap between them is glyph-edge antialiasing.

| Report | pages | worst page visible | worst page exact | baseline visible | change |
|---|---:|---:|---:|---:|---:|
| S1051-MKOLANI SECONDARY SCHOOL | 13 | 90.9330% | 68.1231% | 64.2245% | +26.71 pt |
| MWANZA CC 10 BEST STUDENTS | 5 | 93.8269% | 89.8311% | 78.8911% | +14.94 pt |
| Mwanza f2 Mock Mobility 2026 | 6 | 93.9966% | 87.3956% | 42.4839% | +51.51 pt |
| Mwanza Schools Rank For Governments | 4 | 95.0529% | 92.7436% | 38.8558% | +56.20 pt |
| Mwanza Schools Rank For Governments (1) | 4 | 95.0529% | 92.7436% | 38.8558% | +56.20 pt |
| Mwanza schools rank Overall | 6 | 95.2218% | 94.4422% | 41.4503% | +53.77 pt |
| MWANZA CC SCHOOLS RANK | 1 | 96.2532% | 64.3854% | 75.9212% | +20.33 pt |
| Mwanza School Rank-English Language | 6 | 97.0000% | 96.4596% | 50.5711% | +46.43 pt |
| Mwanza Best Students-Overall | 9 | 97.0570% | 96.7473% | 85.2537% | +11.80 pt |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | 24 | 97.2361% | 73.2701% | 50.2034% | +47.03 pt |
| Mwanza Overall Subjects Performance | 2 | 97.7869% | 93.7591% | 79.0369% | +18.75 pt |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | 30 | 98.2994% | 93.2470% | 88.5419% | +9.76 pt |
| Mwanza Top 10 Schools | 6 | 98.5802% | 97.6297% | 82.2047% | +16.38 pt |
| Mwanza Best students-Subjectwise | 23 | 98.7237% | 95.7867% | 86.4667% | +12.26 pt |
| MWANZA CC SUBJECTS RANK | 2 | 98.8673% | 76.5124% | 80.7537% | +18.11 pt |
| Mwanza School Rank-EDK | 1 | 98.8892% | 98.6863% | 76.9805% | +21.91 pt |
| Mwanza f2 District Performance | 5 | 99.1381% | 98.8950% | 84.6693% | +14.47 pt |
| MWANZA CC Wards Rank | 1 | 99.1666% | 79.0910% | 61.6775% | +37.49 pt |
| MWANZA CC 10 BEST SCHOOLS | 3 | 99.4301% | 81.4279% | 63.4253% | +36.00 pt |

## How to read this

A report is only DONE at 100% visible on **every** page (see `docs/FIDELITY_SPEC.md` §10). Nothing in this table is done. The gate exits non-zero and `pytest -m slow` fails while that is true.

