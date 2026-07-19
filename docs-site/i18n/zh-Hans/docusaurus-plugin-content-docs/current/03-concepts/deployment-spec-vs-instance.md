---
title: "DeploymentSpec vs DeploymentInstance"
sidebar_position: 1
---

<!-- source: docs/domain.md §Core terms -->

# DeploymentSpec vs DeploymentInstance

:::warning 🔄 中文翻译进行中 · PLAN 20 T6
本章中文正文将在 Plan 20 T6 完成。当前显示英文占位。
:::

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
