# Authority documents

The machine-readable authority manifest is `authority-manifest.json`. Its
required authority snapshot is repository-local at
`docs/authority/ecosystem-authority.json`, so a standalone clone can run the
gate. Workspace authority documents are optional alignment inputs only.

Precedence:

1. ecosystem data ownership;
2. migration rollout and physical database contract;
3. ecosystem domain model;
4. ecosystem architecture;
5. accepted ADRs;
6. local Custos domain and protocol documents.

Custos owns local execution and signed observations only.
deployment_instance_id is the runtime key. ARX authorization and Crucible
business decisions must not be reimplemented in the runner.

`docs/design/strategy-toolkit.md` and the source-generated schemas indexed by
`docs/authority/strategy-contract-assets-v1.json` are authoritative for the
Custos execution ABI and artifact verifier. Philosophers-Stone produces the
canonical release BOM; Crucible owns StrategyRelease and artifact selection.
The `Custos Plan 18 Task 2 schema receipt` is usable only when READY with exact
producer, review, asset-digest, and fresh authority-check evidence.

Run make check-authority after changing ownership or protocols.
