# Plan 12 review round 2 (claude, custos)

- **Plan**: `.forge/plans/2026-07/12-custos-distribution-signed-wheel-docker-lts.md`
- **Reviewer**: claude (opus-4-7[1m], Plan-team R2 reviewer role)
- **Base**: Round 1 review `.forge/reviews/2026-07/12-plan-review-claude.md` + `.forge/reviews/2026-07/cross-plan-11-12-review-claude.md`
- **Fix commit**: `2bae32b` (2026-07-10 21:13 +0800)
- **Verdict**: **APPROVE with 1 CRITICAL follow-up + 2 MEDIUM new findings** — Round 1 fix landing rate 22/22 = 100% (all CRITICAL + HIGH + MEDIUM + LOW + all Cross findings addressed with matching intent). However, the H3 (`token_sha256` → `token_hash`) fix touched only the field name and did NOT audit full payload shape → **schema is now missing `agent_version` field while `additionalProperties: false` is set → Plan 11 actual runner payload will FAIL v1 schema validation on landing**. This is a Round 1 HIGH-derivative regression: the fix corrected the reviewed defect but left a related contract-shape defect. Additionally 1 MEDIUM (Cross H4 delegation gap: docker mount pattern doc has no owner across Plan 11 T9 + Plan 12 T9), 1 MEDIUM (Dockerfile `.arx` directory writability without pre-mkdir + chown). Not blocking execute-team dispatch since Plan 12 T7 executor can add missing schema field within Task 7 scope + Task 2 executor can add mkdir/chown line — but must be tracked as R2 execute-time follow-ups.

**Fix completion**: 22/22 = 100% (BLK-4/C2 + BLK-5/C1 + H1-H6 + M1/M2/M4/M5/M6/M7 + Cross H1/H4/H5/M1/M3/M5 + L1/L2)

**Counts**: 1 Critical (new subtle regression) / 2 Medium (new subtle) / 3 Positive / 22 fixes verified landed

---

## Round 1 finding acceptance table

