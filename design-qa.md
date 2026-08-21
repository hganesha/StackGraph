# Business Map design QA

## Evidence

- Source visual truth: `docs/audits/capability-mapper/03-hydrated-map.jpg`
- Final value-chain implementation: `docs/audits/capability-mapper/15-business-map-shared-bands.jpg`
- Final organization implementation: `docs/audits/capability-mapper/16-business-map-organization.jpg`
- Full-view side-by-side comparison: `docs/audits/capability-mapper/17-business-map-shared-comparison.jpg`
- Focused shared-group editor: `docs/audits/capability-mapper/18-business-map-shared-editor.jpg`
- Focused CRUD editor: `docs/audits/capability-mapper/11-business-map-crud-editor.jpg`
- UI inconsistency source captures: `/Users/hariganesh/Desktop/Screenshot 2026-08-19 at 6.08.29 PM.png` and `/Users/hariganesh/Desktop/Screenshot 2026-08-19 at 6.08.14 PM.png`
- Final function-editor fix: `docs/audits/capability-mapper/19-business-map-ui-fix-function.jpg`
- Final capability-editor fix: `docs/audits/capability-mapper/20-business-map-ui-fix-capability.jpg`
- Matched 1405 x 712 comparisons: `docs/audits/capability-mapper/21-business-map-ui-fix-function-comparison.jpg` and `docs/audits/capability-mapper/22-business-map-ui-fix-capability-comparison.jpg`
- Shared-band spacing before/final: `docs/audits/capability-mapper/23-shared-band-spacing-before.jpg` and `docs/audits/capability-mapper/24-shared-band-spacing-final.jpg`
- Shared-band spacing comparison: `docs/audits/capability-mapper/25-shared-band-spacing-comparison.jpg`
- Stacked and tablet spacing evidence: `docs/audits/capability-mapper/26-shared-band-stacked-final.jpg` and `docs/audits/capability-mapper/27-shared-band-spacing-tablet.jpg`
- Default View mode: `docs/audits/capability-mapper/28-view-mode/final-view.jpg`
- Restored Edit mode: `docs/audits/capability-mapper/28-view-mode/edit-mode.jpg`
- View-mode comparison: `docs/audits/capability-mapper/28-view-mode/comparison.jpg`
- Contextual Ask handoff: `docs/audits/capability-mapper/14-business-map-ask-handoff.jpg`
- Viewport: 1280 x 720 CSS pixels at device scale factor 1
- Source and implementation captures: 1280 x 720 pixels each at device scale factor 1; comparison: 2560 x 720 pixels with no density normalization required
- State: light theme. Value-chain capture uses the Porter template, Technology & Digital loaded, 11 mapped capabilities, five stages, average maturity 2.1, and one shared horizontal group. Organization capture uses five organization units and eight mapped functions.

The full-view comparison establishes layout, density, hierarchy, source fidelity, and how the new horizontal band fits the source canvas. The focused shared-group editor capture is required because its range controls and group definition are not legible in the full view. The organization view is an intentional new state without a one-to-one source screen; it is evaluated against the same source shell, grid, card density, typography, and business-domain token treatment.

The UI-consistency pass uses matched 1405 x 712 CSS-pixel and image dimensions at device scale factor 1. The source and implementation differ in selected catalog function, but the compared edit affordances, library boundary, toolbar action, editor width, and destructive section are in the same route, theme, viewport, and interaction states.

The View-mode pass uses the 1405 x 712 source edit-state capture as visual-language truth and a browser-rendered 1405 x 714 implementation at device scale factor 1. The combined comparison is 2834 x 754 pixels; no density normalization was needed. The state difference is intentional: the source shows the editing workspace while the implementation shows the requested default read-only state. The comparison therefore judges typography, tokens, card density, stage hierarchy, shared-band treatment, and toolbar alignment rather than one-to-one panel geometry. A separate focused crop was not needed because the mode switch, toolbar, stage headers, shared band, and capability cards remain readable at native resolution in the individual captures.

## Findings

