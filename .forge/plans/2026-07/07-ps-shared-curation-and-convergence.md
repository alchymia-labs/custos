# 07 — ps shared curation + convergence: custos-as-shared-authority landing + sync discipline real implementation + ps convergence path

> **Status**: 🔲 Todo (Phase 1 draft 2026-07-09; L1 codex REQUEST_CHANGES fix cycle 2026-07-09; plan-drafter-07, opus-4-7[1m])
> **Created**: 2026-07-09 (post-Plan 06 06a squash-merge `306b9e5`)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Phase 1 draft + L1 fix cycle applied; L2 codex re-review recommended before `/forge:execute` or execute-team
> **Depends on**: Plan 06 06a squash-merge (main HEAD `306b9e5`) — `src/custos/engines/nautilus/toolkit/` already vendored (9 ps subpackages @ `fc4ab1d` + pandas_ta @ fork `a3a2228`, byte-identical snapshot per evidence-scout §2.1); `TOOLKIT_PROVENANCE.md` already landed with sync-procedure prose; `Makefile toolkit-sync-check` stub already landed
> **Blocks**: Plan 08 (Plan 06 remainder Track 5 e2e + Track 6 sidecar retirement docs) — Plan 08 T5.1 e2e coverage scope depends on Plan 07 curation-scope decision (DP1); Plan 08 T6.1 sidecar retirement doc scope depends on Plan 07 crucible Docker preservation window statement (DP2)
> **multi_session_scope**: **false** — scope is architectural/documentation/sync-check-real-implementation, not code-heavy: 5 tracks, 9 tasks, 9 NEW contract tests, one Makefile target upgrade from stub to real diff, one provenance-schema evolution. Fits a single execute-team session

---

## Origin

