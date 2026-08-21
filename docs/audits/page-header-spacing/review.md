# Page header spacing review

## Outcome

- Added the missing `--sg-space-5` token (`20px`) used by Admin and other feature-owned layouts.
- Standardized the global `h1` line height on `--sg-type-h1-line` (`32px`).
- Removed the one-off Admin eyebrow so its page title shares the standard workspace baseline.
- Preserved Business Map as a canvas-toolbar layout; it intentionally has no page-title `h1`.

## Browser measurements

The primary workspace routes now render their page titles at `top: 76px`, `height: 32px`, and `line-height: 32px`:

- Applications
- Technologies
- Modernization
- Ask
- Reviews
- Estate Health
- Software Estate
- Admin

Admin panel spacing now resolves as intended:

- Page gap: `20px`
- Panel header padding: `16px 20px`
- Page-title baseline: `76px`

## Verification

- `pnpm --filter @stackgraph/web typecheck`
- `NEXT_PUBLIC_DATA_SOURCE=fixtures pnpm --filter @stackgraph/web build`
- `git diff --check`
