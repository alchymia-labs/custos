# Vendored toolkit provenance

This directory is a **vendored snapshot** of the philosophers-stone `shared/`
supertrend dependency closure plus its third-party indicator library
(`pandas_ta`). It exists because custos is an independent, audit-able
open-source repository; an external auditor cloning custos alone must have
every line of code that runs on their machine visible in this repo
(mandatory-rules §7 independent-repo self-sufficiency + non-custodial red line
that Key and strategy stay on the user's box, verifiable from a single clone).

Do **not** hand-edit files in this tree. When either upstream ships a fix that
affects the vendored subset, refresh by rerunning the sync procedure below and
updating the pinned commit here.

---

## Upstream — philosophers-stone (`shared/` subset)

- **Repo**: `git@github.com:alchymia-labs/philosophers-stone.git`
- **Upstream commit**: `fc4ab1d`
- **Vendored on**: 2026-07-09
- **Vendored by**: custos runner-executor (Plan 06 06a slice)
- **License**: philosophers-stone is a private repo owned by the same author;
  vendored under authorial permission for use inside custos.

### Vendored subset

Copied from ps `shared/` — supertrend minimal closure only.

| ps path | vendored path | reason |
|---------|---------------|--------|
| `shared/config/` | `toolkit/shared/config/` | config loader (`load_yaml_file`, `deep_merge`) used by ps `create_strategy()` |
| `shared/nautilus/` | `toolkit/shared/nautilus/` | registry + `NautilusTradingStrategy` + coordinators (RiskController activation via `RiskControlCoordinator.init_risk_controls`) |
| `shared/risk/` | `toolkit/shared/risk/` | `RiskController` platform-agnostic risk-limit enforcement (Decimal-only, red line 0.4) |
| `shared/signals/` | `toolkit/shared/signals/` | signal primitives used by supertrend |
| `shared/protocols/` | `toolkit/shared/protocols/` | protocol interfaces shared by nautilus + risk |
| `shared/indicators/` | `toolkit/shared/indicators/` | indicator primitives referenced by nautilus coordinators |
| `shared/position/` | `toolkit/shared/position/` | position sizing (`PositionSizer`) constructed by `NautilusTradingStrategy` |
| `shared/warmup/` | `toolkit/shared/warmup/` | layered warmup manager referenced by `NautilusTradingStrategy` |
| `shared/filters/` | `toolkit/shared/filters/` | filter primitives referenced by nautilus filters |

Excluded (not in the supertrend closure):

- `shared/hummingbot/` — Hummingbot engine glue, out of scope for the NT path.
- `shared/tradingview/` — TradingView integration, unrelated to runner execution.

Note on the chained-path finding: the ps repo lays its coordinators under
`shared/nautilus/coordinators/` (nested inside `nautilus/`), **not** a
top-level `shared/coordinators/` as an earlier plan draft suggested. The
`RiskControlCoordinator.init_risk_controls` mount site that activates
`_risk_controller` lives at `shared/nautilus/coordinators/risk_control.py:35-49`
in the vendored copy. Vendoring `shared/nautilus/` in full captures the
whole coordinators subtree — no separate copy needed.

---

## Curation decision

**Decision (CEO-ratified)**: keep the vendored 9-subpackage status quo — no
change to the vendored subset.

- **Option chosen**: keep status quo (the 90-file / 17,110-LOC vendored
  subset above)
- **Rationale**: the current subset (`config`, `nautilus`, `risk`,
  `signals`, `protocols`, `indicators`, `position`, `warmup`, `filters`)
  already covers the full NT-path closure for all 6 ps NT-path strategy
  dirs (`_template`, `momentum/macd_v1`, `momentum/triple_filter_momentum`,
  `portfolio/rebalancing`, `trend/adaptive_martingale`, `trend/supertrend`).
  Extending to `shared/hummingbot/` was considered and rejected: there is
  **no custos Hummingbot host implementation and no `shared.hummingbot.*`
  runtime consumer outside vendored/provenance references** — vendoring
  engine-glue with no runtime consumer would only expand audit surface
  without benefit. Trimming to a strict supertrend-only closure was also
  considered and rejected: `trend/aion_trend` and
  `market_making/adaptive_grid` are pending future strategies that would
  force a re-vendor churn on every migration if the subset were trimmed
  today.
- **Affected files**: 90 files (unchanged from this landing; see the
  "Vendored subset" table above)
- **Options considered**: keep status quo — **chosen**; extend to
  `shared/hummingbot/` (13 files / 2730 LOC) — rejected, no runtime
  consumer; trim to strict supertrend minimal closure — rejected, forces
  re-vendor churn on future strategy migrations

---

## Upstream — pandas_ta

- **Repo**: `https://github.com/wukai9203/Technical-Analysis-Indicators---Pandas.git`
  (author-maintained fork of the upstream `pandas-ta` project)
- **Upstream commit**: `a3a2228` (fix: replace numpy.NaN with numpy.nan for NumPy 2.0 compatibility)
- **Vendored on**: 2026-07-09
- **Vendored by**: custos runner-executor (Plan 06 06a slice)
- **License**: MIT (Copyright 2020 pandas-ta; see
  `toolkit/vendor/pandas_ta/LICENSE`). MIT allows verbatim vendoring with
  attribution — the LICENSE file is retained inside the vendored tree so
  attribution ships with the code an auditor reads.
- **Attribution**: the original pandas-ta project is at
  https://github.com/twopirllc/pandas-ta; the fork above is used to pick up
  a NumPy 2.0 compatibility fix ahead of upstream mainline.

### Vendored subset

Only the `pandas_ta/` package tree is vendored — tests, docs, examples,
setup.py, and Makefile from the fork are excluded because they are not needed
for runtime import and would just enlarge the audit surface.

| upstream path | vendored path | reason |
|---------------|---------------|--------|
| `pandas_ta/` | `toolkit/vendor/pandas_ta/` | technical-analysis indicator library; ps `shared/nautilus/indicators/{supertrend,adx,macd,atr,rsi}.py` all import `pandas_ta as ta` at module top |
| `LICENSE` | `toolkit/vendor/pandas_ta/LICENSE` | MIT attribution — kept inside the vendored tree so it travels with the code |

Excluded from the fork (not needed at runtime, kept out of the audit surface):

- `tests/`, `docs/`, `examples/`, `data/`, `images/` — non-runtime.
- `setup.py`, `_config.yml`, `Makefile`, `README.md`, `CODE_OF_CONDUCT.md` —
  packaging / project meta.

---

## Layout after vendoring

```
toolkit/
├── TOOLKIT_PROVENANCE.md   # this file
├── __init__.py             # bootstraps sys.path so `shared.*` and `pandas_ta` resolve
├── shared/                 # verbatim ps snapshot (subset above)
│   ├── config/
│   ├── nautilus/           # includes coordinators/ (chained under nautilus, not top-level)
│   ├── risk/
│   ├── signals/
│   ├── protocols/
│   ├── indicators/
│   ├── position/
│   ├── warmup/
│   └── filters/
└── vendor/
    └── pandas_ta/          # verbatim MIT-licensed indicator library snapshot
        ├── LICENSE
        └── ... (indicator submodules)
```

## Import resolution

`toolkit/__init__.py` runs on package import and prepends two paths to
`sys.path`:

1. `toolkit/` itself — makes `from shared.<pkg> import ...` resolve into
   `toolkit/shared/<pkg>`.
2. `toolkit/vendor/` — makes `import pandas_ta as ta` resolve into
   `toolkit/vendor/pandas_ta/`.

Both `_prepend_if_missing()` calls are idempotent — importing the toolkit
package twice does not duplicate `sys.path` entries. Bare-import bootstrap was
chosen over a rewrite so the vendored ps and pandas_ta code stay byte-identical
to their upstreams; the alternative (patching every `import pandas_ta` /
`from shared` inside the vendored trees) would multiply the sync-maintenance
burden and hide upstream drift.

## Sync procedure

When either upstream ships a change that touches its vendored subset:

**ps `shared/`** —

1. `cd /path/to/philosophers-stone && git log --oneline -5 shared/` — pick the
   upstream commit to sync to.
2. From custos root:
   ```sh
   PS_ROOT=/path/to/philosophers-stone
   TK=src/custos/engines/nautilus/toolkit/shared
   for pkg in config nautilus risk signals protocols indicators position warmup filters; do
     rm -rf "$TK/$pkg"
     cp -r "$PS_ROOT/shared/$pkg" "$TK/$pkg"
   done
   find "$TK" -name __pycache__ -type d -exec rm -rf {} +
   find "$TK" -name '.ruff_cache' -type d -exec rm -rf {} +
   ```
3. Update the **ps Upstream commit** and **Vendored on** fields above.

**pandas_ta** —

1. `git clone --depth 1 https://github.com/wukai9203/Technical-Analysis-Indicators---Pandas.git /tmp/pandas_ta_check`
   then `git -C /tmp/pandas_ta_check log --oneline -1` to pick the commit.
2. From custos root:
   ```sh
   TK=src/custos/engines/nautilus/toolkit/vendor/pandas_ta
   rm -rf "$TK"
   mkdir -p "$TK"
   cp -r /tmp/pandas_ta_check/pandas_ta/* "$TK/"
   cp /tmp/pandas_ta_check/LICENSE "$TK/LICENSE"
   find "$TK" -name __pycache__ -type d -exec rm -rf {} +
   ```
3. Update the **pandas_ta Upstream commit** and **Vendored on** fields above.

**After either sync** —

4. Run `make verify` and `make verify-nt` — the toolkit sync must not regress
   any red-line grep or contract test.
5. Commit both the vendored diff and the provenance bump in one atomic commit
   (`chore(custos): sync vendored toolkit — ps <sha> / pandas_ta <sha>`).

## Sync-check

`Makefile` exposes a `toolkit-sync-check` target that computes a real diff
against a local upstream checkout:

```sh
PS_ROOT=/path/to/philosophers-stone make toolkit-sync-check
```

`PS_ROOT` is required (fails fast with a clear message if unset). It reads
the pinned ps commit above, diffs it against `PS_ROOT`'s current HEAD under
`shared/`, and prints the new-commit list plus a diff-stat. Exit 0 means
zero drift; a non-zero exit means drift was detected. `PANDAS_TA_ROOT` is
optional — the pandas_ta upstream drifts far less often, so the check
gracefully prints "manual check required" when it is unset rather than
failing.

**Cadence**: weekly diff review — run manually or via cron/CI weekly, and
append the result to the drift audit log below. Drift found → follow the
sync procedure above.

## Drift audit log

Append-only log of `toolkit-sync-check` runs. Each entry records:
`{ran_at, ps_upstream_head, ps_drift, pandas_ta_upstream_head, pandas_ta_drift, run_by}`.

| ran_at | ps_upstream_head | ps_drift | pandas_ta_upstream_head | pandas_ta_drift | run_by |
|--------|-------------------|----------|--------------------------|-------------------|--------|
| 2026-07-09 | `34b73a2` | no | N/A (upstream not local) | N/A | toolkit curation landing |

## pandas_ta governance

**Decision (CEO-ratified)**: keep the vendored fork status quo, and
formalize the trigger criteria for a future PyPI-package escalation.

- **Status quo**: pandas_ta stays vendored as a fork snapshot (149 files
  at the pinned commit above, LICENSE retained inside the vendored tree).
  Audit surface is known and no external supply-chain surface is added by
  switching to a PyPI dependency.
- **Trigger criteria** for revisiting PyPI-package escalation (any single
  trigger firing → CEO revisits via a new dedicated plan):
  1. More than 2 upstream drift events/quarter that provenance sync
     struggles to keep up with.
  2. Other non-Guild projects need reuse of the fork.
  3. custos Rust migration starts and needs the toolkit as a decoupled
     package.

See the prior `DEV-06-DP1-DEFERRED-C-OPTION` memo (Plan 06) for the
historical context this formalizes.

## Why vendored (option A + B, not submodule / not PyPI)

- Submodule breaks the independent-clone audit invariant — a lone
  `git clone custos` cannot reach the ps repo.
- PyPI package introduces a supply-chain surface auditors have to cross the
  repo boundary to verify — and `pandas_ta` is not on PyPI in the fork's
  patched form.
- Vendoring pandas_ta separately (option A applied to ps + option B applied
  to pandas_ta) trades update-fastness for audit-ability. That trade is
  deliberate; see `.forge/plans/2026-07/06-ps-supertrend-migration.md`
  §DEV-06-SHARED-PACKAGING-CHOICE + §DEV-06-06A-VENDOR-PANDAS-TA-DECISION-B.
