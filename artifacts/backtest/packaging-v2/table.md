# Breakwater backtest

29 items · verified known issues 9 · candidates 3 · total Nemotron cost $2.59

| arm | verified known caught | candidate known caught | items with any divergence |
|---|---|---|---|
| PR's own tests + benchmarks | 0/9 (by construction) | 0 | 0 |
| hypothesis | 2/9 | 0/3 | 4/29 |
| mutations | 7/9 | 1/3 | 10/29 |
| llm-plan | 5/9 | 1/3 | 10/29 |
| breakwater | 9/9 | 1/3 | 11/29 |

| item | merged | target | hypothesis | mutations | llm-plan | breakwater | known caught (breakwater) | perf: worst valid family | $ |
|---|---|---|---|---|---|---|---|---|---|
| #997 | 2026-01-06 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.060 |
| #1028 | 2026-01-06 | `Requirement` | 0 | 0 | 0 | 0 | – | – | 0.052 |
| #1029 | 2026-01-04 | `Marker` | 0 | 0 | 0 | 0 | – | – | 0.232 |
| #1030 | 2026-01-05 | `canonicalize_name` | 6 | 1 | 5 | 8 | unicode-lowercase | 4.52x many_underscores_and_dots | 0.051 |
| #1032 | 2026-01-02 | `Marker` | 0 | 1 | 1 | 1 | – | – | 0.041 |
| #1058 | 2026-01-14 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.180 |
| #1064 | 2026-01-19 | `canonicalize_name` | 6 | 1 | 7 | 9 | – | 1.10x many_underscores_and_dots | 0.048 |
| #1076 | 2026-01-30 | `SpecifierSet#filter` | 0 | 0 | 0 | 0 | – | – | 0.102 |
| #1081 | 2026-02-09 | `Specifier` | 0 | 0 | 0 | 0 | – | – | 0.074 |
| #1082 | 2026-02-11 | `Version` | 0 | 1 | 0 | 1 | oversized-int-exception | 2.85x Each numeric chunk increases digit count | 0.058 |
| 1082@61967cca | 2026-02-11 | `Version` | 0 | 2 | 2 | 7 | unicode-digits, inner-whitespace, oversized-int-exception | 1.91x versions with an epoch (e.g. "1!2.3.4") | 0.105 |
| #1083 | 2026-03-06 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.086 |
| #1105 | 2026-03-08 | `SpecifierSet#filter` | 0 | 0 | 0 | 0 | – | – | 0.124 |
| #1106 | 2026-03-09 | `Specifier` | 0 | 0 | 0 | 0 | – | – | 0.114 |
| #1108 | 2026-03-07 | `SpecifierSet` | 1 | 6 | 1 | 10 | dedup-equality, dedup-str-len, old-pickles-break-comparison | – | 0.093 |
| #1111 | 2026-03-09 | `Specifier#contains` | 0 | 0 | 0 | 0 | – | – | 0.121 |
| #1115 | 2026-03-11 | `Version` | 0 | 1 | 1 | 1 | – | – | 0.076 |
| #1116 | 2026-03-11 | `Version` | 0 | 1 | 1 | 1 | old-pickles-fail-to-load | – | 0.110 |
| #1118 | 2026-03-13 | `Version` | 0 | 0 | 0 | 0 | none | – | 0.070 |
| #1147 | 2026-04-05 | `Marker` | 0 | 1 | 1 | 1 | marker-pickle | – | 0.038 |
| #1236 † | 2026-06-09 | `parse_tag` | 3 | 4 | 2 | 7 | – | 1.09x tiny_tag | 0.090 |
| #1250 † | 2026-07-10 | `Marker#evaluate` | 0 | 0 | 0 | 0 | – | – | 0.041 |
| #1253 † | 2026-06-16 | `SpecifierSet#contains` | 0 | 0 | 0 | 0 | – | – | 0.099 |
| #1256 † | 2026-06-13 | `parse_wheel_filename` | 0 | 0 | 0 | 0 | – | – | 0.042 |
| #1258 † | 2026-06-13 | `Requirement` | 0 | 0 | 0 | 0 | – | – | 0.040 |
| #1259 † | 2026-06-15 | `SpecifierSet#contains` | 0 | 0 | 0 | 0 | – | – | 0.208 |
| #1320 † | 2026-07-07 | `Requirement` | 0 | 0 | 0 | 0 | none | – | 0.049 |
| #1371 † | 2026-09-25 | `Marker` | 0 | 0 | 0 | 0 | – | – | 0.139 |
| #1429 † | 2026-10-05 | `Marker` | 0 | 0 | 1 | 1 | – | – | 0.051 |

Cells are distinct divergence classes per arm. † merged after Nemotron 3 Ultra's release (2026-06-04).

#1111 and #1258 were re-run after v2 (transient API error; harness crash, fixed). #1028 and #1258 were re-scored after a P3 probe fix: an eq/hash contract violation already present on base is not a divergence.

Re-scored after the P4 control fix (`scripts/backtest/rescore_p4.py`): removed #1030 hypothesis 1, mutations 1, breakwater 1, llm-plan 1; #1064 hypothesis 1, mutations 1, breakwater 1, llm-plan 1; #1081 mutations 1, breakwater 1; #1106 mutations 2, breakwater 1; #1258 mutations 1, breakwater 1; #1320 mutations 1, breakwater 1.