- P0: none.
- P1: none.
- P2: none remaining.
- P3: Long stage and process names truncate at compact widths. The complete value remains available in the editable field or editor, and truncation preserves the dense canvas rhythm.
- P3: Catalog and map persistence are browser-local. Server-side versioning, collaboration, and audit history remain an integration follow-up rather than a visual defect.
- P3: Organization cards truncate long function names at the compact 1280 px five-column layout. Full names remain available in the function editor and accessible name, preserving the dense source rhythm.

## Required fidelity surfaces

- Fonts and typography: IBM Plex Sans and StackGraph evidence-mono treatments are loaded and consistent. The library keeps the source's compact 10–12 px hierarchy without illegible compression.
- Spacing and layout: the compact product rail, 276 px library, five-column grid, and 324 px overlay editor preserve all five primary stages or organization units at the reference viewport. The horizontal group occupies a dedicated band above capability cards without covering them. At 768 x 900 the library overlays the horizontally scrollable canvas, and its toolbar toggle remains visible.
- Colors and tokens: business-domain amber is used for map structure and intelligence styling is reserved for global Ask. Borders, focus states, danger actions, surfaces, and disabled states use Strata semantic tokens.
- Image quality and assets: the target contains no raster product imagery. All visible interface icons use the installed Tabler icon set; no emoji, handcrafted SVG, placeholder art, or CSS illustration substitutes are rendered.
- Copy and content: function, process, capability, maturity, owner, tags, KPI, delete-impact, and Ask-context copy use business architecture terminology and explain hierarchy consequences plainly.

## Comparison history

### Pass 1 — base mapper

- P2: Only three of five value-chain stages were visible at 1280 px because the full global rail, capability library, and wide stage tracks competed for horizontal space.
- P2: The capability detail pane reduced the usable canvas width when opened.
- P2: The responsive toolbar breakpoint hid useful map metrics too early.

Fixes applied:

- Added a route-specific 64 px compact global rail while retaining StackGraph navigation and its mobile drawer.
- Reduced the minimum stage track width and made the five-stage grid explicit.
- Converted the detail pane to an overlay at canvas-constrained widths.
- Separated the toolbar metric breakpoint from the drawer breakpoint.

Post-fix evidence: `07-business-map-implementation.jpg`, `08-design-qa-comparison.jpg`, and `09-design-qa-focused.jpg`.

### Pass 2 — catalog CRUD and Ask consolidation

- P2: A local Advisor panel duplicated the product-wide Ask mental model.
- P2: At tablet width, the catalog library could layer above the entity editor opened from that library.
- P2: Capability edit affordances were too hidden and the disabled add control could visually compete with direct editing.
- P2: Long process names wrapped into tall, fragmented headings in the narrow catalog.

Fixes applied:

- Replaced Advisor with `Ask about map`, which opens global Ask with the current title, template, stages, capability placements, and maturity levels attached.
- Raised the entity editor above the library at tablet/mobile widths.
- Kept edit controls visible at rest, isolated their hit area, and added an `Edit definition` route from capability detail.
- Applied single-line truncation to process headings while retaining the full value in the editor.

Post-fix evidence: `11-business-map-crud-editor.jpg`, `12-business-map-crud-qa.jpg`, `13-business-map-crud-comparison.jpg`, and `14-business-map-ask-handoff.jpg`.

### Pass 3 — cross-cutting capability bands and organization mapping

- P2: The stage-placement model could only place individual capabilities inside one vertical stage, so shared functions and horizontal enablers could not be represented.
- P2: Business functions had no visual relationship to the current operating organization.
- P2: Drag-only organization assignment would make the new mapping harder to discover and less reliable for keyboard-oriented workflows.

Fixes applied:

- Added editable shared capability groups with a start stage, end stage, selected capability set, and a spanning business-domain band above the underlying stage cards.
- Added an Organization map template with five starter organization units, function cards, direct unit naming, unit add/delete, and reassignment-safe deletion.
- Added both drag-and-drop organization reassignment and an explicit Organization unit selector in the function editor.
- Extended the global Ask handoff to serialize organization units and their assigned business functions when the organization template is active.

Post-fix evidence: `15-business-map-shared-bands.jpg`, `16-business-map-organization.jpg`, `17-business-map-shared-comparison.jpg`, and `18-business-map-shared-editor.jpg`.

### Pass 4 — entity actions and destructive containment