| Finding | Type | Landed? | Evidence (Plan 12 line) | Note |
|---------|------|---------|-------------------------|------|
| BLK-4 / C2 (Dockerfile ENTRYPOINT) | CRIT | ✅ Landed | line 245-246 `ENTRYPOINT ["arx-runner", "start"]` (C2 fix); line 169 `tests/test_docker_entrypoint_help.py`; verify-release.sh line 312 `docker run --rm ... --help` + line 314 non-root probe | FM2 Layer 3 (smoke) 已 alive, 独立可测 |
| BLK-5 / C1 (backward-compat direction) | CRIT | ✅ Landed | line 406 `set(current.get("required", [])) <= set(golden.get("required", []))` (方向正确); 3 negative test 名 `test_additive_optional_field_passes` (413) / `test_new_required_field_blocked` (423) / `test_removed_property_blocked` (431) 全落地 | additive-only 精准语义闭环, 新增 required 会被 assert 阻断 |
| H1 (Dockerfile 本地 wheel) | HIGH | ✅ Landed | line 232 `COPY dist/custos_runner-*.whl /tmp/` + line 233 `pip install --no-index --find-links=/tmp`; line 295 CI DAG `build-wheel` → `build-docker` wheel artifact input | 避免 PyPI 首发鸡生蛋 |
| H2 (`permissions:` 复数) | HIGH | ✅ Landed | line 293 `**permissions:**` (H2 fix) 明说复数; sigstore OIDC id-token / packages / contents 三 scope | plan 文本澄清, executor 落地 workflow YAML 时用正确 key |
| H3 (`token_sha256` → `token_hash`) | HIGH | ⚠️ **Partial** — 见 R2-C1 | line 450 `"required": ["token_hash", "runner_id"]`; line 452 `"token_hash": {...}`; line 460 H3 note | 字段名改对但**未审全 payload shape** → 见下 R2-C1 subtle regression |
| H4 (`~=0.2.0` pin) | HIGH | ✅ Landed | line 117 `~=0.2.0` (PEP 440 展开 `>=0.2.0, <0.3.0`) | 禁自动升 minor 意图与实际对齐 |
| H5 (8 job DAG) | HIGH | ✅ Landed | line 294 `**8 job 串行 DAG** (H5 fix — 6 vs 8 内部矛盾修正; 无合并规则)` | 8 job 逐字列出无歧义 |
| H6 (sigstore `--help` grep + pin) | HIGH | ✅ Landed | line 210 `sigstore>=3.0,<4.0` 显式 major pin; line 269-270 executor 落地时先跑 grep 实证 flag 名的注释 | UNVERIFIED 状态明说, executor 落地时兜底 |
| M1 (SEMVER MINOR wording) | MED | ✅ Landed | line 113 `新增 optional field: MINOR (需两侧同步部署)` / `新增 required field: MAJOR` 明确 | additive-only 语义澄清 |
| M2 (PATCH dep 版本) | MED | ✅ Landed | line 114 `依赖 patch/minor 版本升级 (uv.lock 同步 commit) 允许`; `依赖 major 版本升级归 MINOR` | uv.lock 变化归属明确 |
| M4 (T8 对照 test) | MED | ✅ Landed | line 488-505 `test_wheel_bytes_differ_without_epoch` 含 hatchling native deterministic 处理 docstring | false positive 防护到位 |
| M5 (FM11 800MB) | MED | ✅ Landed | line 173 + line 194 `500MB → 800MB` | flaky-fail 风险降低 |
| M6 (CI tag pattern) | MED | ✅ Landed | line 292 `v[0-9]+.[0-9]+.[0-9]+` + rc.* 独立 workflow 处理 | stable-only, rc 不污染稳定 channel |
| M7 (Foundation Scan iter 4) | MED | ✅ Landed | line 620 iteration 4 arx-side wire UNVERIFIED + 跨 plan wire 字段名 fanout 核对 | Foundation Scan 4 维完整 |
| Cross H1 (CHANGELOG 结构) | HIGH | ✅ Landed | line 331-336 T5 Step 3 明列 `### Removed` (Plan 11) / `### Changed` (Plan 11) / `### Added` (Plan 12) 三段 + line 336 明说 T5 唯一 owner | 下游 `~=0.2` client 可清晰读到 breaking scope |
| Cross H4 (Dockerfile useradd + HOME + VOLUME) | HIGH | ⚠️ **Partial** — 见 R2-M1 | line 237-243 `useradd -u 1000 -m -d /home/custos custos` + `ENV HOME=/home/custos` + `VOLUME ["/home/custos/.arx"]`; Cross H4 note line 221 委托 docs/ops/05-deployment.md 挂载 pattern 给 Plan 11 T9 | Dockerfile 主体对了; docker mount 段 doc 责任归属**不闭环** → 见 R2-M1 |
| Cross H5 (strict serial merge) | HIGH | ✅ Landed | line 10 `**Cross H5 — Strict serial merge protocol**` + SHA gate `grep 'plan 11 t8'` + `grep '"arx-runner"'` + "Plan 12 does NOT run in worktree parallel with Plan 11" | execute-team spawn prompt 强制入口固化 |
| Cross M1 (T9 README inspection-only) | MED | ✅ Landed | line 530 `README.md § "Not Included Yet" 剩余项精简 (Cross M1 fix — T5 已处理; T9 只做 inspection-only 复检)` | 三方修改冲突预防 |
| Cross M3 (DP5 wording) | MED | ✅ Landed | line 629 `partial resolve` → `resolved` (Cross M3 fix — 与 line 101 DP5 header "RESOLVED" 一致) | 内部一致 |
| Cross M5 (fanout list) | MED | ✅ Landed | line 629 fanout list 扩展 `pyproject.toml + Dockerfile + verify-release.sh + release.yml + docs/lts-commitment.md + docs/ops/05-deployment.md + docs/design/03-implementation.md + README.md + CHANGELOG.md` | 9 消费者显式列出 |
| L1 (EOL 日期表行断言) | LOW | ✅ Landed | line 364-370 `test_lts_doc_has_eol_date_row` regex `\|\s*0\.\d+\.x\s*\|\s*\d{4}-\d{2}-\d{2}` 抓 EOL 表行 | FM10 audit-non-silence 兜底强化 |
| L2 (SECURITY.md no warranty) | LOW | ✅ Landed | line 166 File Inventory SECURITY.md 描述 + line 534 T9 §4 SECURITY.md 内容注明 Apache-2.0 免责声明 | Apache-2.0 disclaimer 明说 |

**Fix landing 22/22 = 100%**。R1 verdict 提到的所有 CRITICAL / HIGH / MEDIUM / LOW / Cross 项均在 Plan 12 fix commit `2bae32b` 中有 file:line 落点 + IMPROVEMENT 偏离日志条目登记。

---

## New R2 findings (fix 引入的 subtle 漏洞 / 未覆盖侧)

### R2-C1 (CRITICAL) — H3 fix incomplete audit: 修正 `token_hash` 字段名但**未审全 payload shape** → `agent_version` 遗漏 + `additionalProperties: false` → Plan 11 实际 runner payload 会 FAIL v1 schema 验证

