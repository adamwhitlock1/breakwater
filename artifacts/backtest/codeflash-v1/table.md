# Breakwater backtest

10 items · verified known issues 0 · candidates 0 · total Nemotron cost $0.82

| arm | verified known caught | candidate known caught | items with any divergence |
|---|---|---|---|
| PR's own tests + benchmarks | 0/0 (by construction) | 0 | 0 |
| hypothesis | 0/0 | 0/0 | 0/10 |
| mutations | 0/0 | 0/0 | 0/10 |
| llm-plan | 0/0 | 0/0 | 1/10 |
| breakwater | 0/0 | 0/0 | 3/10 |

| item | merged | target | hypothesis | mutations | llm-plan | breakwater | known caught (breakwater) | perf: worst valid family | $ |
|---|---|---|---|---|---|---|---|---|---|
| Math-Interpreter#1 | 2025-02-09 | `Lexer#generate_tokens` | 0 | 0 | 1 | 3 | – | 1.05x Each call to generate_number now creates | 0.054 |
| micropie#3 | 2025-02-03 | `App()#_parse_cookies` | 0 | 0 | 0 | 0 | – | 1.34x cookies surrounded by whitespace | 0.052 |
| caddy-feeds#4 | 2025-02-09 | `is_excluded` | 0 | 0 | 0 | 1 | – | – | 0.038 |
| patterns#9 | 2025-02-09 | `validate_regex` | 0 | 0 | 0 | 0 | – | – | 0.028 |
| patterns#12 | 2025-02-09 | `sanitize_pattern` | 0 | 0 | 0 | 0 | – | – | 0.039 |
| rendercv#17 † | 2026-08-10 | `validate_typst_dimension` | 0 | 0 | 0 | 0 | – | – | 0.308 |
| rendercv#18 † | 2026-08-10 | `get_date_object` | 0 | 0 | 0 | 2 | – | 1.11x present_string | 0.062 |
| rendercv#19 † | 2026-08-10 | `get_date_object` | 0 | 0 | 0 | 0 | – | – | 0.048 |
| json_repair#113 | 2025-05-16 | `ObjectComparer.is_same_object` | 0 | 0 | 0 | 0 | – | 393.38x swap position of the mismatched key with | 0.147 |
| pyhs3#154 | 2026-01-26 | `parse_expression` | 0 | 0 | 0 | 0 | – | – | 0.042 |

Cells are distinct divergence classes per arm. † merged after Nemotron 3 Ultra's release (2026-06-04).

pyhs3#154 was re-run after a harness fix (sympy's symbolic comparisons broke JSON output); its perf families are unmeasured because the instruction count is not linear in repetitions (caching).