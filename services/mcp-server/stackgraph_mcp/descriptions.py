"""Human-written context layered on top of the generated contract.

The contract's ``summary`` fields are title-cased operation ids ("Get Estate Summary")
and it carries no operation descriptions at all, so tools built purely from the spec
read as opaque. Everything here exists to tell an agent *when* to reach for a tool.
"""

from __future__ import annotations

SERVER_INSTRUCTIONS = """\
StackGraph models an enterprise software estate as an evidence-backed graph:
Business -> Applications -> Code -> Technology -> Dependencies -> Deployment ->
Infrastructure -> OSS ecosystem -> Viability -> Modernization actions.

Every tool here is one operation of the StackGraph v1 API contract. Tool names are
`stackgraph_<operation>` in snake_case.

Getting oriented:
- `stackgraph_list_operations` filters the tool catalog by toolset or keyword.
- `stackgraph_describe_operation` returns the full request and response JSON Schema
  for one operation. Call it before sending a request body you are unsure about.
- `stackgraph_get_estate_summary` is the usual starting point for estate questions;
  `stackgraph_ask_estate` answers natural-language questions over the estate.

Identifiers: entities, repositories, applications, technologies and review candidates
are addressed by UUID. Obtain ids from a list or search operation rather than guessing.

Capabilities: the caller's principal holds a capability on the ladder
view -> review -> execute -> admin. Operations under `/admin/*` require `admin`;
review and canvas comparison operations require `review`. A 403 means the configured
token is below the required rung, not that the request was malformed.

Claims returned by StackGraph carry confidence and evidence. When reporting a finding,
prefer `stackgraph_get_fact_evidence` to cite the evidence behind it.
"""

TOOLSET_SUMMARIES: dict[str, str] = {
    "admin": "Tenant administration: members, connectors, GitHub wiring, scan policy, AI provider configuration, and governance.",
    "applications": "Application read models.",
    "architecture-canvas": "Architecture canvas projections, reference models, taxonomy, templates, and current-vs-target comparisons.",
    "authentication": "OIDC login, callback, refresh, and logout.",
    "business-map": "Business capability maps: create, read, save, archive, and revision history.",
    "embeddings": "Semantic search, embedding status, backfills, and embedding-space promotion.",
    "estate": "Top-level estate summary counts and posture.",
    "evidence": "Evidence supporting an individual fact or claim.",
    "graph": "Raw graph neighborhood traversal around a center entity.",
    "graph-intelligence": "Derived graph structure: communities, motifs, anomalies, risks, blast radius, and critical edges.",
    "identity": "Identity assertion review.",
    "intelligence": "Natural-language estate questions, modernization opportunities and scenarios, deterministic insights, and enterprise reports.",
    "operations": "Liveness and readiness probes.",
    "repositories": "Repository read models, capabilities, and modernization intelligence.",
    "reviews": "The cross-cutting human review queue.",
    "session": "The current principal, tenant, and capabilities.",
    "technologies": "Technology detail and the technology estate hierarchy.",
    "other": "Operations the contract left untagged.",
}

# Operations whose HTTP verb is POST but which compute a result without changing state.
READ_ONLY_POST_OPERATIONS: frozenset[str] = frozenset(
    {
        "askEstate",
        "compareCanvasProjections",
        "optimizeModernizationScenario",
        "semanticSearch",
    }
)

# Curated descriptions for the operations an agent is most likely to need. Anything
# absent falls back to a description synthesised from the contract.
OPERATION_DESCRIPTIONS: dict[str, str] = {
    "askEstate": (
        "Answer a natural-language question about the software estate. Returns a grounded "
        "answer with the facts and evidence it was derived from. Use this to start an "
        "open-ended investigation; use the specific read models once you know what to look up. "
        "Rate limited separately from other operations."
    ),
    "getEstateSummary": (
        "Top-level counts and posture for the whole estate: applications, repositories, "
        "technologies, and outstanding modernization signal. The usual first call when "
        "answering 'what does this estate look like'."
    ),
    "semanticSearch": (
        "Vector search across estate entities by meaning rather than exact text. Use it to "
        "find applications, repositories or technologies matching a described function when "
        "you do not know their names."
    ),
    "getSession": (
        "The current principal: actor, tenant, and capabilities. Call this first when an "
        "operation returns 403 to confirm which rung of the capability ladder the token holds."
    ),
    "getGraphNeighborhood": (
        "Traverse the estate graph outward from one entity, up to depth 2. Filter by predicate, "
        "namespace, and minimum confidence to keep the result readable. Use this to answer "
        "'what does X depend on' and 'what touches X'."
    ),
    "getEntityBlastRadius": (
        "What breaks if this entity changes or fails: the downstream set reachable from it, "
        "weighted by criticality. Use for change-risk and incident-impact questions."
    ),
    "listEntityCriticalEdges": (
        "The dependency edges that carry the most risk for one entity - single points of "
        "failure and chokepoints in its neighborhood."
    ),
    "listSimilarApplications": (
        "Applications whose capability profile resembles this entity's. Use to find duplicated "
        "implementations of the same business capability across the estate."
    ),
    "listModernizationOpportunities": (
        "Ranked modernization opportunities across the estate, each with business importance, "
        "technical viability, effort, and confidence. The entry point for 'where should we invest'."
    ),
    "optimizeModernizationScenario": (
        "Optimise a modernization portfolio under constraints (budget, capacity, risk appetite) "
        "and return the selected opportunities. Computes a scenario; does not commit anything."
    ),
    "getRepositoryModernizationIntelligence": (
        "Everything StackGraph knows about one repository's modernization posture: technology "
        "viability, detected duplication, recommended action, and the evidence behind each."
    ),
    "getTechnologyEstateHierarchy": (
        "The estate's technology tree - languages, runtimes, frameworks, packages, databases and "
        "infrastructure - with usage counts. Use to answer 'what are we built on'."
    ),
    "listDeterministicInsights": (
        "Rule-derived insights that do not depend on a model: reproducible findings with the rule "
        "key and evidence that produced them."
    ),
    "getFactEvidence": (
        "The evidence records backing one fact: source repository, file, commit, and extraction "
        "method. Use this to cite a claim rather than asserting it."
    ),
    "getReviewQueue": (
        "The cross-cutting queue of inferences awaiting human review - capability inferences, "
        "identity assertions, similarity candidates, and modernization recommendations."
    ),
    "getCanvasProjection": (
        "Project the estate onto an architecture canvas: entities placed into architectural "
        "layers and domains. Pair with getTargetCanvasProjection and compareCanvasProjections "
        "to show current versus target state."
    ),
    "getGraphIntelligenceStatus": (
        "Freshness of the derived graph-intelligence products. Check this before trusting "
        "communities, motifs, anomalies or risks - they may predate the latest ingestion."
    ),
    "listBusinessMaps": (
        "Business capability maps for the tenant. A map is the editable business-side model that "
        "estate entities are attached to."
    ),
    "getEmbeddingStatus": (
        "Coverage and freshness of estate embeddings. Low coverage means semanticSearch and "
        "listSimilarApplications will miss entities."
    ),
    "live_health_live_get": "Liveness probe. Returns immediately if the API process is up.",
    "ready_health_ready_get": (
        "Readiness probe covering database, graph store, and dependent services. Call this first "
        "when other operations fail with 5xx."
    ),
}

# Toolsets excluded unless explicitly requested: browser-driven OIDC flows cannot be
# completed by an agent, and exposing them only invites dead-end calls.
DEFAULT_EXCLUDED_TOOLSETS: frozenset[str] = frozenset({"authentication"})