- P2: Function editing used a labeled button while process and capability editing used pencil icons, weakening the entity hierarchy.
- P2: Process and capability edit controls extended past the capability-library divider into the canvas.
- P2: Shared-group creation used a horizontal-arrows icon while function and process creation used a plus affordance.
- P2: The function danger zone stretched flush against the editor edge, visually bleeding beyond the padded form rhythm.

Fixes applied:

- Standardized edit actions on the Tabler pencil icon with accessible labels and titles; creation actions consistently use a plus icon followed by the entity noun.
- Constrained and paint-contained the library, narrowed the expanded process content track, and aligned function, process, and capability actions inside the divider.
- Changed the toolbar action to `+ Shared group` while retaining the horizontal icon in shared-band identity and editor headers.
- Centered the destructive section at the same 16 px inset as editor form fields and verified both initial and confirmation states.

Post-fix evidence: `19-business-map-ui-fix-function.jpg`, `20-business-map-ui-fix-capability.jpg`, `21-business-map-ui-fix-function-comparison.jpg`, and `22-business-map-ui-fix-capability-comparison.jpg`.

### Pass 5 — shared-band vertical rhythm

- P2: The first shared band sat directly against the stage headers, and the previous 38 px band stride allowed stacked bands to overlap because their rendered height is approximately 56 px.
- P2: Capability cards began immediately after the last band, leaving no visual separation between cross-cutting groups and stage-owned capabilities.

Fixes applied:

- Set the first band to begin 76 px from the grid top, producing an 8 px gutter below the rendered stage headers.
- Increased the shared-band stride to 64 px: the rendered band height plus an 8 px inter-band gutter.
- Added an 8 px body inset after the final band so capability cards begin on their own clean row.
- Verified one-band, four-band stress, desktop 1405 x 712, and tablet 768 x 900 states without collision or overlap.

Post-fix evidence: `24-shared-band-spacing-final.jpg`, `25-shared-band-spacing-comparison.jpg`, `26-shared-band-stacked-final.jpg`, and `27-shared-band-spacing-tablet.jpg`.

### Pass 6 — default View mode and explicit Edit boundary

- P2: The map opened directly into a mutation-heavy workspace, exposing the capability library, drag behavior, inline naming, delete/reset actions, and add controls before the user chose to edit.
- P2: The first implementation of the new mode switch caused `Ask about map` to wrap at the 1405 px reference viewport.

Fixes applied:

- Added an explicit View/Edit segmented control and made View the route default without mutating or discarding the saved business-map draft.
- In View mode, removed the catalog library, inline text fields, drag/drop behavior, shared-group and stage/unit creation, reset/delete controls, and capability mutation actions while retaining zoom, grid, Ask, metrics, and read-only capability details.
- Kept the full existing CRUD workspace intact behind Edit, including the library, template picker, load menu, drag/drop, shared groups, stage/unit controls, and editors.
- Made the Ask control non-wrapping and verified both modes at 1405 x 714 and 900 x 714 with no document-level horizontal overflow.

Post-fix evidence: `docs/audits/capability-mapper/28-view-mode/final-view.jpg`, `docs/audits/capability-mapper/28-view-mode/edit-mode.jpg`, and `docs/audits/capability-mapper/28-view-mode/comparison.jpg`.

## Functional verification

