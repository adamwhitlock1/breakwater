# Breakwater backtest

8 items · verified known issues 9 · candidates 1 · total Nemotron cost $0.77

| arm | verified known caught | candidate known caught | items with any divergence |
|---|---|---|---|
| PR's own tests + benchmarks | 0/9 (by construction) | 0 | 0 |
| hypothesis | 2/9 | 0/1 | 4/8 |
| mutations | 7/9 | 1/1 | 8/8 |
| llm-plan | 5/9 | 0/1 | 5/8 |
| breakwater | 9/9 | 1/1 | 8/8 |

| item | merged | target | hypothesis | mutations | llm-plan | breakwater | known caught (breakwater) | perf: worst valid family | $ |
|---|---|---|---|---|---|---|---|---|---|
| #1030 | 2026-01-05 | `canonicalize_name` | 6 | 1 | 5 | 7 | unicode-lowercase | 6.50x leading_and_alternating_pattern | 0.048 |
| #1064 | 2026-01-19 | `canonicalize_name` | 6 | 1 | 5 | 7 | – | 1.09x Normal package names are short‑ish alpha | 0.046 |
| #1082 | 2026-02-11 | `Version` | 0 | 1 | 0 | 1 | oversized-int-exception | 2.91x Leading zeros in first segment | 0.171 |
| 1082@61967cca | 2026-02-11 | `Version` | 0 | 2 | 2 | 6 | unicode-digits, inner-whitespace, oversized-int-exception | 2.86x Leading zeros in first segment | 0.079 |
| #1108 | 2026-03-07 | `SpecifierSet` | 1 | 6 | 3 | 11 | dedup-equality, dedup-str-len, old-pickles-break-comparison | – | 0.098 |
| #1116 | 2026-03-11 | `Version` | 0 | 1 | 0 | 1 | old-pickles-fail-to-load | – | 0.229 |
| #1147 | 2026-04-05 | `Marker` | 0 | 1 | 0 | 1 | marker-pickle | – | 0.031 |
| #1236 † | 2026-06-09 | `parse_tag` | 3 | 4 | 2 | 6 | – | 1.09x simple tag with one interpreter, one abi | 0.071 |

Cells are distinct divergence classes per arm. † merged after Nemotron 3 Ultra's release (2026-06-04).