**位置**:
- Plan 12 line 450-457 enrollment.schema.json (T7 实现):
  ```json
  "required": ["token_hash", "runner_id"],
  "properties": {
    "token_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "runner_id": { "type": "string", "maxLength": 128 },
    "capabilities": { "type": "array", "items": { "type": "string" } }
  },
  "additionalProperties": false
  ```

**与 Plan 11 payload 对照** (Plan 11 line 308 + line 319):
```python
# Plan 11 test_enroll_payload_shape 断言 payload =
{"token_hash": <sha256 hex>, "runner_id": <id>, "agent_version": <str>, "capabilities": <list>}

# Plan 11 T4 Step 3 build payload =
{"token_hash": ..., "runner_id": ..., "agent_version": ..., "capabilities": args.capabilities}
```

**问题**: Plan 11 runner 侧实际发送**4 字段** payload (`token_hash` / `runner_id` / `agent_version` / `capabilities`); Plan 12 T7 v1 schema properties 只声明**3 字段** (`token_hash` / `runner_id` / `capabilities`), 遗漏 `agent_version`。而 schema 有 `additionalProperties: false` (line 456)。当 Plan 11 landed + arx 侧收 runner 发来 payload 走 v1 schema 验证时:
1. `agent_version` 不在 `properties` 里, `additionalProperties: false` → validation FAIL
2. 生产环境 enrollment 就此完全 broken; arx 侧 4XX response; runner 侧 error

**根因**: R1 H3 fix 只 rename 字段 (`token_sha256` → `token_hash`) 未 grep Plan 11 全部 payload 字段清单核对 shape。是**"改一处但未扫全 shape"** 反模式 — 与 lesson #14 / #33b Foundation Scan 分层展开精神相通 (fix 也需要 Foundation Scan iteration 覆盖影响面), 也是 lesson #37 spawner 元层 grep 实证在**编辑 spec 后再核对完整 shape** 层面的复现。

**关联 R1 review 遗漏**: R1 H3 finding 本身也只 focus 在字段名 rename, 没有列 "对齐 Plan 11 payload shape 全清单" 校对项。R2 是补做 — R1 reviewer (即我本人) 也应 own 此漏审。

**修法** (T7 executor 落地时必修):
1. `enrollment.schema.json` properties 补 `agent_version`:
   ```json
   "agent_version": { "type": "string", "maxLength": 64 }
   ```
2. `required` 是否含 `agent_version` — 参考 Plan 11 runner side (T4 Step 3 直接构造 4 字段 payload, 无 optional 语义) → 建议 `required: ["token_hash", "runner_id", "agent_version"]`; `capabilities` 保持 optional (Plan 11 line 319 显示 `capabilities: args.capabilities`, args 可能为空 list)
3. 4 其他 schema (`deployment_status` / `telemetry_snapshot` / `heartbeat`) 同 pattern 审查 — Plan 12 T7 line 461 只说 "3 schema 逐一对齐 `custos.rs:13-30` typed method 参数 + `nats_client.py` envelope", executor 落地时**必先 grep Plan 11 各 subcommand payload build 位置 + arx trait 参数**, 交叉对照; 不再单侧凭推理起 schema
4. `golden` fixture (`tests/fixtures/gateway_contract_v1_golden/`) 首次 land 时 golden = 修正后的 schema copy, 以保 backward-compat baseline 一开始就是完整 shape

**下游**: 若 executor 未察觉直接落地当前 schema, Plan 11 close-out CI 侧 integration test 会侥幸 pass (Plan 11 test 是 mock 断言 payload shape, 不跑 v1 schema 校验); Plan 12 T7 golden 也侥幸 pass (schema == golden)。真出问题在 arx-79 wire 侧真跑 payload validation 时。是**layer 2 static / layer 3 wire 联动缺口**, 与 lesson #40 精神一致 (code-level test 覆盖 ≠ runtime wire 兑现)。

---

### R2-M1 (MEDIUM) — Cross H4 fix 有 orphan delegation: docker mount pattern 在 `docs/ops/05-deployment.md` **无实际 owner**

**位置**:
- Plan 12 line 221 Cross H4 note: "`docs/ops/05-deployment.md` § Docker deployment 挂载 pattern (`docker run -v ~/.arx:/home/custos/.arx ...`) 由 Plan 11 T9 owner 承担 (Plan 11 已修改 `docs/ops/05-deployment.md`, Plan 12 T9 复检其含 docker mount 段而不追加 edit)"
- Plan 11 T9 File Inventory (line 493): "`docs/ops/05-deployment.md` — same substitution + add Upgrade from 0.1.x section detailing the manual re-enroll + re-vault-put steps"