- Created a new business function.
- Added a process to the new function.
- Added a capability with description, owner, tags, and KPIs.
- Edited and moved catalog definitions through the hierarchy-aware editor.
- Verified guarded function deletion cascades to its processes, capabilities, and canvas placements; the QA test data was removed afterward.
- Loaded 11 Technology & Digital capabilities, selected a capability, changed maturity, and moved it between stages.
- Confirmed map and catalog state persist after reload and the legacy map draft migrates into the new versioned state.
- Verified `Ask about map` opens `/ask?source=business-map` with a visible map-context banner and map-specific prompts.
- Created, edited, ranged, and retained a 10-capability horizontal shared group spanning all five stages; underlying stage placements remained intact.
- Switched to Organization map, verified all eight seeded functions across five starter units, reassigned Technology & Digital through the function editor, and restored the curated mapping.
- Added and removed an organization unit, confirming functions are reassigned safely when a populated unit is deleted.
- Verified organization-context Ask displays `5 units · 8 mapped functions`.
- Verified the 768 x 900 layout with both the entity editor and organization map states.
- Verified function, process, and capability edit controls remain inside the 276 px library at the reported 1405 x 712 viewport.
- Verified `+ Function`, `+ Process`, and `+ Shared group` creation affordances and pencil-only edit affordances retain accessible names.
- Verified function delete confirmation remains contained and does not execute until `Delete permanently` is selected.
- Verified shared bands retain 8 px gutters above, between, and below the rendered bands with one through four groups.
- Verified a fresh route load opens with View selected, the library and mutation controls absent, and the saved map data unchanged.
- Verified View-mode capability cards open read-only details with maturity, stage, structure, and KPI information but no edit/remove or maturity/stage mutation controls.
- Verified Edit restores the complete current value-chain workspace; switching back to View closes transient editors and returns to the clean canvas.
- Verified the Organization map follows the same View/Edit boundary: View uses static unit labels and function cards, while Edit restores assignment, drag/drop, add/delete, and inline naming controls.
- Verified 1405 x 714 and 900 x 714 browser viewports in both modes with document scroll width equal to viewport width.
- Production build and TypeScript validation passed.
- Browser console: 0 errors and 0 warnings after the final server restart; informational React/Fast Refresh development messages only.

## Acceptance

The mapper retains the source's dense hierarchical library, five-stage value-chain canvas, capability cards, stage metrics, maturity treatment, and direct manipulation. It now represents both vertical stage ownership and horizontal/shared capabilities, while the organization template maps the same durable business functions to the current operating structure. Visual CRUD covers functions, processes, capabilities, shared groups, and organization units. Global Ask remains the single intelligence entry point and receives either value-chain or organization-map context.

final result: passed

---

# Shared filter bar design QA

## Evidence

- Source visual truth: `/Users/hariganesh/Desktop/Screenshot 2026-08-21 at 9.22.04 AM.png`
- Applications implementation: `artifacts/filter-bar-applications-production.png`
- Estate implementation with Domain control: `artifacts/filter-bar-estate-full.png`
- Narrow-width implementation: `artifacts/filter-bar-narrow.png`
- Source and implementation comparison: `artifacts/filter-bar-comparison.png`
- Viewport: 1440 x 900 CSS pixels at device scale factor 1 for the desktop captures; 768 x 800 CSS pixels for the narrow-width capture.
- Dimensions: source 1125 x 92 pixels; Applications filter-bar crop 1100 x 62 CSS/pixels; full Applications capture 1440 x 900 pixels. The comparison preserves both source and implementation at native scale and centers them on one canvas; no density resampling was required.
- State: light theme, default lens, confidence, freshness, sort, and direction; Applications shows 5 of 5 and Estate shows 50 of 50.

The full-view captures establish the bar in product context. The combined focused comparison is needed because the filter typography, border radii, control spacing, chevrons, and result count are too small to judge reliably in the full view.

## Findings

- P0: none.
- P1: none.
- P2: none remaining.
- P3: The concept includes shortcut keycaps inside search. They are intentionally omitted because Command/Ctrl-K is already the product-wide Ask shortcut; duplicating that hint on the estate name filter would be misleading.
- P3: The Estate route includes a Domain control that is absent from the concept and the domain-scoped Applications route. This is intentional product behavior.

## Required fidelity surfaces

- Fonts and typography: IBM Plex Sans remains the app-native face. Labels and current values stay on one line at the default state; the result count retains the evidence-mono treatment. No control text wraps.
- Spacing and layout rhythm: the bar is 62 px high with 40 px controls, 8 px gaps, 10 px panel padding, token radii, and subtle token elevation. Search grows into available room while filter controls retain compact fixed widths. At the 1176 px Estate workspace, the full bar including Domain and count fits exactly without overflow. At 768 px, controls remain on one horizontal track and the strip becomes horizontally scrollable (`929 px` content in a `748 px` scroller) instead of wrapping.
- Colors and visual tokens: panel, base surface, borders, muted labels, focus rings, and hover states use existing Strata tokens in both light and dark themes.
- Image quality and asset fidelity: the source contains no raster product imagery. Search, chevron, and direction icons use the installed Tabler icon set; no text-glyph or handcrafted SVG substitutes were added.
- Copy and content: Search, Lens, Domain where applicable, Confidence, Freshness, Sort, and result-count copy match the product vocabulary and the reference concept.

