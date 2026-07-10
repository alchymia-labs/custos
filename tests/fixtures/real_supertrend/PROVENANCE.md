# real_supertrend fixture mirror provenance

## Purpose

This directory is a **permanent in-repo mirror** of the ps SuperTrendStrategy
source files (option iii per the plan that first landed this mirror). The mirror
enables the sandbox end-to-end acceptance test
(`tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py`) to load the
production strategy class through the vendored toolkit substrate without
requiring a sibling `philosophers-stone/` repo checkout at test time.

Custos is an Apache-2.0 open-source project audited via single-repo clone. This
mirror is what makes the real-strategy sandbox acceptance test independent-clone
reproducible.

## Source pin

Upstream repo: `philosophers-stone` (Alephain Guild monorepo component)
Upstream branch: `develop`
Upstream commit: `3443e969bec5988276e96694806d1602b61e75fc`
Upstream commit subject: `feat(nautilus): supertrend production tier risk config`

## File mapping

| Fixture file | Upstream path |
|--------------|---------------|
| `strategy.py` | `trend/supertrend/refinement/nautilus/strategy.py` |
| `__init__.py` | `trend/supertrend/refinement/nautilus/__init__.py` |
| `config.yaml` | `trend/supertrend/config.yaml` |

## Runtime resolution

At test time the fixture `strategy.py` is loaded via
`custos.engines.nautilus.strategy_loader.load_strategy_class`; the module's
`from shared.<pkg>` imports resolve through the vendored toolkit's `sys.path`
bootstrap (`import custos.engines.nautilus.toolkit`), i.e. the vendored
`src/custos/engines/nautilus/toolkit/shared/<pkg>` tree. There is no runtime
lookup into a sibling `philosophers-stone/` checkout.

## Drift discipline

- The mirror is pinned to the upstream commit above. It is intentionally NOT
  auto-synced.
- When the upstream SuperTrendStrategy changes materially (config schema,
  base-class contract, factory signature), the acceptance test surfaces the
  drift as a red assertion; that is the intended failure mode.
- Bumping the pin is a deliberate maintenance step: copy the three files again
  (`strategy.py` + `__init__.py` + `config.yaml`), update the `Upstream commit`
  field above, and re-run the acceptance test to confirm the assertions still
  hold. The bump commit message should reference the upstream commit subject.
- If the vendored toolkit substrate expands (`toolkit/shared/*`) or trims,
  re-verify that this fixture's imports still resolve; a `strategy_toolkit_import_failed`
  event during load is the observable signal.

## Not a runtime import

Nothing under `src/custos/` imports from `tests/fixtures/real_supertrend/`. The
fixture is loaded via a filesystem path handed to `load_strategy_class`, not via
Python's import system.