**问题**: Plan 11 T9 对 `docs/ops/05-deployment.md` 的 scope 是 **(a)** `~/.custos/` → `~/.arx/` substitution + **(b)** Upgrade from 0.1.x section。**未涵盖** docker container mount pattern (Docker mount / VOLUME 用法说明 / 具体的 `docker run -v` 示例)。Plan 12 T2 line 221 note 假设 Plan 11 T9 owner 会写 docker mount 段, 但 Plan 11 T9 在 draft 状态无 Docker 上下文 (Plan 11 是 CLI clean-break, 无 Docker 关切)。Plan 12 T9 只做 inspection-only 复检 → docker mount 段**无 owner**。

**下游**: 生产用户按 `docs/ops/05-deployment.md` 部署时读不到 `docker run -v ~/.arx:/home/custos/.arx ...` 示例, 首次跑 `docker run custos-runner:v0.2.0 arx-runner enroll` 会因 volume 未挂载 → runner.toml 写入 ephemeral 层 → 容器重启后 vault 丢失 (Cross H4 finding 起因的场景复现)。

**修法** (二选一):
1. **Plan 12 T9 变从 inspection-only 升级为 append-only**: T9 §3 加一个 bullet 明说 "在 `docs/ops/05-deployment.md` 现有 Docker section 追加 mount pattern 段 (`docker run -v ~/.arx:/home/custos/.arx ghcr.io/the-alephain-guild/custos:v0.2.0 arx-runner enroll ...` 示例)"; 此 append 不与 Plan 11 T9 冲突 (Plan 11 T9 owner substitution + Upgrade section, Plan 12 T9 owner Docker mount pattern 段, 各占不同 section)。
2. **Plan 11 T9 File Inventory 扩展 scope**: 加一行 "在 `docs/ops/05-deployment.md` 新增 Docker deployment section 描述 `docker run -v` mount pattern" — 但 Plan 11 T9 draft 时无 Dockerfile 上下文, 需读 Plan 12 T2 现状。要求 Plan 11 T9 executor 主动 grep Plan 12 T2 Dockerfile 决策。**不推荐**此选项 (Plan 11 单会话完成期望的 scope 界限被扩)。

**建议采用选项 1** — Plan 12 T9 §3 加一 bullet 处理 docker mount pattern doc, 不再"复检 Plan 11 T9 输出"式假设 delegation。

---

### R2-M2 (MEDIUM) — Dockerfile `VOLUME /home/custos/.arx` 未 pre-`mkdir` + `chown`, non-root user 首次运行 mount 后可能无写权限

**位置**: Plan 12 line 237-244:
```dockerfile
RUN useradd -u 1000 -m -d /home/custos custos
ENV HOME=/home/custos
...
VOLUME ["/home/custos/.arx"]
USER 1000:1000
WORKDIR /opt/custos
```

**问题**:
1. `useradd -m -d /home/custos custos` 创建 `/home/custos` (owned by uid=1000 gid=1000)
2. **未** `mkdir -p /home/custos/.arx` + `chown custos:custos /home/custos/.arx` — `.arx` 子目录不存在
3. `VOLUME ["/home/custos/.arx"]` 声明 mount point, 但目录不存在, docker runtime mount 时会**自动创建 owned by root** (docker daemon behavior); 或者用户显式 `docker run -v /host/.arx:/home/custos/.arx` 时 mount 覆盖不存在的路径 → 挂载点 owned by host `.arx` owner
4. `USER 1000:1000` 后, 若 mount 后目录 owned by root, container 内 `arx-runner enroll` 尝试写 `/home/custos/.arx/runner.toml` → **permission denied**
5. 用户不加 `-v` 显式挂载时, 匿名 volume 权限一样是 root, 写入也会失败

**修法** (T2 executor 落地时必修): Dockerfile `USER 1000:1000` 前加一行:
```dockerfile
RUN mkdir -p /home/custos/.arx && chown -R custos:custos /home/custos
```

或用户体验更好的 pattern (支持 host mount + 匿名 volume):
```dockerfile
RUN install -d -o custos -g custos -m 0700 /home/custos/.arx
```

**下游**: 若不修, 生产用户跑 `docker run ghcr.io/.../custos:v0.2.0 arx-runner enroll` **首次即 fail**, image 全然不可用 — 与 R1 C2 (ENTRYPOINT `python -m custos` exit 2) 严重程度接近, 但触发场景更窄 (只在 arx-runner 尝试写 `.arx/` 时露)。`test_docker_entrypoint_help.py` 只测 `--help`, 不写文件, 抓不到; `verify-release.sh` `docker run --help` 也抓不到。

