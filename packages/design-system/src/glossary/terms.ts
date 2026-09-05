/**
 * StackGraph's vocabulary, defined once.
 *
 * Every definition is written in terms of the product's own model — entities,
 * relationships, facts, evidence, domains — rather than as a generic gloss. A reader
 * who follows two or three of these should come away understanding how the graph is
 * put together, not just what one word means.
 *
 * `body` answers "what is this". `note` answers "and what should I do about it", and
 * appears only where a term is routinely misread.
 */
export interface GlossaryEntry {
  term: string;
  body: string;
  note?: string;
}

export const GLOSSARY = {
  // ── The graph itself ───────────────────────────────────────────────────────
  estate: {
    term: "Estate",
    body:
      "Every entity StackGraph has discovered across your connected repositories — applications, repositories, services, technologies, deployments — and the relationships between them.",
  },
  entity: {
    term: "Entity",
    body:
      "One thing in the graph: an application, a repository, a technology, a deployment. Entities are joined by relationships, and both are built from facts.",
  },
  relationship: {
    term: "Relationship",
    body:
      "A connection between two entities — an application depends on a technology, a repository belongs to an application. Relationships carry evidence and confidence just as entities do.",
  },
  fact: {
    term: "Fact",
    body:
      "A single statement read out of a scan, keeping a pointer to the file and line it came from. Entities and relationships are assembled from facts.",
  },
  evidence: {
    term: "Evidence",
    body:
      "The fact behind a statement, and the source it was read from. Every claim on screen links back to at least one.",
    note: "If something here looks wrong, open its evidence — that is where the answer is.",
  },
  domain: {
    term: "Domain",
    body:
      "One of the six layers the graph is organised into: Business, Enterprise, Technology, OSS, Deployment, and Intelligence.",
  },

  // ── How strongly something is known ────────────────────────────────────────
  declared: {
    term: "Declared",
    body: "Read from something your team wrote — a manifest, a lockfile, a configuration file.",
  },
  observed: {
    term: "Observed",
    body: "Seen in the built or running system, rather than only declared in a file.",
  },
  inferred: {
    term: "Inferred",
    body:
      "Worked out by StackGraph from other facts. Always carries a confidence and is never presented as certain.",
  },
  curated: {
    term: "Curated",
    body: "From StackGraph's own reviewed technology catalog, rather than from your estate.",
  },
  confidence: {
    term: "Confidence",
    body:
      "How directly the evidence supports a claim. High is 85% or above, medium 60% or above, low below that.",
  },
  freshness: {
    term: "Freshness",
    body:
      "How recently the evidence was last confirmed. Stale means the scan behind it is older than its refresh budget — the claim may still hold, but nothing has checked lately.",
  },

  // ── The architecture canvas ────────────────────────────────────────────────
  concern: {
    term: "Concern",
    body:
      "One job a stack has to do — storing records, routing requests, running tests. The canvas is a fixed grid of them, so the same picture can be filled from any application or from the whole estate.",
  },
  referenceModel: {
    term: "Reference model",
    body:
      "StackGraph's canonical list of concerns and what counts as addressing each one. It supplies the frame; your profile fills it in.",
  },
  posture: {
    term: "Posture",
    body:
      "A summary of how healthy one area looks, combining coverage, standardisation, currency, risk, and conformance.",
    note: "Areas without enough evidence are left unscored rather than guessed at.",
  },
  drift: {
    term: "Drift",
    body: "Where what you actually run differs from the standard you set.",
  },
  placement: {
    term: "Placement",
    body:
      "The reason a technology appears in a particular area — the capability or resource it was found providing. One technology can legitimately appear in several areas.",
  },

  // ── Canvas cell states ─────────────────────────────────────────────────────
  noneFound: {
    term: "None found",
    body: "StackGraph checked everywhere it could and found nothing here.",
    note: "A genuine gap — different from not having looked.",
  },
  notObserved: {
    term: "Not observed",
    body:
      "StackGraph could not check: a scan is missing, stale, or this ecosystem is not yet supported.",
    note: "A gap in what we can see, not in your estate. Never counted against you.",
  },
  notModelled: {
    term: "Not yet modelled",
    body: "StackGraph has no way to detect this yet.",
    note: "A limitation of the tool, not a finding about your estate.",
  },

  // ── Graph intelligence ─────────────────────────────────────────────────────
  blastRadius: {
    term: "Blast radius",
    body:
      "Everything that would be affected if this entity failed or disappeared, found by following relationships outward from it. Each affected entity keeps the path and the facts that connect it back.",
    note: "A reachability result, not a prediction. It says what depends on this, not what would actually break.",
  },
  systemicRisk: {
    term: "Systemic risk",
    body:
      "How much of the estate rests on one entity, scored from its position in the graph — how many things reach it, how many dependency paths run through it, and whether removing it would split the graph.",
    note: "Signals StackGraph cannot see for your estate are left out and the rest rescaled, so a score always says which signals it used.",
  },
  articulationPoint: {
    term: "Single point of failure",
    body:
      "An entity whose removal would split the graph into pieces that can no longer reach each other. Also called an articulation point.",
    note: "Structural, not operational. It describes the shape of your dependencies, not the reliability of the thing itself.",
  },
  community: {
    term: "Community",
    body:
      "A group of entities that reach each other through dependencies but barely connect to anything outside the group. Found by algorithm from the graph's shape alone.",
    note: "Not a team, an owner, or a business domain. Two applications land in one community because they share dependencies, not because anyone decided they belong together.",
  },
  centrality: {
    term: "Centrality",
    body:
      "How important an entity's position is in the graph. PageRank counts how much depends on it, weighted by how much depends on those things in turn; betweenness counts how often the shortest path between two other entities runs through it.",
  },
  analysisSnapshot: {
    term: "Analysis snapshot",
    body:
      "One complete run of the graph analysis, frozen. Every metric, path, and ranking on screen is read from a snapshot rather than recalculated, so numbers shown together were computed together.",
    note: "The snapshot's age is how current the structural picture is — separate from the freshness of the underlying scans.",
  },
  embeddingSpace: {
    term: "Embedding space",
    body:
      "A versioned set of numeric representations of your entities, used to find candidates by meaning rather than by exact match. A new space stays in shadow until its coverage and reviewed relevance are good enough to replace the active one.",
    note: "Used to retrieve and rank candidates. Never used as proof that two things are related.",
  },
  semanticSimilarity: {
    term: "Semantic similarity",
    body:
      "How close two entities are in an embedding space — a suggestion that they may serve the same purpose, drawn from their descriptions, dependencies, capabilities, and technologies.",
    note: "A starting point for a human decision, never a conclusion. Always read what the two share and what differs before acting.",
  },

  // ── Reading a picture ──────────────────────────────────────────────────────
  spread: {
    term: "Spread",
    body:
      "How many different ways one business capability is implemented across the applications behind it. Low spread means one way of doing the job; high spread means the same job is being done several different ways at once.",
    note:
      "Computed as technology entropy over the capability's footprint. High spread is not automatically wrong — it is the cost of every future change to that capability, stated in advance.",
  },
  reuseSignal: {
    term: "Reuse",
    body:
      "How much of a capability is built on things already used elsewhere in the estate, rather than rebuilt for it.",
  },
  attenuation: {
    term: "Attenuation",
    body:
      "How a finding narrows as each class of evidence is applied: present in a lockfile, then referenced in code, then reachable, then seen at runtime, then deployed, then in production, then internet-facing, then behind a business-critical capability.",
    note:
      "The drop between stages is the point. A stage nobody checked is shown as unchecked, never as zero — those are different facts.",
  },
  corroboration: {
    term: "Corroboration",
    body:
      "How many independent sources agree on one relationship — a generated client, a reference in source, observed traffic, an architecture document. Shown as one to four stacked hairlines beside the claim.",
    note:
      "Four agreeing sources is a materially stronger claim than one. Where the mark is absent, the number is a direct count rather than something inferred from sources.",
  },
  stratum: {
    term: "Estate layers",
    body:
      "The five layers the estate is stacked in — Business over Enterprise over Technology over OSS over Deployment — drawn as five bands, each filled to how much of that layer is populated and evidenced.",
    note:
      "Where a band is hatched, nothing measures that layer yet. That is a gap in what we can report, not a finding about your estate.",
  },

  // ── Blocking and identity ──────────────────────────────────────────────────
  gate: {
    term: "Gate",
    body:
      "Something standing between you and a change: a subject that could not be resolved, a contradiction between two sources, or an approval that has not been given. A gate always names what is in the way and links to its evidence.",
    note:
      "A gate is not a warning. Warnings can be read past; a gate cannot be dismissed, and the control it governs stays disabled until it clears.",
  },
  resolution: {
    term: "Resolution",
    body:
      "Whether StackGraph knows exactly which thing in your estate you meant. Resolved means one match; inferred means several, and you choose; unresolved means nothing in your estate matches.",
    note:
      "Not the same as confidence. Something can be resolved beyond doubt and still rest on a weak fact, or be ambiguous between two things that are each well evidenced.",
  },

  // ── Governance ─────────────────────────────────────────────────────────────
  governed: {
    term: "Governed",
    body: "Someone has recorded a decision about which technologies are allowed in this area.",
  },
  ungoverned: {
    term: "Ungoverned",
    body: "No decision has been recorded for this area yet.",
    note: "Never reported as a violation. It means nobody has ruled, not that something is wrong.",
  },
  preferred: {
    term: "Preferred",
    body: "The technology your standard says teams should reach for here.",
  },
  discouraged: {
    term: "Discouraged",
    body: "Permitted for now, but your standard says to move away from it.",
  },
  prohibited: {
    term: "Prohibited",
    body: "Your standard says this must not be used here. Prohibited always overrides an allowlist.",
  },
  exempted: {
    term: "Exempted",
    body:
      "Not normally allowed here, but covered by a written, time-boxed exception naming the applications it applies to.",
  },
  profile: {
    term: "Architecture profile",
    body:
      "Your workspace's standard: which concerns apply, how many implementations each should have, and which technologies are preferred, allowed, discouraged, or prohibited. Published as numbered revisions.",
  },
  fingerprint: {
    term: "Fingerprint",
    body:
      "A short checksum identifying an exact version of something, so two people can confirm they are looking at the same thing.",
  },
} as const satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
