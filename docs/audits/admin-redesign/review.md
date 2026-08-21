# Admin screen redesign review

## Audit scope

Combined UX and screenshot-based accessibility review of the StackGraph Admin screen, with emphasis on modernization governance, deterministic insight rules, and tenant code policies. The review used the fixture-backed local app at desktop/tablet and 390px mobile widths.

## User goal and accessibility target

An administrator should be able to locate one workspace control, understand its effect, and make a governed change without scanning unrelated systems or losing context. The layout should reflow without horizontal page overflow and expose clear regions, labels, selected states, and status text to assistive technology.

## Flow evidence

1. **Admin landing — needs improvement before the redesign.** Seven peer tabs were compressed into one narrow row while the page was capped at 820px, leaving much of the desktop unused. Evidence: `01-before-connections.jpg`.
2. **Modernization governance — poor before the redesign.** Rules, eligibility, replacement catalog, calibration, and ecosystem admission were stacked into one continuous panel. Nine rule editors appeared before the policy forms, producing a long and cognitively expensive scan. Evidence: `02-before-modernization.jpg`.
3. **Policies and rules — healthy after the redesign.** Four task-based admin areas lead to a focused policy workspace. Modernization and code policy are separated, and modernization has dedicated tabs for insight rules, eligibility, replacements, calibration, and ecosystems. Evidence: `09-final-clean-governance.jpg`.
4. **Mobile reflow — healthy after the redesign.** The four primary admin areas wrap into a visible two-column grid at 390px, nested settings remain touch-accessible, and the document has no horizontal page overflow. Evidence: `08-final-mobile-wrapped-tabs.jpg`.

## Strengths retained

- Existing Strata tokens, typography, status colors, card language, and form behavior remain intact.
- Destructive and high-impact actions retain their existing labels, confirmation behavior, and audited server workflows.
- Rule status, evidence coverage, fingerprints, and data-readiness language continue to make governance state explicit.

## UX risks found

- The original flat navigation described implementation areas rather than administrator tasks.
- The 820px content cap made complex forms feel cramped despite ample desktop space.
- Modernization mixed five distinct governance jobs in one reading order.
- Rule phase one and phase two appeared simultaneously, forcing users to scan unrelated maturity levels.
- Code-policy editing and estate evaluation competed for attention on the same page.

## Accessibility risks found

- The original long screen increased focus-travel and reading-order cost for keyboard and screen-reader users.
- Narrow rule rows compressed labels and controls, increasing zoom and reflow risk.
- Screenshot review cannot confirm color contrast ratios, full keyboard arrow-key behavior for ARIA tabs, screen-reader announcements after mutations, or focus recovery after errors.

## Changes implemented

- Grouped the screen into four task-based areas: Data & sources, Intelligence, Policies & rules, and People & access.
- Added nested tabs that reveal one relevant settings surface at a time.
- Split deterministic rules into phase tabs and code policies into function-policy and repository-alignment tabs.
- Expanded the desktop canvas to 1180px and added responsive breakpoints for tablet and mobile.
- Added consistent panel headers, explanatory callouts, real icon-library icons, selected-state borders, and mobile tab wrapping.
- Corrected the root theme script placement so the preview hydrates without browser console errors.

## Evidence limits

The review verifies visible layout, semantic regions, selected states, primary tab interactions, mobile reflow, and the absence of console errors in the fixture-backed preview. It does not claim full WCAG conformance or validate live API mutation/error states.