Plan 06 06a slice landed the mechanical vendoring (`306b9e5`): 9 ps `shared/` subpackages verbatim-copied to `src/custos/engines/nautilus/toolkit/shared/` at ps commit `fc4ab1d`, plus pandas_ta at fork commit `a3a2228` under MIT license. Plan 06 §DEV-06-06A-REVERSE-DEPENDENCY-STRATEGY-D (amended D→D') declared the final architectural end-state:

> Plan 06 phase short-term keeps ps `shared/`; **Plan 07 delivers the architectural end-state — custos toolkit is the shared body-of-truth authority, ps converges into a strategy-research copy (team-experimental indicators / new-signal code, migrated back to custos once stable)**.

`.forge/README.md:59` execution-order suggestion pins Plan 07 = "ps shared curation migration — land under `custos.engines.nautilus.toolkit.*`" — 06a landed the location and mechanics, Plan 07 lands the **decision** (curation scope + convergence criteria + sync discipline).

Evidence-scout §4.2 surfaced a **critical architectural constraint not anticipated in the dispatch prompt**: `the-crucible/crucible_engine/*.py` has **0 direct `from shared` imports** (pure HTTP/Docker orchestrator, `crucible_engine/supervisor.py:32` `import httpx` + `:362` `sidecar_url = f"http://{container_ip}:8080"`), **but** the ps repo's own Docker build packages `shared/` into the production runtime container images that `the-crucible` supervises: scout §4.2 anchors `philosophers-stone/deploy/nautilus/Dockerfile:1-8` header comment ("runtime base: NT + deps + shared + sidecar") + `:35 COPY shared/README.md /tmp/deps/shared/README.md`; `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared`. Any Plan 07 "ps convergence" that trims, moves, or deletes parts of ps `shared/` without preserving the Docker-buildable closure would break `the-crucible`'s currently-running production strategy containers — independent of what custos vendors. This escalates the packet §3 goal's "no destructive delete" caveat from a caution to a **hard constraint (DP2 rewrites around it)**.

---

## Context

### Contract Verification Gate (Step 1.5)

> **as-of evidence-scout Foundation Scan** (`.forge/handoff/2026-07/evidence-scout-07-08.md`, 230 lines) run 2026-07-09 with 3 rounds (round 1 direct anchors + round 2 import-graph closure + round 3 cascade into `the-crucible` repo). custos main HEAD `306b9e5` (Plan 06 06a squash) + hook infra `5c01cdb` + orchestration `55782d0`. ps `develop` HEAD `34b73a2`. Table 1 below quotes scout anchors verbatim; Table 2 lists additional drafter verification anchors (not scout-verbatim), kept separate per lesson C2 zero-paraphrase discipline. This drafter did no independent grep of source repos beyond `tests/` for lesson #25 test-name uniqueness verification.

#### Table 1 — Scout-verbatim anchors (source of truth: evidence-scout report)

| Referenced contract | file:line (scout anchor) | Use |
|---------------------|--------------------------|-----|
| 9 subpackages already vendored (byte-identical) | scout §1.1 table + §2.1 table — 90 files / 17,110 LOC verbatim match | T1.1 baseline (curation "keep" baseline) |
| Zero drift `fc4ab1d..34b73a2` under `shared/` | scout §3 — `git diff --stat fc4ab1d..34b73a2 -- shared/` → empty; 2 post-pin ps commits touch only `tests/strategies/test_supertrend_risk_controller_enabled.py` + `trend/supertrend/config.yaml` (Plan 06 Track 2 products) | T2.1 sync-check zero-drift-current baseline |
| ps `shared/hummingbot/` = 13 files / 2730 LOC, no custos runtime consumer outside vendored/provenance references | scout §1.3 — "not consumed by anything in custos (custos is NT-only, no Hummingbot host exists in custos source)". **See scout report §11 errata (2026-07-09) for the narrower framing corrected by codex L1 CR-8**: `hummingbot` string does appear at `src/custos/core/engine_protocol.py:3` docstring + toolkit vendored `shared/config/validator.py` + `shared/nautilus/config/platforms.py`, but no custos Hummingbot host implementation and no runtime consumer of `shared.hummingbot.*` outside those references | DP1 option (b) refuted (no custos runtime consumer of shared.hummingbot = no gain from expansion) |
| ps `shared/tradingview/` = 0 `.py` (README + `.pine`) | scout §1.1 last row — "non-runtime artifact, correctly excluded" | DP1 non-candidate |
| crucible Docker bundling of ps `shared/` + `deploy/` | scout §4.2 — `philosophers-stone/deploy/nautilus/Dockerfile:1-8` header comment ("runtime base: NT + deps + shared + sidecar") + `:35 COPY shared/README.md /tmp/deps/shared/README.md`; `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared` | DP2 hard constraint (crucible Docker preservation window) |
| crucible has 0 direct `shared.*` imports | scout §4.2 — "`grep -rn -E "(from shared\|import shared)" crucible_engine --include='*.py'` → 0 hits"; HTTP-only via `httpx.AsyncClient` to `sidecar_url` | DP2 rationale — no code-level coupling, only container-image-level bundling |
| ps non-test consumers of `shared/` | scout §1.2 — 6 NT-path strategy dirs (`_template`, `macd_v1`, `triple_filter_momentum`, `portfolio/rebalancing`, `adaptive_martingale`, `supertrend`) + 3 deploy entrypoints + 1 backtest script; 3 Hummingbot-path strategy dirs (`_template`, `macd_v1`, `supertrend`) | Track 3 convergence-documentation impact scope |
| ps `develop` HEAD `34b73a2` | scout header + §3 | Sync-check as-of anchor |
| custos main HEAD `306b9e5` | scout §3 last paragraph | Plan-07 as-of anchor |
| ps `aion_trend` + `market_making/adaptive_grid` not yet consumers | scout §1.2 — "`aion_trend` has only `design.md` + `insight/notes.md`, no `refinement/` yet — not a consumer"; `market_making/adaptive_grid/refinement/` = empty (0 files) | DP1 option (c) risk analysis — future strategies may need `shared.nautilus.indicators.*` that trim would remove |

#### Table 2 — Additional drafter verification anchors (not scout-verbatim)

> Kept in a separate table per codex L1 CR-2 fix (lesson C2 zero-paraphrase). Executor Foundation Scan re-verifies these before Track start.

| Referenced contract | file:line (drafter anchor) | Use |
|---------------------|----------------------------|-----|
| Existing `TOOLKIT_PROVENANCE.md` content (Plan 06 06a landed) | drafter Read (`src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md:1-191`) — 191 lines, sections: Upstream ps + subset table + Upstream pandas_ta + Layout + Import resolution + Sync procedure + Sync-check stub + "Why vendored" | T2.2 provenance-schema evolution baseline |
| Existing `Makefile toolkit-sync-check` = stub | drafter Read (`Makefile:toolkit-sync-check`) — 4-line stub: `awk` grep of provenance file + `echo` hint text; no actual diff implementation | T2.2 stub → real upgrade target |
| Existing `docs/design/nautilus_host.md` has no sync/toolkit/drift sections | drafter grep `-n "sync\|toolkit-sync\|drift" docs/design/nautilus_host.md` → 0 hits within relevant scope (matches only pre-existing `NoopHost` / capability-contract table rows) | T3.2 sync-discipline docs section is genuinely NEW |
| ps `aion_trend` + `market_making/adaptive_grid` `refinement/` re-check | drafter re-verified 2026-07-09 via `find <ps>/trend/aion_trend/refinement -type f` (no such path) + `find <ps>/market_making/adaptive_grid/refinement -type f` (empty) | Complements scout §1.2 anchor above for DP1 option (c) risk analysis |

### plan-to-plan references (Step 1.5)

| plan-id | Status | Referenced product | Verification |
|---------|--------|--------------------|--------------|
| 05 | ✅ landed via Plan 06 06a inheritance | `src/custos/engines/nautilus/*` directory shape | Plan 05 close-out (post-06a squash) — Plan 07 file paths assume this shape |
| 06 06a slice | ✅ landed at `306b9e5` (squash-merge) | `src/custos/engines/nautilus/toolkit/{shared/,vendor/pandas_ta/,__init__.py,TOOLKIT_PROVENANCE.md}` + `Makefile toolkit-sync-check` stub | drafter Read + Bash verify (all present) |
| 06 remainder → **Plan 08** | 🔲 not-yet-started (packet §4) | Track 5 e2e + Track 6 sidecar retirement docs | Plan 07 must not block Plan 08 start; Plan 08 START gate = Plan 07 landing |

### As-of anchors (lesson #14/#33 four-dimensional scan)

- **Spatial** (lesson #14): scout §1.1 + §2.1 covered `shared/` full closure + custos toolkit current state; no additional file-system scan needed for the drafting session
- **Temporal** (lesson #33): scout run 2026-07-09; custos main HEAD `306b9e5`; ps `develop` HEAD `34b73a2`; upstream ps commit pinned in provenance = `fc4ab1d`; zero drift `fc4ab1d..34b73a2` under `shared/`
- **Namespace** (lesson #30): no migration DDL in scope (Plan 07 is docs + Makefile + toolkit-metadata + contract tests; no schema)
- **Layered impact** (lesson #33b): DP2 crucible Docker bundling is a **layer-3 dependency** discovered only by reading Dockerfiles (not by grepping `.py` imports) — evidence-scout Round 3 cascade chase surfaced it beyond the dispatch-prompt hint set

---

## Goal

Plan 07 close-out delivers:

1. **Architectural end-state landing**: custos toolkit is declared and documented as the shared body-of-truth authority (audit-able from a single custos clone per mandatory-rules §7); ps `shared/` is documented as a research-side copy (team-experimental indicators / new-signal code) with a stability-based flow-back path to custos
2. **Curation scope decision** (DP1 — drafter recommends; CEO pending): keep 06a full-9-subpackage vendor / extend / trim — decision materialized in `TOOLKIT_PROVENANCE.md` with rationale + affected-files audit
3. **ps convergence path** (DP2 — drafter recommends; CEO pending): criteria for "which ps `shared/` code stays for research vs migrates to custos toolkit" + explicit **crucible Docker preservation window** hard constraint (ps repo MUST keep Docker-buildable `shared/` + `deploy/` while crucible production containers depend on them; no destructive delete under any option)
4. **Sync discipline real implementation**: `Makefile toolkit-sync-check` stub → real diff (detects upstream `shared/` drift + pandas_ta drift + reports new commits); provenance-file schema evolves to record last-checked-SHA + drift-audit log; sync-check triggering cadence decision (DP3)
5. **pandas_ta governance formalization** (DP4): keep vendored fork status quo vs formalize DEV-06-DP1-DEFERRED-C-OPTION trigger conditions for future PyPI-package escalation

**Red line vision ≠ delivery statement (lesson #40 / custos C40)**: Plan 07 delivers "architectural landing + curation-decision materialization + sync-check real diff"; per-strategy drawdown breaker (red line 0.3 layer 1, delivered by Plan 06) and per-runner cap (red line 0.3 layer 2, deferred to Plan 04) are unchanged.

---

## Architecture

### custos-as-shared-authority + ps-as-research-copy end-state

```
┌────────────────────────────────────────────────────────────────────────┐
│                 custos (independent audit-able repo)                    │
│                                                                         │
│  src/custos/engines/nautilus/toolkit/           ← authority body-of-   │
│    shared/    (9 subpackages, 90 files, 17,110    truth for shared/    │
│                LOC — verbatim ps snapshot @ SHA)                        │
│    vendor/pandas_ta/  (149 files @ fork SHA)                            │
│    TOOLKIT_PROVENANCE.md  (SHA + curation decision +                    │
│                            sync log + drift audit)                       │
│    ↑ single-clone audit surface (mandatory-rules §7)                    │
│                                                                         │
│  Makefile toolkit-sync-check                                            │
│    ↑ real diff vs ps upstream + pandas_ta upstream                      │
└────────────────────────────────────────────────────────────────────────┘
                            ↑
                            │ periodic sync
                            │ (cadence per DP3)
                            │
┌────────────────────────────────────────────────────────────────────────┐
│         philosophers-stone (research copy, not authority)              │
│                                                                         │
│  shared/    ← research copy: team-experimental indicators, new-signal  │
│              code, unfinished refinement; STABLE code migrates back    │
│              to custos toolkit via sync flow                            │
│                                                                         │
│  deploy/nautilus/Dockerfile  ─┐                                         │
│  deploy/hummingbot/Dockerfile.image ─┤ COPY shared/ into runtime image  │
│                                                                         │
│  ↓ crucible Docker preservation window (HARD CONSTRAINT, DP2):         │
│    ps repo MUST keep Docker-buildable shared/ + deploy/ so long as     │
│    the-crucible production containers depend on them.                  │
│    NO destructive delete of ps shared/ under any option.               │
└────────────────────────────────────────────────────────────────────────┘
                            ↑
                            │ Docker image build (bundles ps shared/)
                            │
┌────────────────────────────────────────────────────────────────────────┐
│                    the-crucible (production supervisor)                 │
│                                                                         │
│  crucible_engine/supervisor.py:32 import httpx                          │
│  crucible_engine/*.py — 0 direct `from shared` imports                 │
│  Talks to production containers via HTTP: sidecar_url = f"http://..."  │
│  Containers are built from ps deploy/ Dockerfiles that COPY shared/.   │
│                                                                         │
│  Consumers of ps shared/ = the containers crucible supervises,          │
│  NOT the crucible_engine Python code itself.                            │
└────────────────────────────────────────────────────────────────────────┘
```

### Curation scope decision (DP1) framing

Post-06a state: **9 subpackages vendored** (config / nautilus / risk / signals / protocols / indicators / position / warmup / filters — total 90 files / 17,110 LOC). Two candidates NOT vendored: `shared/hummingbot/` (13 files / 2730 LOC, NT-path excluded — zero custos consumer per scout §1.3) + `shared/tradingview/` (0 `.py`, non-runtime — correctly excluded).

Three curation options (DP1 — drafter recommends; CEO pending):

- **(a) Keep 06a full-9 vendor status quo** (drafter recommend): 90-file vendored subset covers the full NT-path closure for all 6 ps NT-path strategy dirs (supertrend, macd_v1, triple_filter_momentum, portfolio/rebalancing, adaptive_martingale, _template). Future ps strategies flowing to custos need no re-vendor churn. Cost: 17,110 LOC audit surface (already landed and audited by 06a red-line 0.4 grep gate `test_vendored_toolkit_no_new_float_money_math`).
- **(b) Extend to `shared/hummingbot/`**: 13-file / 2730-LOC expansion. **Rejected** by drafter — scout §1.3 confirms no custos Hummingbot host implementation and no `shared.hummingbot.*` runtime consumer outside vendored/provenance references (the `hummingbot` string does appear at `src/custos/core/engine_protocol.py:3` docstring naming the class of engines the protocol targets, plus toolkit vendored `shared/config/validator.py` + `shared/nautilus/config/platforms.py` — none of these consume `shared.hummingbot.*` as a Hummingbot host). Vendoring engine-glue with no runtime consumer expands audit surface without benefit. Only worth revisiting if a future custos Hummingbot host emerges (see Plan 08+ engine-plugin roadmap in Plan 05 "Next steps").
- **(c) Trim to strict supertrend minimal closure**: reduce to `config` + `signals` + `risk` + `shared/nautilus/{coordinators/risk_control.py, indicators/supertrend.py, trading_strategy.py}` + narrow supporting files. **Risk**: ps `aion_trend/insight/notes.md` and `market_making/adaptive_grid/design.md` exist as future strategies (scout §1.2 confirmed non-consumers today). Trimming today forces a re-vendor churn for every future strategy migration; the 06a red-line 0.4 grep gate already covers the current 90-file surface.

**drafter recommendation: (a)** — CEO pending; status quo minimizes churn while awaiting future strategy migrations, and the current audit-surface is already gated.

### ps convergence + crucible Docker preservation window (DP2) framing

The end-state (`DEV-06-06A-REVERSE-DEPENDENCY-STRATEGY-D'`) is "custos toolkit = authority; ps = research copy". Naive implementation would delete ps `shared/` post-migration. But scout §4.2 established a **hard constraint** (scout-verbatim anchors only per CR-2 discipline):

- `crucible_engine` has 0 direct `shared.*` imports (pure HTTP orchestrator via `httpx` to `sidecar_url`)
- `philosophers-stone/deploy/nautilus/Dockerfile:1-8` header comment declares "runtime base: NT + deps + shared + sidecar" + `:35 COPY shared/README.md /tmp/deps/shared/README.md` inside the dependency-install stage; `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared` bundle ps `shared/` **directly into production runtime container images**
- These images are what `the-crucible` supervises today. Deleting or trimming ps `shared/` would break running production strategy containers, **independent of custos vendoring state**

Three options (DP2 — drafter recommends; CEO pending):

- **(a) Short-term keep ps Docker-buildable `shared/` + `deploy/` until crucible→custos runtime migration** (drafter recommend, hard-constraint-derived): ps `shared/` continues to exist in ps repo as-is; convergence documentation adds deprecation notices in ps README + individual strategy README pointing at custos toolkit as the authority; no ps files are deleted or moved; sync-check flows stable code from ps `shared/` → custos toolkit; end-state (crucible migrated to consume custos runtime images instead of ps `deploy/` images) unblocks eventual ps convergence to research-only copy. Timeline: multi-quarter; explicitly outside Plan 07 scope.
- **(b) Immediately converge ps to research-only copy**: delete/move ps `shared/`. **Rejected by hard constraint** — would break `the-crucible` production containers immediately (Dockerfile `COPY shared` would fail).
- **(c) Add "crucible→custos runtime migration plan" as Plan 07 blocker**: expands Plan 07 scope to include cross-repo (custos + crucible + ps) coordination. Rejected as scope creep — that migration warrants its own dedicated plan (candidate future plan `crucible-runtime-migration`); Plan 07 delivers what's audit-able and CEO-ratifiable today without cross-repo coordination cost.

**drafter recommendation: (a)** — CEO pending; Plan 07 close-out note lists "crucible→custos runtime migration" as a future candidate plan (not a Plan 07 blocker).

### Sync discipline real implementation (DP3) framing

Post-06a state: `Makefile toolkit-sync-check` = 4-line stub (grep provenance + echo hint text). Real implementation upgrades to:

1. Read pinned ps SHA + pinned pandas_ta SHA from `TOOLKIT_PROVENANCE.md`
2. Discover ps upstream HEAD SHA (from `PS_ROOT` env var pointing at ps checkout; fail-fast if unset with clear message; **non-destructive**: does not clone or modify ps checkout)
3. Discover pandas_ta upstream HEAD (from optional `PANDAS_TA_ROOT` env var; if unset, print "manual check required" and skip pandas_ta check — pandas_ta upstream may not always be locally available)
4. Compute `git diff --stat <pinned>..<upstream_HEAD> -- shared/` for ps; print new commit range + diff-stat under `shared/` (files-changed count + insertions/deletions)
5. Exit 0 if zero-drift, exit 1 if drift detected, print structured output for CI consumption
6. Provenance file gains a new "Drift audit log" section: each sync-check run records `{ran_at: <date>, ps_upstream_head: <SHA>, ps_drift: <yes|no|<n>-files>, pandas_ta_upstream_head: <SHA or "N/A">, pandas_ta_drift: <yes|no|N/A>, run_by: <who>}` (append-only log)

Three cadence options (DP3 — drafter recommends; CEO pending):

- **(a) Auto-alert on every ps commit**: requires webhook or polling infra outside custos. Rejected as scope creep for Plan 07.
- **(b) Weekly diff review** (drafter recommend): manageable rhythm; sync-check run manually or via cron/CI weekly; results appended to provenance drift-audit log; drift → trigger sync procedure in TOOLKIT_PROVENANCE.md
- **(c) Manual trigger only**: pure on-demand; no rhythm commitment. Risk: drift accumulates silently.

**drafter recommendation: (b)** — CEO pending; weekly review is enforceable via CI or ops runbook (custos has no CI today per scout §9; enforcement mechanism can be a docs-recorded runbook step until Plan 09 lands CI).

### pandas_ta governance (DP4) framing

Post-06a: pandas_ta vendored at fork SHA `a3a2228` under MIT license (LICENSE file retained in vendored tree). DEV-06-DP1-DEFERRED-C-OPTION memo (Plan 06) records "future PyPI-package escalation" as candidate if trigger conditions met. Plan 07 formalizes:

- **(a) Keep vendored fork status quo** (drafter recommend): 149 files vendored + LICENSE retained; audit surface known; no external supply-chain surface added
- **(b) Formalize DEV-06-DP1-DEFERRED-C-OPTION trigger conditions** with explicit criteria: (i) >2 upstream drift events/quarter that provenance sync struggles to keep up with; (ii) other non-Guild projects need reuse of the fork; (iii) custos Rust migration starts and needs toolkit as decoupled package. Any single trigger firing → CEO revisits pkg escalation via new dedicated plan

drafter recommends **(a) status quo + (b) formalize criteria in provenance-file addendum** — the two are complementary, not alternatives. CEO pending.

---

## Key Design Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Curation scope**: keep 9 vendored / extend hummingbot / trim to supertrend? | **(a) Keep 06a full-9-subpackage vendor status quo** (DP1, drafter recommends; CEO pending) | No custos Hummingbot host implementation / no `shared.hummingbot.*` runtime consumer outside vendored/provenance references (scout §1.3 + CR-8 errata); trimming forces re-vendor churn on future strategy migration (aion_trend / adaptive_grid pending); red-line 0.4 gate already covers current surface |
| **ps convergence timing** vs crucible Docker preservation? | **(a) Short-term keep ps Docker-buildable `shared/` + `deploy/`** (DP2, drafter recommends; CEO pending); crucible→custos runtime migration = future candidate plan, not Plan 07 blocker | scout §4.2 hard constraint — crucible production containers built from ps `deploy/` Dockerfiles; destructive convergence breaks production |
| **Sync-check cadence** | **(b) Weekly diff review** (DP3, drafter recommends; CEO pending); enforced via runbook (docs) until Plan 09 CI lands | Manageable rhythm; auto-alert needs infra outside Plan 07; manual-only risks silent drift |
| **pandas_ta governance** | **(a) Keep vendored fork + (b) Formalize DEV-06-DP1-DEFERRED-C-OPTION trigger criteria** (DP4, drafter recommends both; CEO pending) | Status quo + explicit escalation criteria = layered discipline; complementary not alternative |
| **`toolkit-sync-check` scope**: ps only / ps + pandas_ta / all-in-one? | **Both** — check ps `shared/` drift (mandatory, `PS_ROOT` required) + pandas_ta drift (optional, `PANDAS_TA_ROOT` env; skips gracefully if unset) | ps is the primary drift risk (weekly commits); pandas_ta drifts rarely (fork was created for NumPy 2.0 compatibility, upstream rebase infrequent) |
| **Provenance schema evolution**: new sections vs replacement? | **Additive** — add "Curation decision" section + "Drift audit log" appendix + "pandas_ta governance" subsection; existing sync-procedure prose unchanged | Preserves 06a-landed content; append-only history matches red-line "zero silence" discipline |
| **Convergence documentation location**: custos-side / ps-side / both? | **Both** — custos `docs/design/nautilus_host.md` §"Toolkit sync discipline" (authority-side view); ps README + strategy READMEs get deprecation notice pointing at custos toolkit (research-side view) | Bilateral documentation matches bilateral repo boundary; single-side note would leave the other side ambiguous |
| **crucible Docker preservation window statement**: docs / DEV entry / both? | **Both** — docs statement in `nautilus_host.md` §"crucible Docker preservation window" + `DEV-07-CRUCIBLE-DOCKER-PRESERVATION-HARD-CONSTRAINT` deviation entry (link to future crucible-runtime-migration candidate plan) | Docs = permanent contract; DEV = decision provenance |

---

## Capability Hosting Decision

Not applicable — Plan 07 does not introduce new capability hosts (no new skill / hook / plan-mode / CLAUDE.md capability carrier). Curation-decision materialization goes into `TOOLKIT_PROVENANCE.md` (existing carrier), sync-check real implementation upgrades an existing Makefile target, convergence docs land in existing design documents.

---

## File Inventory

> Status markings: **create** / **modify** / **delete** (none in this plan — hard constraint per DP2). `as-of (test -f)` column = executor Foundation Scan `test -f` expectation. All paths English-primary per Language Policy (mandatory-rules §7 + `.claude/rules/code-style.md` §language constraint).

### A. custos source (modify only — no source-code changes; toolkit vendored subset is unchanged from 06a per DP1 = "keep status quo")

| File | Status | as-of (`test -f`) | Track/Task | Description |
|------|--------|--------------|-----------|-------------|
| (no source-code files modified) | — | — | — | Plan 07 does not touch `src/custos/**/*.py` — the vendored subset is already correct per DP1 recommend; Plan 07 delivers decisions + docs + Makefile + tests |

### B. custos tests (create — under `tests/engines/nautilus/` per Plan 05 T8.2)

| File | Status | as-of (`test -f`) | Track/Task | Description |
|------|--------|--------------|-----------|-------------|
| `tests/engines/nautilus/test_toolkit_sync_check.py` | create | absent (grep verified) | T2.1 + T2.2 + T2.3 | Contract tests: (1) `test_toolkit_sync_check_zero_drift_current` — as-of `34b73a2`, sync-check exits 0; (2) `test_toolkit_sync_check_detects_upstream_drift` — synthetic drift fixture (later-than-pinned SHA in `PS_ROOT`) exits 1 with structured output; (3) `test_toolkit_sync_check_reports_new_ps_commits` — output format includes new commit count + diff-stat under `shared/`; (4) **`test_toolkit_sync_check_requires_ps_root`** (CR-5: dedicated fail-fast test per lesson #22/#28 independent-testability) — runs target with `PS_ROOT` unset; asserts non-zero exit + clear error message on stderr referencing `PS_ROOT` |
| `tests/engines/nautilus/test_toolkit_provenance_schema.py` | create | absent (grep verified) | T1.2 + T2.3 | Contract tests: (1) `test_toolkit_provenance_pinned_commit_valid` — pinned ps commit + pandas_ta commit are resolvable in respective upstream repos (if `PS_ROOT` / `PANDAS_TA_ROOT` set; else skip with explicit reason); (2) `test_toolkit_provenance_curation_decision_recorded` — provenance file contains a "Curation decision" section with the CEO-ratified DP1 option + rationale + affected-files list; (3) `test_toolkit_provenance_drift_audit_log_appendable` — drift-audit log section exists and accepts new entries without corrupting prior entries |
| `tests/engines/nautilus/test_convergence_docs.py` | create | absent (grep verified) | T3.1 + T3.2 | Contract tests: (1) `test_ps_convergence_documentation_no_destructive_delete` — `docs/design/nautilus_host.md` §"Toolkit sync discipline" section explicitly declares "no destructive delete of ps `shared/`" and references DP2 hard constraint; (2) `test_crucible_docker_preservation_window_documented` — same doc section names the hard constraint + Dockerfile-line evidence + points at future candidate crucible-runtime-migration plan |

### C. ps-side changes (research-side deprecation notices, non-destructive)

| File | Status | as-of (`test -f`) | Track/Task | Description |
|------|--------|--------------|-----------|-------------|
| `philosophers-stone/shared/README.md` | modify | exists (per scout §1.1 mention of `shared/README.md`) | T3.1 | Add "custos-as-authority notice" — this ps `shared/` directory is a research copy; custos `src/custos/engines/nautilus/toolkit/shared/` is the body-of-truth authority; stable code flows ps→custos via sync-check (`Makefile toolkit-sync-check`); crucible Docker preservation window keeps ps `shared/` + `deploy/` alive for supervised container images; no destructive delete under any Plan 07 option |

### D. Docs / configs (modify / create)

| File | Status | as-of (`test -f`) | Track/Task | Description |
|------|--------|--------------|-----------|-------------|
| `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` | modify | exists (191 lines, drafter Read) | T1.2 + T2.3 + T4.1 | Add "Curation decision" section (CEO-ratified DP1 option + rationale + affected-files) + "Drift audit log" appendix (append-only entries: `{ran_at, ps_upstream_head, ps_drift, pandas_ta_upstream_head, pandas_ta_drift, run_by}`) + "pandas_ta governance" subsection (CEO-ratified DP4 status quo + three trigger criteria for future PyPI escalation) |
| `Makefile` | modify | exists (drafter Read, `toolkit-sync-check` = 4-line stub) | T2.2 | Upgrade `toolkit-sync-check` target: stub → real diff. Reads pinned SHAs from provenance file, requires `PS_ROOT` env (fail-fast with clear message if unset), optional `PANDAS_TA_ROOT`. Prints new commit range + diff-stat under `shared/` for ps; skips pandas_ta gracefully if `PANDAS_TA_ROOT` unset. Exit 0 = zero drift; exit 1 = drift detected |
| `docs/design/nautilus_host.md` | modify | exists (drafter grep confirms no existing sync section) | T3.2 | Add "Toolkit sync discipline" section: (a) authority declaration (custos toolkit = shared body-of-truth); (b) sync-check mechanism (Makefile target + weekly cadence per DP3); (c) crucible Docker preservation window hard constraint (scout §4.2 evidence + Dockerfile lines + points at future crucible-runtime-migration candidate); (d) convergence flow (research code flows back ps→custos as it stabilizes); (e) no-destructive-delete guarantee |
| `.forge/README.md` | modify | exists | T4.1 | Close-out — index Plan 07 Status → ✅; add DP1/DP2/DP3/DP4 CEO decisions to close-out record |

> **Cross-repo change discipline (mandatory-rules §6)**: Plan 07 touches custos + ps. custos commits go on `main` (Plan 07 branch); ps commit is a single docs-only edit on `philosophers-stone` `develop`. Two independent commits, `git add <specific-file>` only, no `git add .` / `-A`. Non-atomic across repos — sync-check contract tests are the integration gate. See `DEV-07-CROSS-REPO-COMMIT-CHOREOGRAPHY` in Deviations.

---

## Tasks

> **TDD rhythm**: each Task writes failing assertion (red) → minimal implementation → green → `make verify` clean (custos-side atomicity) → commit. Source-code comments must not contain plan/task/lesson tracking numbers (lesson #15 — use semantic reference: "shared authority landing" not "Plan 07 T1.2"). **Executor Foundation Scan before Task start** (lesson #14/#30/#33): confirm as-of `main` SHA (`306b9e5` + any later commits) + `test -f` verify File Inventory + re-verify test-name uniqueness under `tests/` (`grep -rn "def test_X" tests/` for each NEW test; lesson #25 gate at close-out).

### Track 1 — Curation scope decision landing (DP1 materialization)

#### Task T1.1: Baseline confirmation — currently-vendored subset matches 06a claim, zero drift
**Files**: none (verification-only task; produces DEV entry if drift detected)

- **Step 1 (red)**: Run `find src/custos/engines/nautilus/toolkit/shared -type f -name '*.py' | wc -l` — assert result matches 06a claim (90 files). Run `git diff --stat <pinned-ps-SHA>..<ps-develop-HEAD> -- shared/` against `PS_ROOT` — assert empty output (scout §3 zero-drift baseline)
- **Step 2**: run → if either assertion fails, halt Track 1 and record `DEV-07-BASELINE-DRIFT-DETECTED` deviation
- **Step 3 (green)**: both assertions pass → baseline confirmed; T1.2 proceeds
- **failure-mode**: baseline drift already exists post-06a (unlikely but possible if someone hand-edited toolkit; hook infra `5c01cdb` should prevent) → halt + DEV entry
- **Step 5**: no commit (verification-only)

#### Task T1.2: Materialize curation decision in `TOOLKIT_PROVENANCE.md`
**Files**: `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` (modify) + `tests/engines/nautilus/test_toolkit_provenance_schema.py` (create)

- **Step 1 (red)**: write `test_toolkit_provenance_curation_decision_recorded` — asserts provenance file contains section "Curation decision" with the CEO-ratified DP1 option identifier (a/b/c) + rationale text mentioning specifics (e.g., "no custos Hummingbot host runtime consumer" for (a) rationale per CR-8 narrower framing) + affected-files count matching current vendored subset (90 files for (a))
- **Step 2**: run → red (section absent)
- **Step 3 (green)**: add "Curation decision" section to provenance file with CEO-ratified DP1 content
- **failure-mode**: provenance edit accidentally corrupts existing sync-procedure prose (already-landed 06a content) → `test_toolkit_provenance_pinned_commit_valid` regression (existing pinned commit fields must still parse correctly)
- **Step 5**: commit `docs(custos): record toolkit curation decision in provenance`

### Track 2 — Sync discipline real implementation

#### Task T2.1: Sync-check contract tests (red skeleton, driven by not-yet-real target)
**Files**: `tests/engines/nautilus/test_toolkit_sync_check.py` (create)

- **Step 1 (red)**: write `test_toolkit_sync_check_zero_drift_current` (invokes `make toolkit-sync-check` via subprocess with `PS_ROOT` fixture pointing at ps `develop` HEAD `34b73a2` — asserts exit code 0 + no drift reported), `test_toolkit_sync_check_detects_upstream_drift` (fixture repo with a synthetic commit after pinned SHA under `shared/` — asserts exit code 1 + structured drift report), `test_toolkit_sync_check_reports_new_ps_commits` (asserts stdout format includes commit count + diff-stat), and `test_toolkit_sync_check_requires_ps_root` (per CR-5 fix — dedicated fail-fast test: unset `PS_ROOT`, assert non-zero exit + clear error message referencing `PS_ROOT`)
- **Step 2**: run → red (target is stub, no drift detection, no PS_ROOT guard)
- **Step 3 (green)**: T2.2 implements real target; then tests turn green
- **failure-mode**: sync-check target reports drift when there is none (false positive) → `test_toolkit_sync_check_zero_drift_current` catches; reports zero drift when there is drift (false negative) → `test_toolkit_sync_check_detects_upstream_drift` catches; `PS_ROOT` unset → silent success (should fail-fast) → `test_toolkit_sync_check_requires_ps_root` catches
- **Step 5**: commit `test(custos): sync-check contract tests for zero-drift + drift-detection + output format + PS_ROOT fail-fast`

#### Task T2.2: Makefile `toolkit-sync-check` stub → real diff
**Files**: `Makefile` (modify)

- **Step 1 (red)**: T2.1 tests are red because target is stub (no drift detection + no PS_ROOT guard)
- **Step 2**: run tests → confirm red
- **Step 3 (green)**: Upgrade `toolkit-sync-check` target: (a) read pinned ps SHA from provenance (existing `awk` pattern retained); (b) require `PS_ROOT` env, fail-fast with clear message referencing `PS_ROOT` if unset (satisfies dedicated `test_toolkit_sync_check_requires_ps_root` per CR-5); (c) compute `git -C $PS_ROOT log --oneline <pinned>..HEAD -- shared/` for new commits + `git -C $PS_ROOT diff --stat <pinned>..HEAD -- shared/` for diff-stat; (d) print structured output (labels + commit list + stat); (e) exit 0 if empty diff, exit 1 if drift; (f) pandas_ta path: optional `PANDAS_TA_ROOT`, same pattern, gracefully skip if unset with printed "manual check required" line
- **failure-mode**: `PS_ROOT` env unset → fail-fast with clear message (dedicated test catches per CR-5, independently testable per lesson #22/#28); pandas_ta path unset → skip gracefully (not fail-fast — pandas_ta drifts rarely per DP4 rationale)
- **Step 5**: commit `feat(custos): make toolkit-sync-check emit real ps + pandas_ta drift diff`

#### Task T2.3: Provenance-file drift-audit log appendix
**Files**: `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` (modify) + `tests/engines/nautilus/test_toolkit_provenance_schema.py` (extend)

- **Step 1 (red)**: extend contract test with `test_toolkit_provenance_drift_audit_log_appendable` — asserts provenance file contains section "Drift audit log" with columns `{ran_at, ps_upstream_head, ps_drift, pandas_ta_upstream_head, pandas_ta_drift, run_by}` and at least one seed entry (landing entry = zero drift as of `34b73a2`); asserts new entries append without corrupting prior entries (structural test — regex or table-row count check)
- **Step 2**: run → red
- **Step 3 (green)**: add "Drift audit log" section to provenance file with seed entry recording landing (`ran_at: 2026-07-09`, `ps_upstream_head: 34b73a2`, `ps_drift: no`, `pandas_ta_upstream_head: N/A (upstream not local)`, `pandas_ta_drift: N/A`, `run_by: toolkit curation close-out`)
- **failure-mode**: drift-audit log seed entry uses wrong SHA / date → contract test catches; log format inconsistent with future append operations → append-simulation in test catches
- **Step 5**: commit `docs(custos): add drift audit log to toolkit provenance sync discipline`

### Track 3 — ps convergence documentation + crucible Docker preservation

#### Task T3.1: ps `shared/README.md` custos-as-authority notice (research-side view)
**Files**: `philosophers-stone/shared/README.md` (modify — cross-repo, ps side) + `tests/engines/nautilus/test_convergence_docs.py` (create, custos-side contract test)

- **Step 1 (red)**: write `test_ps_convergence_documentation_no_destructive_delete` in custos-side test file — reads ps `shared/README.md` (via `PS_ROOT` env fixture); asserts contains "custos-as-authority" statement pointing at `src/custos/engines/nautilus/toolkit/shared/` + "no destructive delete" guarantee + reference to crucible Docker preservation window
- **Step 2**: run → red
- **Step 3 (green)**: edit ps `shared/README.md` — add "custos-as-authority notice" section: this directory is a research copy; body-of-truth is custos toolkit; stable code flows ps→custos; crucible Docker preservation window applies; no destructive delete under any Plan 07 option
- **failure-mode**: ps README modified but reference to custos toolkit path is wrong (typo) → contract test catches path mismatch
- **Step 5**: commit ps-side `docs: mark ps shared/ as research copy; custos toolkit is authority`; commit custos-side `test(custos): assert ps convergence docs are non-destructive`

#### Task T3.2: custos-side authority declaration + crucible Docker preservation window docs
**Files**: `docs/design/nautilus_host.md` (modify) + `tests/engines/nautilus/test_convergence_docs.py` (extend)

- **Step 1 (red)**: extend contract tests: `test_crucible_docker_preservation_window_documented` — asserts `docs/design/nautilus_host.md` §"Toolkit sync discipline" section names the hard constraint + Dockerfile-line evidence (scout-verbatim per CR-1 fix: `deploy/nautilus/Dockerfile:1-8` header comment + `:35 COPY shared/README.md /tmp/deps/shared/README.md`; `deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared`) + points at future candidate crucible-runtime-migration plan
- **Step 2**: run → red (section absent per drafter grep)
- **Step 3 (green)**: add "Toolkit sync discipline" section to `docs/design/nautilus_host.md` covering: (a) authority declaration (custos toolkit = shared body-of-truth); (b) sync-check mechanism (Makefile target + weekly cadence per DP3); (c) crucible Docker preservation window hard constraint with evidence; (d) convergence flow (ps→custos as stability accrues); (e) no-destructive-delete guarantee; (f) DP1/DP2/DP3/DP4 decisions inline (drafter-recommended values; CEO-ratified values overwrite at execute-team dispatch)
- **failure-mode**: doc section added but omits Dockerfile-line evidence → test catches
- **Step 5**: commit `docs(custos): add toolkit sync discipline + crucible Docker preservation window to nautilus_host design`

### Track 4 — pandas_ta governance formalization (DP4)

#### Task T4.1: pandas_ta trigger-criteria appendix in provenance
**Files**: `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` (modify)

- **Step 1 (red)**: extend contract test — asserts provenance file contains "pandas_ta governance" section with the three trigger criteria (>2 upstream drift/quarter; other non-Guild reuse; Rust migration) + explicit "status quo = vendored fork" statement
- **Step 2**: run → red
- **Step 3 (green)**: add "pandas_ta governance" subsection to provenance file with CEO-ratified DP4 content (status quo + trigger criteria); link back to `DEV-06-DP1-DEFERRED-C-OPTION` for historical context
- **Step 5**: commit `docs(custos): formalize pandas_ta governance trigger criteria in toolkit provenance`

### Track 5 — Close-out (forced final)

#### Task T5.1: `.forge/README.md` index update + Plan 07 close-out report
**Files**: this plan file + `.forge/README.md`

- **Step 1**: `.forge/README.md` Plan 07 row Status ⏳ → ✅ with completion date + brief summary of DP1/DP2/DP3/DP4 decisions
- **Step 2**: this plan file top `Status: 🔲 Todo → ✅ Completed` + `Completed: YYYY-MM-DD`
- **Step 3**: fill "Close-out Report" section (per `progress-management.md` template) with red-line gate satisfaction table (lesson #40 / C40)
- **Step 4**: note Plan 08 START gate is now open (Plan 07 landing unblocks Plan 06 remainder e2e coverage + sidecar retirement docs per §Blocks)
- **Step 5**: `git add <this plan> .forge/README.md && git commit -m "docs(custos): mark plan 07 as completed"`

---

## Verification

- [ ] `make verify` (fmt-check + lint + pytest baseline): PASS after each Track green + close-out
- [ ] `make toolkit-sync-check` with `PS_ROOT=<ps-develop-HEAD>`: exit 0 zero-drift (baseline confirms as-of `34b73a2`)
- [ ] `make toolkit-sync-check` with `PS_ROOT=<synthetic-drift-fixture>`: exit 1 with structured drift report (contract test verifies)
- [ ] `TOOLKIT_PROVENANCE.md` contains: (a) existing 06a-landed content unchanged; (b) NEW "Curation decision" section with CEO-ratified DP1 option + rationale; (c) NEW "Drift audit log" appendix with landing seed entry (drift = no as of `34b73a2`); (d) NEW "pandas_ta governance" subsection with CEO-ratified DP4 status quo + three trigger criteria
- [ ] `docs/design/nautilus_host.md` contains "Toolkit sync discipline" section with authority declaration + sync-check mechanism + crucible Docker preservation window + convergence flow + no-destructive-delete guarantee
- [ ] `philosophers-stone/shared/README.md` contains custos-as-authority notice + no-destructive-delete guarantee (ps-side commit)
- [ ] Contract tests full grep-verified NEW (lesson #25 close-out gate): all test names still return 0 hits in `tests/` before create, then present after Track ends
- [ ] Non-Custodial 4 red lines grep from `verification.md` §"red-line specific check": 0 hits (Plan 07 makes no source-code changes; existing gates hold)
- [ ] No source-code comment contains plan/task/lesson tracking numbers (lesson #15 grep gate)
- [ ] Cross-repo commits use `git add <specific-file>` only (mandatory-rules §6 + lesson #3): custos + ps two independent commits

---

## Progress

| Task | Track | Status | Completed | Notes |
|------|-------|--------|-----------|-------|
| T1.1 Baseline confirmation (currently-vendored subset matches 06a claim) | 1 | 🔲 | | verification-only; halt if drift detected + DEV entry |
| T1.2 Materialize curation decision in TOOLKIT_PROVENANCE.md | 1 | 🔲 | | DP1 recommendation landing (CEO-ratified value written at dispatch time) |
| T2.1 Sync-check contract tests (red skeleton) | 2 | 🔲 | | drives T2.2 |
| T2.2 Makefile toolkit-sync-check stub → real diff | 2 | 🔲 | | requires `PS_ROOT`; optional `PANDAS_TA_ROOT` |
| T2.3 Provenance drift-audit log appendix | 2 | 🔲 | | seed entry = Plan 07 landing |
| T3.1 ps shared/README.md custos-as-authority notice (cross-repo) | 3 | 🔲 | | DP2 non-destructive; ps-side commit |
| T3.2 docs/design/nautilus_host.md Toolkit sync discipline section | 3 | 🔲 | | crucible Docker preservation window hard constraint |
| T4.1 pandas_ta governance trigger criteria appendix | 4 | 🔲 | | DP4 formalization |
| T5.1 Close-out (forced final) | 5 | 🔲 | | `.forge/README.md` index + red-line gate satisfaction table |

**multi_session_scope = false** — 9 tasks total (across 5 Tracks); light code footprint (one Makefile target + 3 test files + 3 doc files + 1 ps-side README edit); should complete in a single execute-team session. No slicing needed.

---

## Failure-mode coverage contract (lesson #17 + #25)

> **status column**: ✓existing = drafter grep-verified 2026-07-09 as present in `tests/`; NEW = executor creates. Every NEW test name grep-verified 0 hits (see drafter Bash log preceding this file's write). Existing tests act as no-regression parity. Post-CR-5 fix: total NEW tests = 9 (was 8; added `test_toolkit_sync_check_requires_ps_root`).

| # | Track | Failure scenario | Coverage test | status |
|---|-------|------------------|---------------|--------|
| — | T1.1 | Baseline drift already exists post-06a (someone hand-edited toolkit) | (verification task; halt + `DEV-07-BASELINE-DRIFT-DETECTED`) | (no test; verification action) |
| 1 | T1.2 | Curation decision recorded incorrectly (wrong DP1 option / missing rationale) | `test_toolkit_provenance_curation_decision_recorded` | NEW |
| 2 | T1.2 (no-regr) | Existing pinned commit fields corrupted by provenance edit; existing sync-procedure prose preserved | `test_toolkit_provenance_pinned_commit_valid` (structural — asserts pinned commit + Sync procedure sections intact) | NEW |
| 3 | T2.1 / T2.2 | Sync-check false positive (reports drift when zero-drift) | `test_toolkit_sync_check_zero_drift_current` | NEW |
| 4 | T2.1 / T2.2 | Sync-check false negative (misses upstream drift) | `test_toolkit_sync_check_detects_upstream_drift` | NEW |
| 5 | T2.1 / T2.2 | Sync-check output format lacks new-commit report + diff-stat | `test_toolkit_sync_check_reports_new_ps_commits` | NEW |
| 6 | T2.1 / T2.2 | `PS_ROOT` env unset → silent success (should fail-fast) | `test_toolkit_sync_check_requires_ps_root` (dedicated per CR-5; independently testable per lesson #22/#28) | NEW |
| 7 | T2.3 | Drift-audit log append corrupts prior entries | `test_toolkit_provenance_drift_audit_log_appendable` | NEW |
| 8 | T3.1 | ps convergence docs missing "no destructive delete" guarantee | `test_ps_convergence_documentation_no_destructive_delete` | NEW |
| 9 | T3.2 | custos-side docs missing crucible Docker preservation window statement | `test_crucible_docker_preservation_window_documented` | NEW |
| — | T4.1 | pandas_ta trigger criteria absent / status quo statement missing | (extends `test_toolkit_provenance_curation_decision_recorded` — asserts DP4 subsection with three trigger criteria + status quo) | (extension of test #1; not a separate NEW test) |
| — | (no-regr) | 06a red-line 0.4 grep gate on vendored toolkit money math | `test_vendored_toolkit_no_new_float_money_math` | ✓existing (06a-landed; grep-verified 1 hit at `tests/engines/nautilus/test_toolkit_provenance.py` on 2026-07-09; executor confirms at Track 1 baseline) |

**Total NEW tests: 9** (rows numbered 1–9). Row for T4.1 is an extension of row 1 (`test_toolkit_provenance_curation_decision_recorded`), not a separate NEW test. Row for `test_vendored_toolkit_no_new_float_money_math` is existing (grep-verified 1 hit; no-regression coverage).

> **drafter grep re-verification (2026-07-09, lesson #25)**: All 9 NEW test names above returned `hits=0` in drafter Bash grep of `tests/` (see drafter Bash log preceding this file's write; result table also inline in fix log `.forge/fixes/2026-07/07-plan-fix.md`). Existing `test_vendored_toolkit_no_new_float_money_math` returned `hits=1` (present at `tests/engines/nautilus/test_toolkit_provenance.py`). Executor **must re-run `grep -rn "def test_X" tests/` at close-out** for each NEW test — verify count went from 0 → 1 (present + running).

---

## Red-line gate satisfaction (lesson #40 / custos C40)

> **Red-line name (vision) ≠ delivery statement (reality)**: distinguish code_coverage (what tests cover) / runtime_wire (composition-root wiring) / defer_status (deferred scope).

| Red line | Delivery target | code_coverage | runtime_wire | defer_status |
|----------|-----------------|---------------|--------------|--------------|
| 0.1 Key/KEK never leaves process | Plan 07 makes no source-code changes; inherited gates unchanged | no Plan 07-specific coverage; inherited from Plan 03 credential lifecycle — `tests/test_credential_lifecycle.py` (verified present, grep hit at `tests/test_credential_lifecycle.py`; includes credential-path canary asserts per lesson C2 evidence, e.g., `assert data_cfg.api_key == _SENTINEL_KEY` + `assert data_cfg.api_secret == _SENTINEL_SECRET`) + `tests/test_credential_vault.py` + `tests/test_credential_vault_sops.py` | no Plan 07-specific runtime wire (credential paths untouched); inherited wire = `src/custos/core/credential_vault.py` `_verify_permission_scope()` + telemetry actor whitelist (per `docs/design/credential_vault.md` + `docs/design/telemetry_actor.md`) | no defer; Plan 07 delivery = no-regression |
| 0.2 G6 gate not bypassed | Plan 07 makes no G6 gate changes; toolkit not entering per-deploy code_hash scope (Plan 06 DEV-06-TOOLKIT-HASH-SCOPE DP4 (a) landed) | no Plan 07-specific coverage; inherited from Plan 00c G6 landing — `tests/test_g6_gate.py` (verified present) + `tests/test_g6_gate_capability_integration.py` + `tests/test_g6_gate_capability_e2e.py` | no Plan 07-specific runtime wire (G6 gate at `src/custos/engines/nautilus/host.py` unchanged); inherited wire = `NtTradingNodeHost.start()` gate per `docs/design/nautilus_host.md` §"G6 gate contract" | no defer; Plan 07 delivery = no-regression |
| 0.3 Disconnected ≠ stopped | Plan 07 does not touch red-line 0.3 delivery. Per-strategy layer (RiskController) = Plan 06; per-runner cap = Plan 04 | no Plan 07-specific coverage; inherited from Plan 04 (per-runner cap) + Plan 06 (per-strategy RiskController) | no Plan 07-specific runtime wire | Both layers delivered in Plan 04 (per-runner) + Plan 06 (per-strategy). Plan 07 = no-op |
| 0.4 Money math Decimal | Plan 07 makes no money-math changes; 06a red-line 0.4 grep gate on vendored toolkit unchanged (curation status quo per DP1 = same 90-file surface as 06a landed) | inherited from Plan 06 06a — `test_vendored_toolkit_no_new_float_money_math` (grep-verified 1 hit at `tests/engines/nautilus/test_toolkit_provenance.py` on 2026-07-09; executor confirms no-regression at Track 1 baseline) | no Plan 07-specific runtime wire (money-path code untouched); inherited wire = `src/custos/core/telemetry_actor.py` Decimal→str serialization per `docs/design/telemetry_actor.md` §money contract | no defer; Plan 07 delivery = no-regression |

**Delivery scope statement (fill at close-out)**: "Plan 07 delivers architectural end-state landing + DP1/DP2/DP3/DP4 CEO-ratified decisions (recorded inline at dispatch) + sync-check real implementation + convergence documentation + pandas_ta governance formalization. No source-code changes (curation status quo per DP1 = zero vendored-subset delta from 06a). All 4 red lines unchanged from post-06a state; existing gates preserved; no regression risk." — Architecture landing does not weaken any red-line delivery.

---

## Deviations & Improvements

> **CEO decision points ×4 (elevate, no silent decisions)**: DP1 curation scope (drafter recommends a, options a/b/c on record); DP2 ps convergence + crucible Docker preservation (drafter recommends a hard-constraint-derived, options a/b/c on record); DP3 sync-check cadence (drafter recommends b, options a/b/c on record); DP4 pandas_ta governance (drafter recommends a+b combined, formalize trigger criteria). All DP status uniform "drafter recommends; CEO pending" until execution dispatch records CEO choice (CR-3 fix).

### DEV-07-CURATION-SCOPE [CEO DECISION POINT 1]

- **Severity**: Medium (architectural end-state landing decision + affects future strategy migration friction)
- **Question**: Post-06a curation scope — keep full-9-subpackage vendor (a) / extend to `shared/hummingbot/` (b) / trim to strict supertrend minimal closure (c)?
- **Option (a) — Keep 06a full-9-subpackage vendor** (drafter recommends): current 90-file / 17,110-LOC surface covers all 6 ps NT-path strategy dirs' closure; future ps strategies (`aion_trend` / `market_making/adaptive_grid` per scout §1.2 non-consumers today) flow to custos without re-vendor churn; red-line 0.4 grep gate already covers this surface (`test_vendored_toolkit_no_new_float_money_math` landed 06a)
- **Option (b) — Extend to `shared/hummingbot/`**: 13-file / 2730-LOC expansion. **Refuted**: scout §1.3 (with CR-8 errata) confirms no custos Hummingbot host implementation and no `shared.hummingbot.*` runtime consumer outside vendored/provenance references. Vendoring engine-glue with no runtime consumer expands audit surface without benefit. Revisit only when a future custos Hummingbot host emerges (Plan 08+ engine-plugin roadmap per Plan 05 "Next steps")
- **Option (c) — Trim to strict supertrend minimal closure**: reduce to `config` + `signals` + `risk` + narrow `shared/nautilus/{coordinators/risk_control.py, indicators/supertrend.py, trading_strategy.py}` + supporting files. **Risk**: `aion_trend` and `market_making/adaptive_grid` (scout §1.2) are pending future strategies; trimming forces re-vendor churn for every future migration
- **Impact**: (a) `src/custos/engines/nautilus/toolkit/shared/` unchanged (status quo) / (b) add 13-file `shared/hummingbot/` subtree / (c) delete files outside supertrend closure — regenerates red-line 0.4 grep gate perimeter
- **Decision**: drafter recommends (a); **CEO pending** (selecting b or c triggers Track 1 re-scope)
- **CEO ruling**: (pending) — record here at execute-team dispatch time
- **Updated documents**: `TOOLKIT_PROVENANCE.md` §"Curation decision" (T1.2)

### DEV-07-PS-CONVERGENCE-AND-CRUCIBLE-DOCKER-PRESERVATION [CEO DECISION POINT 2]

- **Severity**: **High (hard-constraint decision — crucible Docker preservation window is derived from architectural evidence, not a soft preference)**
- **Question**: ps convergence criteria + when to converge ps `shared/` to research-only copy — considering the crucible Docker preservation constraint (evidence-scout §4.2 surfaced)
- **Option (a) — Short-term keep ps Docker-buildable `shared/` + `deploy/` until crucible→custos runtime migration** (drafter recommends, hard-constraint-derived): ps `shared/` stays; convergence documentation adds deprecation notices in ps README (T3.1) pointing at custos toolkit; no ps files deleted or moved; sync-check flows stable code from ps→custos; future crucible→custos runtime migration (multi-quarter, out of Plan 07 scope) unblocks eventual ps convergence to research-only copy
- **Option (b) — Immediately converge ps to research-only copy (delete/move ps `shared/`)**: **Rejected by hard constraint** — scout §4.2 anchors: `philosophers-stone/deploy/nautilus/Dockerfile:1-8` header comment ("runtime base: NT + deps + shared + sidecar") + `:35 COPY shared/README.md /tmp/deps/shared/README.md`; `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared` bundle ps `shared/` into production runtime container images that `the-crucible` supervises. Immediate destructive convergence would break running production containers
- **Option (c) — Add "crucible→custos runtime migration plan" as Plan 07 blocker**: expand scope to include cross-repo (custos + crucible + ps) coordination + multi-quarter timeline. **Rejected as scope creep** — that migration warrants its own dedicated plan (candidate future plan `crucible-runtime-migration`); Plan 07 delivers what is audit-able and CEO-ratifiable today without cross-repo coordination cost
- **Impact**: (a) T3.1 adds ps `shared/README.md` deprecation notice (non-destructive); T3.2 documents crucible Docker preservation window in `nautilus_host.md` + points at future crucible-runtime-migration candidate plan / (b) rejected / (c) expands Plan 07 into cross-repo blocker plan
- **Decision**: drafter recommends (a); **CEO pending**
- **CEO ruling**: (pending)
- **Updated documents**: `docs/design/nautilus_host.md` §"Toolkit sync discipline / crucible Docker preservation window" (T3.2) + ps `shared/README.md` (T3.1)

### DEV-07-CRUCIBLE-DOCKER-PRESERVATION-HARD-CONSTRAINT (evidence-scout derived, informs DP2)

- **Severity**: High (architectural evidence-derived; not a decision but a hard constraint)
- **Background**: evidence-scout §4.2 Round 3 cascade chase surfaced: `crucible_engine/*.py` has 0 direct `from shared` imports (pure HTTP orchestrator via `httpx` to `sidecar_url`); but scout §4.2 anchors — `philosophers-stone/deploy/nautilus/Dockerfile:1-8` header comment ("runtime base: NT + deps + shared + sidecar") + `:35 COPY shared/README.md /tmp/deps/shared/README.md`; `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared` — bundle ps `shared/` into production runtime container images that `the-crucible` supervises. This finding was **not** anticipated in the dispatch-prompt hints; surfaced only by reading Dockerfiles (not by grepping `.py` imports for `shared`)
- **Decision**: Plan 07 delivery must include explicit documentation of this hard constraint (T3.2) + link to future candidate plan `crucible-runtime-migration` as the unblocker for eventual ps convergence
- **cross-reference**: informs DP2 (a) drafter recommendation; also lands in lesson-C candidate (evidence-scout Round 3 discovery pattern — Foundation Scan influence-dimension escalation per lesson #33b)

### DEV-07-SYNC-CHECK-CADENCE [CEO DECISION POINT 3]

- **Severity**: Low (operational rhythm decision; does not affect red-line delivery)
- **Question**: Sync-check triggering cadence — auto-alert on every ps commit (a) / weekly diff review (b) / manual trigger only (c)?
- **Option (a) — Auto-alert on every ps commit**: requires webhook or polling infra outside custos. **Rejected as scope creep** for Plan 07 (custos has no CI today per scout §9; Plan 09 lands CI)
- **Option (b) — Weekly diff review** (drafter recommends): manageable rhythm; sync-check run manually or via cron weekly; results appended to provenance drift-audit log (T2.3); drift → trigger sync procedure in TOOLKIT_PROVENANCE.md
- **Option (c) — Manual trigger only**: pure on-demand; no rhythm commitment. **Risk**: drift accumulates silently
- **Impact**: (b) T3.2 docs section §"sync-check cadence" states weekly review runbook; enforcement via ops runbook (until Plan 09 CI lands)
- **Decision**: drafter recommends (b); **CEO pending**
- **CEO ruling**: (pending)
- **Updated documents**: `docs/design/nautilus_host.md` §"Toolkit sync discipline" (T3.2) + `TOOLKIT_PROVENANCE.md` §"Drift audit log" (T2.3)

### DEV-07-PANDAS-TA-GOVERNANCE [CEO DECISION POINT 4]

- **Severity**: Low (governance formalization; does not affect runtime code)
- **Question**: pandas_ta governance — keep vendored fork status quo (a) / formalize DEV-06-DP1-DEFERRED-C-OPTION trigger conditions for future PyPI-package escalation (b) / both (a+b)?
- **Option (a) — Keep vendored fork status quo**: 149 files vendored at fork SHA `a3a2228` + LICENSE retained (Plan 06 06a landing); audit surface known; no external supply-chain surface added
- **Option (b) — Formalize DEV-06-DP1-DEFERRED-C-OPTION trigger conditions**: explicit criteria in provenance-file appendix — (i) >2 upstream drift events/quarter that provenance sync struggles to keep up with; (ii) other non-Guild projects need reuse of the fork; (iii) custos Rust migration starts and needs toolkit as decoupled package. Any single trigger firing → CEO revisits pkg escalation via new dedicated plan
- **Option (a+b) — Both** (drafter recommends): status quo + explicit escalation criteria = layered discipline; complementary not alternative
- **Impact**: (a+b) T4.1 adds "pandas_ta governance" subsection to provenance file with both status quo statement + three trigger criteria (CEO-ratified DP4 content)
- **Decision**: drafter recommends (a+b combined); **CEO pending**
- **CEO ruling**: (pending)
- **Updated documents**: `TOOLKIT_PROVENANCE.md` §"pandas_ta governance" (T4.1) — link back to DEV-06-DP1-DEFERRED-C-OPTION for historical context

### DEV-07-CROSS-REPO-COMMIT-CHOREOGRAPHY

- **Severity**: Medium (cross-repo custos + ps)
- **Question**: custos + ps two-repo commit orchestration + atomic guarantee (inherited pattern from Plan 06 DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY)
- **Decision**: two-repo independent commits (`git add <specific-file>`, mandatory-rules §6 + lesson #3); no atomic cross-repo guarantee — Plan 07 sync-check contract tests (T2.1) are the integration gate. ps-side commit is a single docs-only edit (T3.1 adds ps `shared/README.md` custos-as-authority notice); custos-side commits span T1.2 / T2.1 / T2.2 / T2.3 / T3.2 / T4.1 / T5.1
- **cross-reference**: lesson #3 forbids `git add .` / `-A`; lesson #27 commit-scope discipline `git status --short` before commit

### DEV-07-NO-SOURCE-CODE-CHANGES (drafter design choice)

- **Severity**: Low (drafter design choice, not a CEO surface)
- **Question**: Should Plan 07 touch `src/custos/**/*.py`?
- **Decision**: **No** — Plan 07 delivers decisions + docs + Makefile + tests + provenance-file evolution. The vendored subset (`src/custos/engines/nautilus/toolkit/shared/**`) is unchanged from 06a landing per DP1 (a) recommendation "keep status quo". This zero-source-code-change scope reduces risk of red-line 0.1/0.2/0.4 regression to zero (grep gates automatically pass because targeted code paths are untouched)
- **cross-reference**: red-line gate satisfaction table above — Plan 07 = no-regression across all 4 red lines

---

## Codex peer review criteria

Per `.forge/teams.yaml` `codex_audit.max_calls_per_plan=3` (custos budget vs arx 5):

- **First call (L1 peer review)**: `--peer=codex --deep=off` medium effort. Focus areas: (1) DP1/DP2/DP3/DP4 rationale soundness; (2) crucible Docker preservation window hard-constraint framing accuracy (is DP2 (a) truly the only non-regressive option?); (3) sync-check real-implementation gap coverage (does the Makefile upgrade close the drift-detection surface? False-positive / false-negative / fail-fast risk); (4) provenance-file schema evolution (curation-decision + drift-audit log + pandas_ta governance) — is the schema future-proof for weekly drift entries?; (5) failure-mode coverage completeness (9 NEW tests + 1 no-regression grep-verified — post-CR-5 fix added `test_toolkit_sync_check_requires_ps_root` as dedicated fail-fast test; anything missing?); (6) cross-repo commit choreography (mandatory-rules §6 + lesson #3 + lesson #27 compliance)
- **Second call (fix cycle)**: reserve for CRITICAL/HIGH finding surface if L1 flags any. drafter in-place directed fix (Option B/C per Plan 06 precedent — no full-scope re-draft)
- **Third call**: reserve for non-routine escalation (drafter major-drift / architect-team elevation)

---

## References

| Ref | Path |
|-----|------|
| Dispatch packet (Batch 1 handoff) | `.forge/handoff/2026-07/plan-team-07-08-09-packet.md` §3 (Plan 07 scope) + §6 (References) + §7-9 (Drafter dispatch parameters + peer review + Language Policy) |
| Evidence-scout report | `.forge/handoff/2026-07/evidence-scout-07-08.md` (230 lines; §1 ps shared full closure + §2 custos toolkit current state + §3 drift check + §4 ps consumer cascade including §4.2 crucible Docker bundling critical finding) |
| Plan 06 (predecessor pattern) | `.forge/plans/2026-07/06-ps-supertrend-migration.md` (Track 3 vendoring decision + DEV-06-06A-REVERSE-DEPENDENCY-STRATEGY-D' + DEV-06-DP1-DEFERRED-C-OPTION memo) |
| Plan 05 §DEV-05-TOOLKIT-LOCATION | `.forge/plans/2026-07/05-structural-refactor-engine-abstraction.md:506-510` (toolkit location = `engines/nautilus/toolkit/`, fixed) |
| Plan index (execution order) | `.forge/README.md:50-62` execution-order suggestion (Plan 07 = ps shared curation migration → `custos.engines.nautilus.toolkit.*`) |
| Main HEAD (post-06a squash) | `306b9e5` (Plan 06 06a squash-merge) + `5c01cdb` (hook infra) + `55782d0` (06a orchestration artifacts) |
| ps develop HEAD | `34b73a2` (ps `develop`, as-of evidence-scout run 2026-07-09) |
| pinned toolkit SHAs | ps `fc4ab1d` + pandas_ta fork `a3a2228` (per `TOOLKIT_PROVENANCE.md:20,61`) |
| Language Policy authority | `CLAUDE.md` §Language Policy (Code Artifacts) + `.claude/rules/code-style.md` §Language constraint |
| Mandatory rules | `.claude/rules/mandatory-rules.md` (§0 non-custodial 4 red lines + §6 cross-repo commit discipline + §7 independent-repo self-sufficiency) |
| Historical lessons applied | `.claude/rules/historical-lessons.md` — #9/#11/#14/#17/#22/#25/#26/#28/#33/#33b/#37/#40 + custos C1 (CEO override) / C2 (output pollution) |

---

## Close-out Report (Close-out)

(Fill after Phase 3 execution completes, per `progress-management.md` template)

- **Completion date**: {YYYY-MM-DD}
- **Total task count**: 9 (across 5 Tracks, including close-out)
- **Deviation count**: {N} (`DEV-07-*` detail in Deviations; DP1/DP2/DP3/DP4 CEO decisions landing recorded)
- **Verification result**: full pass / partial pass
- **Implementation commit range**: custos `{first_sha}..{last_sha}` + ps single-commit `{ps_sha}` (cross-repo)
- **Contract impact**: `TOOLKIT_PROVENANCE.md` (Curation decision + Drift audit log + pandas_ta governance sections) + `docs/design/nautilus_host.md` (Toolkit sync discipline + crucible Docker preservation window) + `philosophers-stone/shared/README.md` (custos-as-authority notice) + `Makefile toolkit-sync-check` (stub → real diff)
- **Red-line preservation**: Non-Custodial 4 red lines fully preserved (Plan 07 makes zero source-code changes; existing gates unchanged) — see red-line gate satisfaction table above
- **Failure-mode coverage**: 9 NEW contract tests (sync-check with `PS_ROOT` fail-fast dedicated + provenance schema + convergence docs) + 1 no-regression grep-verified (`test_vendored_toolkit_no_new_float_money_math` 06a existing at `tests/engines/nautilus/test_toolkit_provenance.py`)
- **Follow-ups**: crucible→custos runtime migration (future candidate plan) + Plan 08 START gate now open + Plan 09 CI integration (future candidate) — sync-check weekly cadence enforcement via ops runbook until CI lands

---

## Next

Plan 07 close-out unblocks:

- **Plan 08 START gate opens** — Plan 06 remainder (Track 5 e2e + Track 6 sidecar retirement docs) can proceed; Plan 08 T5.1 e2e coverage now knows curation scope (DP1 = full 90-file vendored subset); Plan 08 T6.1 sidecar retirement docs align with crucible Docker preservation window (DP2 (a) hard constraint statement in `nautilus_host.md` T3.2)
- **Weekly sync-check runbook** — ops or dev periodically runs `make toolkit-sync-check` with `PS_ROOT` set; drift → follow sync procedure in `TOOLKIT_PROVENANCE.md`; drift-audit log entries append with each run
- **crucible→custos runtime migration** — future candidate plan (multi-quarter timeline); unblocks eventual ps convergence to research-only copy (removing crucible Docker preservation window constraint)
- **pandas_ta PyPI-package escalation** — dormant until DP4 trigger criteria fire; DEV-06-DP1-DEFERRED-C-OPTION memo remains active
