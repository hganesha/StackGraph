# Strata — Design Language for StackGraph

**Companion files:** `strata-design-tokens.json` (import into Figma via Tokens Studio or native Variables import), `strata-style-guide.html` (live reference)

---

## Why "Strata"

The product's own metaphor is layers: three graphs (Business, Enterprise, OSS) stacked into one estate, evidence stacked under every conclusion (DECLARED → OBSERVED → INFERRED), time stacked as history under the present state. Strata names that directly instead of reaching for a generic "cloud/network" enterprise-SaaS visual language.

## Who this is for, and what that rules out

Primary users are CTOs skimming for five minutes, EAs living in it for hours, CISOs cross-checking a vulnerability list, engineers reading evidence line by line (spec §4). That's a data-dense, trust-critical, specialist tool — not a marketing site and not a consumer app. It rules out: playful/toy-like, maximalist chaos, soft pastels, and — explicitly — the generic AI-SaaS default of Inter-on-white with a purple gradient hero. It also rules out heavy skeuomorphism or decorative texture; an instrument panel doesn't need atmosphere, it needs to be scannable under pressure.

**Direction:** instrument-panel precision. Flat, high-contrast, quietly confident. Closer to a technical terminal than a dashboard template.

## The one idea that makes this distinctive

Typography is assigned by **evidence class, not by hierarchy.** The spec (§33) already splits every fact into DECLARED / OBSERVED / EXTERNAL_MEASURED (raw, machine-read) versus INFERRED (reasoned, probabilistic). Strata makes that distinction visible before you read a word:

- **IBM Plex Mono** — anything that is a raw fact: file paths, package names, confidence decimals, scan IDs, node/graph labels, evidence source lines.
- **IBM Plex Sans** — anything that is reasoning or narrative: headings, recommendation "why" prose, INFERRED assessments, UI chrome.

A user internalizes within one screen that monospace = "this came directly from a scan" and sans = "this is StackGraph's interpretation" — without a label. That reinforces the product's central trust claim (§33: "no material conclusion without evidence") at the typography level, not just in a drawer. IBM Plex was chosen because it's a genuinely enterprise/technical family (designed for IBM's own product suite) with matched sans/mono weights — not because it's unusual for its own sake.

---

## Color system

Four domain ramps, extended from the hues already established in the UI spec, plus exactly one semantic color reserved for warnings. **Five colors total, disciplined on purpose** — every additional hue is a hue the user has to learn.

| Ramp | Anchor (500) | Meaning | Never used for |
|---|---|---|---|
| Business (amber) | `#D4A843` | Business graph domain | Warnings, confidence |
| Enterprise (slate) | `#4A6FA5` | Enterprise tech graph domain | Warnings, confidence |
| OSS (teal) | `#2A9D8F` | OSS reference graph domain | Warnings, confidence |
| Intelligence (violet) | `#7B5AA6` | Assessments, recommendations, findings | Warnings, confidence |
| Danger (red) | `#B3261E` | LOW confidence and error states only | Anything decorative |

**Confidence is not a sixth color.** Per the earlier design critique, color-only category encoding fails accessibility and a fifth competing hue would blur against the domain system. Confidence is shown as a **3-segment bar indicator** (▮▮▮ / ▮▮▯ / ▮▯▯ for HIGH / MEDIUM / LOW) in neutral ink, with the text label always present. Red appears exactly once in this system: LOW confidence and genuine errors. If the user sees red, something needs attention — that's the entire vocabulary of the color, which is what makes it work.

Each domain ramp runs 50→900 (see tokens file) so the same hue can express a light-mode tint fill, a dark-mode fill, a border, and 800/900-stop text-on-fill — without ever putting black text on a colored background (a rule worth stating explicitly because it's the single most common contrast failure in dashboard UI).

**Domain badges carry text, not just color** — a two-letter mono code (`ENT` / `OSS` / `BIZ` / `INT`) on a 100-tint fill with 800/900-tint text. This was a direct fix from the critique: color-blind users and black-and-white printouts (CTOs still print) both need the badge to work without hue.

## Surfaces — light and dark, both first-class

This is a tool people leave open all day next to other engineering tools (most of which default dark) and also a tool CTOs screen-share in daylight meeting rooms. Both modes are required, not a dark-mode-as-afterthought toggle.

| | Light | Dark |
|---|---|---|
| Base | `#FAF9F6` (warm paper, not stark white) | `#14151A` |
| Card | `#FFFFFF` | `#1C1E24` |
| Sunken (evidence drawer background) | `#F1EFEA` | `#0E0F13` |
| Border | `#DEDCD4` | `#2C2E36` |

Neutrals are warm-graphite, not pure black/white/gray — this is a small, deliberate choice that keeps the interface from reading as a generic dashboard template.

## Type scale

14px is the default body size, not 16px — this is a data-dense enterprise tool where a marketing-site type scale would waste vertical space the user needs for rows of evidence and table data. Full scale in the tokens file; the only oversized text in the entire system is the `display` style (32px), reserved for exactly two things: the Technology Entropy score and a Viability delta — the two numbers meant to be read from across a room.

## Spacing, radius, elevation, motion

- **8px base grid** (4/8/12/16/24/32/48/64) — standard, chosen for consistency with dense table rows, not novelty.
- **Two elevation levels only**: flat (default — hairline border, no shadow) and raised (evidence drawer, modals, the recommendation card — 1px border + an 8%-opacity shadow). An instrument panel doesn't need five shadow tiers.
- **Two connector states** carry the system's one genuinely novel interaction pattern: a confirmed cross-domain bridge (join confidence ≥ 0.85) renders as a solid 2px domain-colored stroke with an amber pulse *only while selected*; an unconfirmed bridge (< 0.85) renders as a 1.5px dashed neutral stroke with no motion and a "possible match" label. This is the direct Figma expression of the uncertain-bridge state from the UI spec revision.
- **Motion is restrained and purposeful**: 150ms for hover, 200ms for panel transitions, a single 1.8s pulse loop reserved for the active bridge selection — never ambient, always `prefers-reduced-motion`-aware.

## Iconography

Tabler outline icons, 1.5px stroke weight, 18px inline / 20px standalone. Outline (not filled) to match the hairline-border, flat-surface language everywhere else — a filled icon set would visually fight the rest of the system.

## Component principles (detailed specs live in the style guide)

- **Domain badge** — pill, mono two-letter code, 100-tint fill / 800-tint text.
- **Confidence chip** — 3-segment bar + label; red only at LOW.
- **Bridge connector** — solid + pulse (confirmed, selected) vs. dashed, static (unconfirmed).
- **Evidence row** — mono evidence-class tag (`DECLARED`/`OBSERVED`/`INFERRED`/`CURATED`/`EXTERNAL_MEASURED`) + mono source path + one line of sans description.
- **Recommendation card** — raised elevation, 4px domain-colored left border indicating the primary affected domain, confidence chip top-right, mono migration stats, sans "why" prose.
- **Table row (Software Estate home)** — the default reading surface; domain badge, mono technology name, sans one-line status, confidence chip, right-aligned priority score.

## Getting this into Figma

1. Import `strata-design-tokens.json` with the **Tokens Studio for Figma** plugin (Tokens Studio → Import → JSON), or via Figma's native Variables import if your workspace supports it. This creates every color ramp, spacing value, radius, and type style as a real Figma variable/style, not a static swatch.
2. Build the base components (badge, chip, connector, evidence row, card) as Figma components bound to those variables — that binding is what makes a light/dark mode toggle in Figma free later.
3. Use `strata-style-guide.html` as the visual reference while building — it's the same values, rendered.