**FM 建议**: T2 tasks 加 test 或 verify-release.sh 加一步 `docker run --rm ... arx-runner enroll --dry-run` (若有 dry-run mode) 或至少 `docker run --rm ... sh -c 'touch /home/custos/.arx/probe && echo OK'`, 独立探针 mount + write 联合可用性。

---

## Positive observations (R2)

### P1 (R2) — 22/22 fix 全落地 + IMPROVEMENT 偏离日志逐条登记, 无静默偏离

Plan 12 line 577-597 IMPROVEMENT 表 22 行**每一行**对应 R1 一个 finding, 有 file:line 引用 + fix 描述 + 已批准状态。是 lesson #29 起 plan 前的**逆向应用** — Fix 完成后的 traceability 与"起 plan 前列 plan-to-plan 引用"对称, 审计员单 diff 即可核对 R1 → fix landed 的完整映射。

### P2 (R2) — 8 job DAG 命名精确到 hyphen level, 消除 R1 H5 内部矛盾

Plan 12 line 294 8 job 名 `build-wheel` / `sign-wheel` / `build-docker` / `sign-docker` / `publish-pypi` (optional flag) / `publish-ghcr` / `verify-release` / `release-notes` 全部小写-hyphen, 与 GitHub Actions job id 惯例一致, executor 落地 workflow YAML 时可 verbatim copy。且 optional flag 声明明说 `workflow_dispatch input` 或 `env var` (line 292), 避免"从哪读 flag"的模糊。

### P3 (R2) — Foundation Scan iteration 4 收拢 R1 M7 UNVERIFIED 到 arx-79 follow-up plan 明说 defer scope

Plan 12 line 620 iteration 4 明说 "contract 层单侧声明, 待 arx-79 wire close-out 补 'gateway contract v1 schema vs arx trait 双向反射对齐检' test", 加 "custos 独立仓库 clone 后无法本地 grep arx 源码" 的独立仓边界诚实说明。符合 lesson #40 close-out defer scope 精准化精神 (承诺"未来补"而非"当前已闭"), audit-non-silence 兑现。

---

## Handoff to execute-team

**Verdict**: **APPROVED for execute-team dispatch**, R2-C1 / R2-M1 / R2-M2 三项作为 Task-scope 内 follow-up 补丁 (不是新增 Task, 是既有 Task 落地时的 subtle refinement):

- **Task 2 executor**: R2-M2 补 `RUN mkdir -p /home/custos/.arx && chown -R custos:custos /home/custos` (放在 USER 指令前); 追加 verify-release.sh 内 mount+write 联合探针 (`docker run --rm ... sh -c 'touch /home/custos/.arx/probe'`)
- **Task 7 executor**: R2-C1 补 enrollment.schema.json `agent_version` 字段 + `required` 含 `agent_version`; 4 schema 全部再 grep Plan 11 各 subcommand payload build 位置 + arx trait 参数逐字对照 (不再单侧凭推理起 schema); golden fixture 首次 land 时 golden = 修正后的完整 schema copy
- **Task 9 executor**: R2-M1 §3 加一 bullet "在 `docs/ops/05-deployment.md` 现有 Docker section 追加 mount pattern 段 (`docker run -v ~/.arx:/home/custos/.arx ghcr.io/.../custos:v0.2.0 arx-runner enroll ...` 示例)"; 从 inspection-only 升级为 append-only 但仅限 Docker mount pattern 段 (不与 Plan 11 T9 substitution + Upgrade section 冲突)

**Merge conflict prevention** 复检: R2 三项均限本 plan 内 Task 内落地, 不引入新的跨 Plan 冲突面。Cross H5 SHA gate + serial merge protocol 保持不变。

**跨 R1 reviewer own-up**: R1 H3 finding 由本人 (claude) 起, 只关注 `token_sha256` → `token_hash` 字段名 rename, 未列 "full payload shape 对齐" 校对项 → R2-C1 是本人 R1 漏审的自我纠正 (lesson #C2 / #18 spawner 元层不豁免 复现). 记 owning: R1 reviewer 本人下一次评类似跨 plan boundary constant 类 finding 时, 建议**先列全 payload shape 字段清单 + 逐字段对照**, 不止关注问题字段 rename。

**Reviewer sign-off**: claude (Plan-team R2 reviewer, opus-4-7[1m])
**Report file**: `.forge/reviews/2026-07/12-plan-review-r2-claude.md`
