# Fidelity report — measured, not claimed

Generated 2026-09-24 18:21 UTC by `tools/fidelity_report.py` from `tools/fidelity_gate.py` output.

* gate: **100% visible-pixel match on every page of every report**, rasterised at 2x, visible = max RGB channel delta <= 8
* result: **PASS 0/19**, worst page across all reports **96.9968% visible**

`visible` is the gate's criterion; `exact` (zero delta on every channel) is shown as well, because the gap between them is glyph-edge antialiasing.

**replay ceiling** is what `tools/replay.py` scores when it places the reference's OWN glyph origins and rectangles through this same pipeline - the most any renderer here could achieve. The last column is therefore what is still winnable; the rest is the toolchain's rasterisation floor.

| Report | pages | worst page visible | worst page exact | baseline | change | replay ceiling | gap to ceiling |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mwanza f2 Mock Mobility 2026 | 6 | 96.9968% | 90.6052% | 42.4839% | +54.51 pt | 99.8675% | +2.87 pt |
| S1051-MKOLANI SECONDARY SCHOOL | 13 | 97.1377% | 70.7404% | 64.2245% | +32.91 pt | 99.5404% | +2.40 pt |
| Mwanza School Rank-English Language | 6 | 97.5641% | 97.0524% | 50.5711% | +46.99 pt | 99.9358% | +2.37 pt |
| Mwanza Best Students-Overall | 9 | 97.6013% | 97.3797% | 85.2537% | +12.35 pt | 99.8441% | +2.24 pt |
| Mwanza Schools Rank For Governments | 4 | 97.9632% | 96.0820% | 38.8558% | +59.11 pt | 99.6789% | +1.72 pt |
| Mwanza Schools Rank For Governments (1) | 4 | 97.9632% | 96.0820% | 38.8558% | +59.11 pt | 99.6789% | +1.72 pt |
| Mwanza schools rank Overall | 6 | 98.3628% | 98.1125% | 41.4503% | +56.91 pt | 99.8129% | +1.45 pt |
| MWANZA CC 10 BEST STUDENTS | 5 | 98.5350% | 94.7958% | 78.8911% | +19.64 pt | 99.8157% | +1.28 pt |
| Mwanza Best students-Subjectwise | 23 | 98.8328% | 95.8330% | 86.4667% | +12.37 pt | 99.8610% | +1.03 pt |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | 30 | 98.8893% | 94.0866% | 88.5419% | +10.35 pt | 99.8162% | +0.93 pt |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | 24 | 98.9748% | 74.4289% | 50.2034% | +48.77 pt | 99.6981% | +0.72 pt |
| Mwanza School Rank-EDK | 1 | 99.1678% | 99.0049% | 76.9805% | +22.19 pt | 100.0000% | +0.83 pt |
| Mwanza f2 District Performance | 5 | 99.2258% | 99.0094% | 84.6693% | +14.56 pt | 99.9846% | +0.76 pt |
| Mwanza Overall Subjects Performance | 2 | 99.3229% | 95.2363% | 79.0369% | +20.29 pt | 99.9797% | +0.66 pt |
| MWANZA CC SCHOOLS RANK | 1 | 99.4876% | 66.5401% | 75.9212% | +23.57 pt | 99.6573% | +0.17 pt |
| MWANZA CC SUBJECTS RANK | 2 | 99.5138% | 76.9393% | 80.7537% | +18.76 pt | 99.6727% | +0.16 pt |
| MWANZA CC Wards Rank | 1 | 99.6535% | 79.4697% | 61.6775% | +37.98 pt | 99.9511% | +0.30 pt |
| MWANZA CC 10 BEST SCHOOLS | 3 | 99.7399% | 81.6309% | 63.4253% | +36.31 pt | 99.9274% | +0.19 pt |
| Mwanza Top 10 Schools | 6 | 99.8105% | 98.4242% | 82.2047% | +17.61 pt | 99.9026% | +0.09 pt |

## How to read this

A report is only DONE at 100% visible on **every** page (see `docs/FIDELITY_SPEC.md` §10). Nothing in this table is done. The gate exits non-zero and `pytest -m slow` fails while that is true.