## Comparison history

### Pass 1 — single-row conversion

- P1: The original shared bar split filters into two wrapping rows with labels stacked above inputs, which was the exact usability issue reported.
- P2: The first single-row implementation allowed native select widths to expand to their longest option. On Estate, the added Domain control pushed the result count beyond the initially visible 1176 px workspace.

Fixes applied:

- Reordered the shared bar to search first, followed by Lens, optional Domain, Confidence, Freshness, Sort/direction, and result count.
- Replaced vertical field labels with inline labels and Tabler icons.
- Added compact fixed control widths while leaving search flexible.
- Kept one non-wrapping flex track and enabled contained horizontal scrolling only below the width needed to show every control.

Post-fix evidence: `artifacts/filter-bar-comparison.png`, `artifacts/filter-bar-estate-full.png`, and `artifacts/filter-bar-narrow.png`. On Estate, `scrollWidth` and `clientWidth` both measured 1154 px after the fix, and the count was visible. All filter/control top coordinates matched on the 768 px capture.

## Functional verification

- Verified the shared bar on `/estate` and `/applications`, including the route-specific Domain control.
- Searched for `acorn`, selected Low confidence, changed sort to Name, toggled ascending direction, and confirmed the URL state and `6 of 50` result count.
- Cleared two active filters and confirmed the default URL, empty search, and `50 of 50` count.
- Verified the 768 px and 390 px layouts remain one row with horizontal overflow instead of wrapping.
- Production-mode browser console: 0 errors and 0 warnings.
- `pnpm --filter @stackgraph/web build` passed.
- `pnpm --filter @stackgraph/web typecheck` passed after the build completed.
- Targeted Stylelint and `git diff --check` passed.

final result: passed

---

# Application Detail design QA — Option 3

## Evidence

- Source visual truth: `docs/audits/application-detail/option-3-source.png`
- Initial application screen: `docs/audits/application-detail/before-overview.jpg`
- Initial unclassified inventory: `docs/audits/application-detail/before-unclassified.jpg`
- Final browser-rendered implementation: `docs/audits/application-detail/option-3-implementation.jpg`
- Full-view comparison: `docs/audits/application-detail/option-3-comparison.jpg`
- Route: `http://localhost:3000/applications/3e6246ee-19ed-4290-9189-725075b73f3d`
- Source visual: 1487 x 1058 pixels, generated for a 1440 x 1024 desktop target.
- Implementation viewport: 1030 x 927 CSS pixels at device pixel ratio 2. The in-app browser capture is normalized to 1030 x 927 image pixels, so the implementation is compared at one image pixel per CSS pixel.
- Combined comparison: 2533 x 1058 pixels, with the source and implementation kept at native capture sizes and aligned at the top edge. No scaling or density interpolation was applied.
- State: dark theme; Technology tab active; By architecture active; dependency hierarchy collapsed; Frontend and Build & bundling expanded; `esbuild@0.25.12` selected; Unclassified collapsed; evidence inspector visible.

The source target and implementation were opened together in the same comparison input and in the durable comparison artifact above. The implementation capture uses the user's available 1030 px in-app browser viewport, so the comparison judges the responsive mapping of hierarchy, density, typography, surfaces, and inspector behavior rather than claiming pixel-level equality with the 1440 px concept. A separate focused crop was not required because the technology table, disclosure controls, selected-row treatment, and evidence inspector remain legible in the native full-view captures. The evidence drawer was inspected directly in the browser as a focused interaction state.

## Findings

- P0: none.
- P1: none.
- P2: none remaining.
- P3: The source concept uses a full-height inspector flush to the right edge. The implementation keeps the inspector sticky within the existing StackGraph workspace at the verified 1030 px viewport, preserving the established shell and leaving the global evidence drawer free to overlay above it.
- P3: The source concept uses illustrative `Backend` and one-source data. The live estate truth is `Middleware` with one linked technology and two distinct evidence source types for the selected package; the implementation intentionally renders the live data rather than mock values.
- P3: Browser-rendered verification covered the available 1030 x 927 desktop viewport. The 900 px stacking breakpoint and mobile reflow were reviewed in CSS but could not be captured because the selected in-app browser surface does not expose viewport resizing.

