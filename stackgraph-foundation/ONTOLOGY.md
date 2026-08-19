# Canonical Ontology

## Business graph
`Organization -> BusinessUnit -> ValueChain -> BusinessFunction -> BusinessProcess -> BusinessCapability`

Primary links:
- `ValueChain CONTAINS BusinessFunction`
- `BusinessFunction CONTAINS BusinessProcess`
- `BusinessProcess REQUIRES BusinessCapability`
- `BusinessProcess ENABLED_BY Application`
- `BusinessCapability PROVIDED_BY Application|Service|Component`

## Enterprise graph
`Application -> Service -> Component -> Repository`

Primary links:
- `Application IMPLEMENTED_BY Repository`
- `Application DEPENDS_ON Application|Service`
- `Service CALLS Service`
- `Service EXPOSES API`
- `Repository USES Technology`
- `Repository DEPENDS_ON Package`

## Deployment graph
`Application -> Deployment -> ComputeTarget -> CloudProvider/OnPrem`

Primary links:
- `Application DEPLOYED_AS Deployment`
- `Deployment RUNS_ON ComputeTarget`
- `Deployment HOSTED_IN CloudProvider|OnPrem`
- `Deployment LOCATED_IN Region`
- `Deployment USES Database|InfrastructureResource`
- `Deployment CONNECTS_TO InfrastructureResource`

Declared deployment and observed deployment must remain distinguishable.

## OSS graph
The OSS graph is first-class, not an enrichment appendix.

Core entities:
- `OSSProject`
- `OSSRepository`
- `Package`
- `PackageVersion`
- `Release`
- `License`
- `Maintainer`
- `Technology`
- `Capability`
- `ReferenceImplementation`
- `MigrationPattern`
- `Vulnerability`

Primary relationships:
- `OSSProject PUBLISHES Package`
- `Package HAS_VERSION PackageVersion`
- `PackageVersion DEPENDS_ON PackageVersion`
- `OSSProject MAINTAINED_BY Maintainer`
- `OSSProject HAS_RELEASE Release`
- `OSSProject USES_LICENSE License`
- `Technology|Package PROVIDES BusinessCapability/technical Capability`
- `Technology ALTERNATIVE_TO Technology`
- `Technology COMMONLY_USED_WITH Technology`
- `Technology MIGRATED_TO Technology`
- `ReferenceImplementation DEMONSTRATES Capability|ArchitecturePattern`
- `PackageVersion AFFECTED_BY Vulnerability`

`Package`, `Technology`, `Runtime`, `Framework` and `Capability` are bridge concepts between enterprise and OSS observations.

## Intelligence
Actions:
`RETAIN | UPGRADE | REMOVE | REPLACE | CONSOLIDATE | REFACTOR | REBUILD | REPLATFORM | RETIRE | INVESTIGATE`

Assessment dimensions should include:
- supportability
- security
- maintenance health
- ecosystem health
- runtime compatibility
- functional fit
- architecture fit
- organizational alignment
- performance opportunity
- dependency complexity
- replaceability
- deployment viability
- business criticality

## Evidence classes
- `DECLARED` — explicit in a manifest/configuration.
- `OBSERVED` — referenced in source/runtime observation.
- `INFERRED` — derived from multiple signals.
- `CURATED` — imported from a human-curated knowledge source.
- `EXTERNAL_MEASURED` — measured from public ecosystem sources.

## Recommendation rule
Never ask “what package replaces X?” first.
Resolve:
`current technology -> capability actually used -> candidate implementations -> compatibility/viability -> organizational fit -> migration evidence -> recommendation`.
