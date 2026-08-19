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
