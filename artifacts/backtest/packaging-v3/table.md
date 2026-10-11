# Breakwater backtest

29 items · verified known issues 9 · candidates 3 · total Nemotron cost $1.58

| arm | verified known caught | candidate known caught | items with any divergence |
|---|---|---|---|
| PR's own tests + benchmarks | 0/9 (by construction) | 0 | 0 |
| hypothesis | 2/9 | 0/3 | 4/29 |
| mutations | 7/9 | 1/3 | 9/29 |
| llm-plan | 6/9 | 1/3 | 7/29 |
| breakwater | 9/9 | 1/3 | 9/29 |

| item | merged | target | hypothesis | mutations | llm-plan | breakwater | known caught (breakwater) | perf: worst valid family | $ |
|---|---|---|---|---|---|---|---|---|---|
| #997 | 2026-01-06 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.033 |
| #1028 | 2026-01-06 | `Requirement` | 0 | 0 | 0 | 0 | – | – | 0.021 |
| #1029 | 2026-01-04 | `Marker` | 0 | 0 | 0 | 0 | – | – | 0.018 |
| #1030 | 2026-01-05 | `canonicalize_name` | 6 | 1 | 5 | 8 | unicode-lowercase | – | 0.027 |
| #1032 | 2026-01-02 | `Marker` | 0 | 1 | 1 | 1 | – | – | 0.015 |
| #1058 | 2026-01-14 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.045 |
| #1064 | 2026-01-19 | `canonicalize_name` | 6 | 1 | 5 | 7 | – | – | 0.022 |
| #1076 | 2026-01-30 | `SpecifierSet#filter` | 0 | 0 | 0 | 0 | – | – | 0.048 |
| #1081 | 2026-02-09 | `Specifier` | 0 | 0 | 0 | 0 | – | – | 0.030 |
| #1082 | 2026-02-11 | `Version` | 0 | 1 | 0 | 2 | oversized-int-exception | – | 0.080 |
| 1082@61967cca | 2026-02-11 | `Version` | 0 | 2 | 1 | 5 | unicode-digits, inner-whitespace, oversized-int-exception | – | 0.047 |
| #1083 | 2026-03-06 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.035 |
| #1105 | 2026-03-08 | `SpecifierSet#filter` | 0 | 0 | 0 | 0 | – | – | 0.058 |
| #1106 | 2026-03-09 | `Specifier` | 0 | 0 | 0 | 0 | – | – | 0.090 |
| #1108 | 2026-03-07 | `SpecifierSet` | 1 | 6 | 8 | 15 | dedup-equality, dedup-str-len, old-pickles-break-comparison | – | 0.050 |
| #1111 | 2026-03-09 | `Specifier#contains` | 0 | 0 | 0 | 0 | – | – | 0.116 |
| #1115 | 2026-03-11 | `Version` | 0 | 0 | 0 | 0 | – | – | 0.041 |
| #1116 | 2026-03-11 | `Version` | 0 | 1 | 1 | 1 | old-pickles-fail-to-load | – | 0.089 |
| #1118 | 2026-03-13 | `Version` | 0 | 0 | 0 | 0 | none | – | 0.044 |
| #1147 | 2026-04-05 | `Marker` | 0 | 1 | 1 | 1 | marker-pickle | – | 0.017 |
| #1236 † | 2026-06-09 | `parse_tag` | 3 | 4 | 0 | 4 | – | – | 0.132 |
| #1250 † | 2026-07-10 | `Marker#evaluate` | 0 | 0 | 0 | 0 | – | – | 0.031 |
| #1253 † | 2026-06-16 | `SpecifierSet#contains` | 0 | 0 | 0 | 0 | – | – | 0.056 |
| #1256 † | 2026-06-13 | `parse_wheel_filename` | 0 | 0 | 0 | 0 | – | – | 0.107 |
| #1258 † | 2026-06-13 | `Requirement` | 0 | 0 | 0 | 0 | – | – | 0.010 |
| #1259 † | 2026-06-15 | `SpecifierSet#contains` | 0 | 0 | 0 | 0 | – | – | 0.082 |
| #1320 † | 2026-07-07 | `Requirement` | 0 | 0 | 0 | 0 | none | – | 0.108 |
| #1371 † | 2026-09-25 | `Marker` | 0 | 0 | 0 | 0 | – | – | 0.100 |
| #1429 † | 2026-10-05 | `Marker` | 0 | 0 | 0 | 0 | – | – | 0.032 |

Cells are distinct divergence classes per arm. † merged after Nemotron 3 Ultra's release (2026-06-04).

Re-scored after a P4 fix (P4 round-trip control; `scripts/backtest/rescore_p4.py`): removed #1115 mutations 1, breakwater 1.