## Required fidelity surfaces

- Fonts and typography: IBM Plex Sans remains the narrative face and IBM Plex Mono remains the evidence/technology face. The implementation matches the source's 12–16 px product hierarchy, medium application title, compact uppercase-free data labels, and readable line heights without malformed wrapping.
- Spacing and layout rhythm: the application header, local tab boundary, technology toolbar, collapsed dependency row, architecture disclosures, compact ledger, and 280–340 px inspector follow StackGraph's 4/8/12/16/24/32 spacing tokens. The 1030 px viewport keeps all persistent controls visible without document-level horizontal overflow.
- Colors and visual tokens: all surfaces, borders, text levels, selection edge, confidence treatment, and active underlines use existing Strata tokens. The design adds no gradients, decorative shadows, or new semantic colors.
- Image quality and assets: the target contains no raster product imagery. Visible interface icons use the installed Tabler icon family; there are no emoji, handcrafted SVGs, CSS drawings, placeholder assets, or generated product imagery in the implementation.
- Copy and content: application, repository, architecture, role, confidence, and evidence labels use live estate data. `.` is presented as `Repository root`, singular/plural labels are correct, and duplicate citation labels are consolidated in the inspector.
- Accessibility and interaction: tabs expose `tablist`/`tab`/`tabpanel` semantics and support arrow, Home, and End navigation; search has an accessible label; disclosure buttons expose expanded state; selected technology uses `aria-pressed`; focus uses the global visible-focus token; reduced motion remains honored globally.

## Comparison history

### Pass 1 — audit findings to selected concept

- P1: The original page rendered all 185 unclassified technologies in the primary reading flow, making the application screen effectively an inventory dump.
- P2: Technology identity, role, confidence, classification, and three repeated evidence controls competed as peer pills and wrapped into malformed rows.
- P2: Dependency and architecture sections had weak hierarchy, `.` appeared as the component name, and singular counts rendered as `1 components`.

Fixes applied:

- Replaced the long page with application-level Overview, Technology, Assessments, and Recommendations tabs, defaulting to the selected Technology workspace.
- Added collapsible architecture and function groups; Unclassified starts collapsed while the first classified group/function is expanded.
- Consolidated evidence into a selected-technology inspector, deduplicated evidence labels, and kept the global evidence drawer as the source-detail drill-down.
- Added filter and architecture/all views, correct disclosure icons, `Repository root` labeling, and count grammar.

Post-fix evidence: `docs/audits/application-detail/option-3-implementation.jpg`.

### Pass 2 — source-to-implementation visual comparison

- P2: The first coded pass retained an Evidence column with source-count actions in every row. The selected visual keeps the ledger focused on Technology, Role, and Confidence and moves evidence into the inspector.

Fix applied:

- Removed the redundant Evidence column and source-count row actions. Evidence count and source labels now appear only in the inspector, matching the selected information architecture and reducing horizontal density.

Post-fix evidence: `docs/audits/application-detail/option-3-comparison.jpg`.

## Functional verification

- Opened Overview, Assessments, Recommendations, and returned to Technology.
- Verified Arrow, Home, and End keyboard navigation across application tabs.
- Filtered the architecture view to `vite`, cleared the query, and confirmed matching groups update.
- Switched between By architecture and All technologies.
- Expanded and collapsed the 185-item Unclassified group.
- Expanded and collapsed Dependency hierarchy; verified `Repository root` and the Explore graph link.
- Selected `esbuild@0.25.12`, inspected role/classification/confidence, opened Technology usage evidence, verified the global evidence drawer, and closed it.
- Confirmed the Open technology link targets the selected technology detail route.
- `pnpm --filter @stackgraph/web typecheck` passed.
- Targeted Stylelint passed for `application.module.css`.
- Docker production-style Next.js build completed successfully and the local web container was rebuilt/restarted.
- Browser console: 0 errors and 0 warnings after the final restart and interaction checks.

final result: passed

---

# Latest design QA result — shared filter bar

The current report is `Shared filter bar design QA` above. Its source, implementation, comparison, responsive measurements, interaction checks, console check, build check, typecheck, and comparison history are the latest QA evidence in this file.

final result: passed
