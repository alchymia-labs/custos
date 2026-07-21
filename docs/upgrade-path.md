# Custos first-production V1 bootstrap

This release has no external production consumer and therefore no runtime
compatibility matrix. The current contract is the sole first-production V1.

1. Rebuild local SQLite state and Crucible databases at the current migration
   heads. Old source-path DeploymentSpec rows are not migrated by Custos.
2. Install the exact Custos runtime image and toolkit wheels named by the
   immutable release receipt.
3. Provision the runner's machine identity, local NKey/JWT/TLS transport and
   per-scope vault records.
4. Configure the Crucible command producer key and authenticated
   StrategyRelease resolver authority.
5. Start with reconcile disabled until all producer/consumer receipts are
   exact-byte complete. A blocked resolver must fail readiness, never select a
   local source or unsigned command.
6. Enable sandbox/testnet acceptance, then live only after the same image digest
   has CR90B and PS56 receipts and the signed runner safety policy is active.

Git history and immutable OCI digests provide audit for pre-production shapes.
Runtime code contains no V2/V3 parser, dual-read, cutover table or fallback.
A future V2 requires a real external production consumer and a documented
migration window.
