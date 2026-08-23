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
| Cold open, thesis quote | Type only |
| `#discovery` | Sticky isometric stack; each scroll step adds one plane (repositories → code → dependencies → deployment → business), with a camera pan that keeps the revealed stack centred |
| `#evidence` | Evidence card with `DECLARED` / `OBSERVED` / `INFERRED` / `EXTERNAL_MEASURED` rows and a confidence indicator |
| Function before package | SVG fan: observed symbols → inferred capability → scored candidates |
| Duplication | Evidence card for four implementations of one capability |
| `#ecosystem` | Migration-pattern card (`axios → native fetch`) with aggregate counts |
| Viability | Multi-dimension scorecard, bars animate on reveal |
| `#impact` | Sticky ladder; a CVE walks up to a value chain stage, rung by rung |
| `#portfolio` | Ranked modernization table plus the controlled action vocabulary |
| Negative space | Architecture Canvas coverage grid with four cell states |
| `#start` | Close, CTAs, data-handling note, author byline |

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
`docs/stackgraph-architecture-canvas-spec.md`, and `docs/stackgraph-insight-catalog-expansion.md`.
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
