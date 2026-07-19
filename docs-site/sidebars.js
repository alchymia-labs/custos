// @ts-check
// custos docs sidebar — 46 chapters across 10 Parts
// Content: Plan 20 T5 migrates from docs/**.md; T6 translates to zh-Hans.

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  main: [
    {
      type: 'category',
      label: 'I · Overview',
      collapsed: false,
      collapsible: true,
      items: [
        '01-introduction/what-is-custos',
        '01-introduction/trust-model',
        '01-introduction/architecture-at-a-glance',
      ],
    },
    {
      type: 'category',
      label: 'II · Getting Started',
      items: [
        '02-getting-started/installation',
        '02-getting-started/enrollment',
        '02-getting-started/first-sandbox-run',
        '02-getting-started/first-deployment-spec',
      ],
    },
    {
      type: 'category',
      label: 'III · Core Concepts',
      items: [
        '03-concepts/deployment-spec-vs-instance',
        '03-concepts/trading-modes',
        '03-concepts/g6-host-gate',
        '03-concepts/reconcile-loop',
        '03-concepts/runner-fact',
      ],
    },
    {
      type: 'category',
      label: 'IV · Operator Guide',
      items: [
        '04-operator-guide/deployment',
        '04-operator-guide/credential-vault',
        '04-operator-guide/readiness-health',
        '04-operator-guide/runtime-log-observability',
        '04-operator-guide/emergency-playbook',
        '04-operator-guide/troubleshooting',
      ],
    },
    {
      type: 'category',
      label: 'V · Non-Custodial Trust Model',
      items: [
        '05-trust-model/red-lines',
        '05-trust-model/rl1-key-kek-never-leaves',
        '05-trust-model/rl2-g6-gate-cannot-bypass',
        '05-trust-model/rl3-reconcile-disconnect',
        '05-trust-model/rl4-decimal-money-math',
        '05-trust-model/signed-release-chain',
        '05-trust-model/audit-checklist',
      ],
    },
    {
      type: 'category',
      label: 'VI · Integration Guide',
      items: [
        '06-integration/gateway-contract-v1',
        '06-integration/signing-deployment-spec',
        '06-integration/consuming-runner-fact',
        '06-integration/contract-versioning',
        '06-integration/reference-implementations',
      ],
    },
    {
      type: 'category',
      label: 'VII · Engines',
      items: [
        '07-engines/nautilus-trader',
        '07-engines/noop',
        '07-engines/engine-roadmap',
      ],
    },
    {
      type: 'category',
      label: 'VIII · Strategy Toolkit',
      items: [
        '08-toolkit/overview',
        '08-toolkit/artifact-signing',
        '08-toolkit/registry-mode-loading',
      ],
    },
    {
      type: 'category',
      label: 'IX · Reference',
      items: [
        '09-reference/cli',
        '09-reference/configuration',
        '09-reference/json-schema',
        '09-reference/nats-subjects',
      ],
    },
    {
      type: 'category',
      label: 'X · Release & Governance',
      items: [
        '10-release-governance/semver-lts',
        '10-release-governance/upgrade-paths',
        '10-release-governance/security-policy',
        '10-release-governance/contributing',
        '10-release-governance/license',
        '10-release-governance/changelog',
      ],
    },
  ],
};

module.exports = sidebars;
