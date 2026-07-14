# Custos runner contract v1

The current runner contract contains two local validation schemas:

- `enrollment.schema.json` for locally provisioned machine enrollment material;
- `deployment_spec.schema.json` for the validated execution view translated
  from a Crucible-signed canonical DeploymentSpec.

Production deployment publication is not a Custos CLI operation. Crucible
publishes `DeploymentSpecReadyForRunner` and
`DeploymentInstanceDesiredStateChanged`; Custos verifies exact subject, exact
event bytes, canonical digest, runner binding and instance binding.

`custos.contracts.DeploymentMessage` is the sole public decode seam for those
signed events. It accepts neither an unsigned ARX topic nor a locally produced
command envelope.

`deployment_spec.schema.json` is generated from
`custos.contracts.DeploymentSpec.model_json_schema()`. The canonical business
payload remains Crucible-owned; this schema covers only the narrow local engine
view after signature and digest verification.

Runner lifecycle observations use `RunnerDeploymentLifecycleFact.v1` through
the signed RunnerFact outbox. The outbox allocates `facts[].seq`; typed fact
builders are forbidden from supplying that field. There is no unsigned
business-topic compatibility schema or publication path.
