# StackGraph app icon

Vector rebuild of the StackGraph icon — three isometric layers (the **Enterprise**,
**Intelligence**, and **OSS** domain graphs) feeding a column of nodes, with a dashed
**danger-signal** connector to a warning node. Colors are drawn from the design-system
tokens (`packages/design-system/src/tokens/tokens.css`) so the icon stays on-brand.

| Element        | Token                         | Value     |
| -------------- | ----------------------------- | --------- |
| Blue layer     | `--sg-color-domain-enterprise-500`   | `#4A6FA5` |
| Purple layer   | `--sg-color-domain-intelligence-500` | `#7B5AA6` |
| Teal layer     | `--sg-color-domain-oss-500`          | `#2A9D8F` |
| Warning node   | `--sg-color-signal-danger-500`       | `#B3261E` |
| Light backdrop | `--sg-surface-card` → base           | `#FFFFFF` → `#F1F0EC` |
| Dark backdrop  | `--sg-surface-*` (dark)              | `#232630` → `#14151A` |

## Files

- `stackgraph-icon-light.svg` — light-mode variant (light backdrop).
- `stackgraph-icon-dark.svg` — dark-mode variant (dark backdrop).
- `../apps/web/app/icon.svg` — **adaptive** favicon that switches backdrop via
  `@media (prefers-color-scheme: dark)`. Next.js App Router serves this automatically
  at `/icon.svg` and injects the `<link rel="icon">`; no code wiring required.

All three are 1024×1024 vectors, so they scale cleanly from favicon to store listing.
To export PNGs (e.g. a 1024 App Store / `apple-icon.png`), rasterize with any SVG tool,
e.g. `rsvg-convert -w 1024 -h 1024 stackgraph-icon-light.svg -o icon-1024.png`.
