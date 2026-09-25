# Fidelity report — measured, not claimed

Generated 2026-09-25 03:05 UTC by `tools/fidelity_report.py` from `tools/fidelity_gate.py` output.

* gate: **100% visible-pixel match on every page of every report**, rasterised at 2x, visible = max RGB channel delta <= 8
* result: **PASS 0/19**, worst page across all reports **98.9822% visible**

`visible` is the gate's criterion; `exact` (zero delta on every channel) is shown as well, because the gap between them is glyph-edge antialiasing.

**replay ceiling** is what `tools/replay.py` scores when it places the reference's OWN glyph origins and rectangles through this same pipeline - the most any renderer here could achieve. The last column is therefore what is still winnable; the rest is the toolchain's rasterisation floor.

| Report | pages | worst page visible | worst page exact | baseline | change | replay ceiling | gap to ceiling |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mwanza f2 Mock Mobility 2026 | 6 | 98.9822% | 92.8772% | 96.9968% | +1.99 pt | 99.8675% | +0.89 pt |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | 24 | 99.5151% | 74.7299% | 98.9748% | +0.54 pt | 99.6981% | +0.18 pt |
| S1051-MKOLANI SECONDARY SCHOOL | 13 | 99.5227% | 71.6539% | 97.1377% | +2.39 pt | 99.5404% | +0.02 pt |
| MWANZA CC SCHOOLS RANK | 1 | 99.6647% | 66.6740% | 99.4876% | +0.18 pt | 99.6573% | -0.01 pt |
| MWANZA CC SUBJECTS RANK | 2 | 99.6727% | 77.0226% | 99.5138% | +0.16 pt | 99.6727% | +0.00 pt |
| Mwanza Schools Rank For Governments | 4 | 99.6831% | 98.2597% | 97.9632% | +1.72 pt | 99.6789% | -0.00 pt |
| Mwanza Schools Rank For Governments (1) | 4 | 99.6831% | 98.2597% | 97.9632% | +1.72 pt | 99.6789% | -0.00 pt |
| MWANZA CC 10 BEST STUDENTS | 5 | 99.8122% | 96.0590% | 98.5350% | +1.28 pt | 99.8157% | +0.00 pt |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | 30 | 99.8211% | 94.2165% | 98.8893% | +0.93 pt | 99.8162% | -0.00 pt |
| Mwanza Best Students-Overall | 9 | 99.8418% | 99.8227% | 97.6013% | +2.24 pt | 99.8441% | +0.00 pt |
| Mwanza schools rank Overall | 6 | 99.8425% | 99.7567% | 98.3628% | +1.48 pt | 99.8129% | -0.03 pt |
| Mwanza Best students-Subjectwise | 23 | 99.8499% | 96.9328% | 98.8328% | +1.02 pt | 99.8610% | +0.01 pt |
| Mwanza Top 10 Schools | 6 | 99.9014% | 98.5691% | 99.8105% | +0.09 pt | 99.9026% | +0.00 pt |
| MWANZA CC 10 BEST SCHOOLS | 3 | 99.9252% | 81.6392% | 99.7399% | +0.19 pt | 99.9274% | +0.00 pt |
| MWANZA CC Wards Rank | 1 | 99.9372% | 79.6929% | 99.6535% | +0.28 pt | 99.9511% | +0.01 pt |
| Mwanza Overall Subjects Performance | 2 | 99.9764% | 95.7004% | 99.3229% | +0.65 pt | 99.9797% | +0.00 pt |
| Mwanza f2 District Performance | 5 | 99.9830% | 99.3325% | 99.2258% | +0.76 pt | 99.9846% | +0.00 pt |
| Mwanza School Rank-English Language | 6 | 99.9853% | 99.9691% | 97.5641% | +2.42 pt | 99.9358% | -0.05 pt |
| Mwanza School Rank-EDK | 1 | 99.9929% | 99.9798% | 99.1678% | +0.83 pt | 100.0000% | +0.01 pt |

## How to read this

A report is only DONE at 100% visible on **every** page (see `docs/FIDELITY_SPEC.md` §10). Nothing in this table is done. The gate exits non-zero and `pytest -m slow` fails while that is true.

