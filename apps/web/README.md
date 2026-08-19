# StackGraph Web (`@stackgraph/web`)

The StackGraph UI — a Next.js (App Router) app built on the Strata design system, bound to the
`contracts/v1` read models. Implements the plan in
[`docs/stackgraph-ux-architecture-and-plan.md`](../../docs/stackgraph-ux-architecture-and-plan.md).

## Run

From the repo root:

```bash
pnpm install
pnpm dev            # → http://localhost:3000
```

Regenerate Strata tokens after editing `docs/strata-design-tokens.json`:

```bash
pnpm tokens
```

Build / typecheck:

```bash
pnpm build
pnpm typecheck
```

## Fixture-first ⇄ live (one flag, no component rewrite)

The UI defaults to **fixtures** — every screen renders from `contracts/v1/fixtures/*` with no
backend running. To point at the live API:

```bash
# apps/web/.env.local
NEXT_PUBLIC_DATA_SOURCE=live
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
```

The swap happens entirely inside `@stackgraph/shared`'s API client
(`packages/shared/src/api/client.ts`); components never change. The live API currently exposes only
`/health/*` — read endpoints (`/estate/summary`, …) are pending on the backend. **CORS is not yet
enabled** on the API; the backend must allow the web origin before `live` mode works from the browser.

## What's implemented (Phase 0 + first Phase 1 slice)

- Monorepo: `apps/web`, `packages/design-system` (Strata), `packages/shared` (contract types + client),
  `packages/graph-ui` (stub for Phase 2).
- Strata token pipeline → CSS variables + typed exports (light/dark, reduced-motion, self-hosted IBM Plex).
- Three-region shell: top bar (Ask/⌘K stub, theme toggle, tenant), left rail (ontology nav + Reviews/Health/Admin),
  always-on status strip (coverage/evidence/as-of/contract).
- Trust primitives: `DomainBadge`, `ConfidenceChip`, `StatusStrip`, `StatTile`, `RankedTable`, `Skeleton`.
- **Software Estate** surface bound to `getEstateSummary` (ranked table, stat tiles, loading/empty/error states).
- **Application detail** (`/applications/[id]`) bound to `getApplication` (ontology breadcrumb, business context,
  assessments, recommendations).
- Placeholder routes for the remaining surfaces (Technologies, Modernization, Ask, Reviews, Health, Admin).

## Next (per plan §9)

Phase 1: Technology Explorer, Modernization Dashboard, Evidence Drawer, filters/lenses, virtualized tables,
run the 20-minute test on fixtures. Phase 2: `packages/graph-ui` (bounded graph lens), uncertain-bridge +
Reviews, Ask thread. Phase 3: flip to live, a11y/i18n/security/perf gates.
