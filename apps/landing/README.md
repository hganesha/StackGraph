# StackGraph landing page

A standalone marketing page for StackGraph, deliberately separate from the product UI in
`apps/web`. No build step, no framework, no dependencies: a single self-contained
`index.html` with inline CSS and JS, plus IBM Plex from Google Fonts.

## Structure

The page is a scroll-driven narrative. One idea carries it: **the estate assembles itself
as you read**, which is the same layering metaphor the product uses (see
`docs/strata-design-language.md`).

| Section | Visual |
| --- | --- |
| Hero | Node field that grows outward as it loads |
| Cold open | Type, then the actor-mix bar that answers the story's own question |
| Thesis quote | Type only |
| `#discovery` | Sticky isometric stack; each scroll step adds one plane (repositories → code → dependencies → deployment → business → AI supply chain), with a camera pan that keeps the revealed stack centred. Hollow nodes on the sixth plane read as not-yet-collected |
| `#evidence` | Evidence card with `DECLARED` / `OBSERVED` / `INFERRED` / `EXTERNAL_MEASURED` rows, then a contradiction ledger holding three current claims with no winner declared |
| Function before package | SVG fan: observed symbols → inferred capability → scored candidates |
| Duplication | Evidence card for four implementations of one capability |
| `#shape` | Articulation-point diagram (two clusters joined through one node), metric grid, and a cohort/outlier/motif card |
| `#ecosystem` | Migration-pattern card (`axios → native fetch`) with aggregate counts |
| Viability | Multi-dimension scorecard, bars animate on reveal |
| `#impact` | Sticky ladder; a CVE walks up to a value chain stage, rung by rung |
| `#ask` | Question card: resolved entities, table rows, citation chips, limitations in the footer |
| `#portfolio` | Ranked modernization table plus the controlled action vocabulary |
| `#simulation` | Predicate vocabulary strip, a simulation plan with `DIRECT` / `TRANSITIVE` / `CONTEXT` / `STOP` findings, and the interpretation panel kept visibly separate |
| `#authority` | Capability envelope card with `READ` / `EXECUTE` / `CONDITIONAL` / `ESCALATE` / `PROHIBITED` bands and a constrained decision |
| Negative space | Architecture Canvas coverage grid with four cell states |
| `#start` | Close, CTAs, data-handling note, author byline |

Card row labels reuse one visual idiom: a typed label in the left column, the subject in the
middle, the value on the right, with an optional `.ev-foot` strip underneath. Adding a new
kind of row means adding a colour for its `data-c` value, not a new card.

## Design notes

- Colour comes from the Strata domain ramps in `packages/design-system/src/tokens/tokens.css`:
  enterprise slate, OSS teal, business amber, intelligence violet, danger red.
- Type is one superfamily in three roles. IBM Plex Sans for headings and UI, IBM Plex Serif
  for reading passages, IBM Plex Mono for anything that represents a machine-read fact.
  That mono/prose split is the same evidence-vs-reasoning convention the product uses.
- Light "paper" passages alternate with full-bleed night stages to pace the read.
- Every animation is entry-only and `prefers-reduced-motion` aware. Nothing loops.

## Provider neutrality

Connector copy is deliberately host-agnostic ("read-only repository access", "your repository
host") so the page does not need rewriting when GitLab and Bitbucket land alongside GitHub. The
one remaining "GitHub Actions" string is inside the Architecture Canvas grid, where it is sample
data describing what the fictional customer runs, not a claim about connector support.

## Content accuracy

Copy is drawn from `docs/stackgraph-specs.md`, `docs/product-ai-addendum-for-ingestion.md`,
`docs/stackgraph-architecture-canvas-spec.md`, `docs/stackgraph-insight-catalog-expansion.md`,
`docs/phase-2-plan.md`, `docs/estate-fidelity-contracts.md`, and
`docs/graph-and-embeddings-features.md`.

Every capability the page claims is backed by an operation in
`stackgraph-foundation/contracts/v1/openapi.json`. The vocabularies shown are the real ones:
the six change predicates, the five simulation finding classifications, the five capability
bands, the four envelope decisions, the six estate strata, and the ten modernization actions.
Numbers in the visuals are illustrative sample data, not measured results.

## Local preview

```sh
python3 -m http.server 4321 --directory apps/landing
```

## Deploying

The page is a single static file. Serve `apps/landing/` from any static host or CDN.

**Before shipping:** the three "Connect a repository" CTAs (masthead, hero, `#start`) are
`<button disabled>` on purpose while sign-up is unavailable. To turn them on, swap each back to
an anchor pointing at the sign-up flow. `Read the specification` in `#start` is still an
`href="#"` placeholder.
