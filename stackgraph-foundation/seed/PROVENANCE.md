# Curated seed provenance

The versioned seed is a curated bootstrap dataset, not live ecosystem truth. The original working document named
`framework-landscape-2026.md` is not distributed with this repository. Its immutable fingerprint and line count
are retained in `seed-manifest.json`; the loss of the source document is explicit rather than silently replaced
with a reconstructed file.

`source-rows.json` is the durable row-level evidence retained by StackGraph. Each hydrated technology record
preserves its source-row key, source line, original text, curation class, and the seed version that produced it.
The files `technologies.json`, `categories.json`, `capabilities.json`, `relationships.json`, and
`assessments.json` are deterministic materializations of those retained rows.

`oss-core.json` is a separately reviewed overlay for package-level classification. It records its own source
identifier and review date, adds package aliases and package-family patterns, and may refine the classification
of a base landscape record without changing the preserved `source-rows.json` evidence. Seed facts created from
these additions and refinements cite `oss-core.json` as their locator.

Before any seed record is promoted into production identity or used as a measured signal, it must have:

1. an atomic product/project/package identity rather than a comparison group;
2. a durable public source URL or internal evidence reference;
3. an observation or effective date;
4. a curator and review state; and
5. a current external observation that can supersede the curated hypothesis.

Compound comparison groups remain visible as curated provenance only. Enrichers must create atomic canonical
entities and explicit `CONTAINS`, `SAME_AS`, or package/project identity assertions instead of treating a group
label as a deployable technology.
