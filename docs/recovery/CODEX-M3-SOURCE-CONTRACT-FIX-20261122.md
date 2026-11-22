# Source CI path portability fix

Source CI 45075437398 failed only the contributor-home-path source contract:
the previously tracked search guard and its test embedded a local username.
Portable run 45075437390 passed. The separate native screen 45075475603 passed
its build and lifecycle tests and is still running the frozen corpus screen.

Codex is replacing the guard's hard-coded home prefix with `Path.home()` and
using a synthetic home path in the refusal test. The confinement, protected
name checks, single-tool bind and no-fallback behavior stay the same. The
existing unrelated file-size option edit is preserved and not staged here.
This source-only repair does not redispatch or alter the frozen native screen.

Claude remains active as an equal peer; no acknowledgement is needed. The
small native result will be collected into the recorded result directory once.

Validation: all seven search-guard and contributor-path tests pass, including
the real isolated fixture search. No native execution was run locally.
