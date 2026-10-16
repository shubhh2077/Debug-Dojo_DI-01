# Mistake taxonomy

| Category | Detection |
|---|---|
| `off_by_one` | A failing numeric result differs by one, a list length differs by one, or multiple boundary failures cluster. |
| `unhandled_short_input` | A failing hidden test is tagged `empty_list`, `short_input`, or `k_larger_than_list`. |
| `print_not_return` | A failing test returned `None` while learner output was printed. |
| `boundary_comparison` | Exact-boundary hidden tests fail while at least one other hidden kind passes. |
| `mutates_input` | The child compares a deep copy of arguments before and after the learner call. |
