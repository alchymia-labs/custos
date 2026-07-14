# Custos domain model

**Status:** authoritative for the Custos execution boundary.

## Bounded context

Custos owns local execution mechanics only:

- runner enrollment material and local machine credentials;
- verification of Crucible-signed commands;
- reconciliation of desired deployment state into a local engine;
- process supervision, watchdogs and local safety circuit breakers;
- signing and publishing observed runner facts.

Custos does not own actor authorization, approval workflows, strategy or risk
configuration, promotion decisions, portfolio truth, settlement truth or the
canonical deployment lifecycle.

## External authorities

| Authority | Owns | Custos treatment |
| --- | --- | --- |
| ARX | actor identity, session, role and capability authorization | no direct deployment dependency |
| Crucible | business state, approvals, DeploymentSpec, DeploymentInstance and canonical facts | verifies signed commands and returns signed observations |
| Custos | local process and machine observations | authoritative only for what happened on this runner |

## Core terms

### DeploymentSpec

An immutable business-owned configuration. deployment_spec_id and
deployment_spec_digest are provenance. The spec includes strategy artifact
provenance, mode, target runner, credential scope, parameters and, for live
mode, promotion evidence.

### DeploymentInstance

One attempt to run a DeploymentSpec on a runner. deployment_instance_id is
the runtime primary key. Retries, redeployments and parallel instances of the
same spec have distinct instance identifiers.

### Desired generation and local watermarks

A monotonic integer attached to a signed desired-state command. Custos tracks
applied_generation separately from reported_generation. A fact enqueue failure
therefore retries reporting without repeating a successful engine action.

### Engine handle

The local engine resource for one deployment instance. All engine protocol
operations receive deployment_instance_id; the spec identifier is retained
only as provenance in facts and diagnostics.

### RunnerFact

A signed observation emitted by Custos. A fact states what this runner
observed or executed. It is not itself the canonical business lifecycle;
Crucible validates and persists it before changing canonical state.

## Invariants

1. A command is processed only after exact-byte and exact-subject signature verification.
2. Tenant, mode, runner and instance in the subject, envelope and payload must agree.
3. Runtime state is keyed only by deployment_instance_id.
4. A DeploymentSpec cannot silently cross paper/live boundaries.
5. Live execution fails closed without signed promotion evidence.
6. Invalid signed commands are terminally acknowledged and audited; transient local apply failures are retried.
7. Custos never fabricates an approval, promotion or business fact.
