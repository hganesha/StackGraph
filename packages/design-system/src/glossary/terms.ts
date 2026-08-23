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
