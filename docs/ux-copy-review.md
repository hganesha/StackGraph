# StackGraph copy review

Status: suggestions · Date: 2026-08-23 · Author: UX copy review

Reviewed the user-facing strings across every surface. This proposes changes grouped by
page, plus one cross-cutting mechanism — hover definitions — that solves more of the
problem than any individual rewrite.

Nothing here is implemented. Each row is `current → suggested` so it can be accepted or
rejected line by line.

---

## 1. What is actually wrong

Four patterns account for nearly every awkward string.

### 1.1 Two voices are mixed

Some copy is written for the reader:

> "Start with the highest-priority items, then open a repository to review the evidence."

Some is written for the architect who built the system:

> "The scheduler creates the work; workers never invent their own loops."
> "Per-provider quota and backoff state, so throttling reads as intentional, not failure."
> "StackGraph's curated classification stays primary; custom functions provide a governed overlay."

The second kind explains a *design decision*. It is interesting, and it belongs in the
docs, not on the screen. A user reading the Scan page wants to know what will happen and
when — not the guarantee the scheduler makes to the workers.

**Rule to adopt:** on-screen prose answers *what is this, what do I do, what happens if I
do it*. Design rationale moves to docs or a help link.

### 1.2 Contract enum names are used as labels

`POPULATED`, `UNBOUND`, `Ungoverned`, `Applicability`, `Allowed diversity`,
`Observation`, `Measures`, `Cell`, `Concern`, `Reference model`, `Fingerprint`,
`Method version`, `Placement keys`.

These come straight from the API contract. Some are load-bearing product vocabulary and
should stay — but *none of them are defined anywhere in the UI*.

### 1.3 There is no way to ask "what does this mean?"

This is the single biggest gap. The product's value is a precise vocabulary — evidence,
confidence, governed, observed, inferred — and a new user meets perhaps thirty terms in
their first five minutes with no way to look any of them up. A few `title` attributes
exist on chips; nothing else.

### 1.4 Empty and error states are uneven

Good, three-part:

> "Nothing needs review. All current findings are confirmed, rejected, or not applicable."

Bare:

> "Canvas unavailable" · "Graph unavailable" · "Loading architecture profiles…"

---

## 2. The cross-cutting fix: a definition affordance

Rather than simplifying away the vocabulary — which would cost precision the product
needs — **define it in place**.

Proposal: a `<Term>` component in the design system. It renders the word with a subtle
dotted underline, and on hover/focus shows a short definition plus, where useful, a
"what to do about it" line. Keyboard-reachable, dismissible with Escape, and readable by
screen readers via `aria-describedby`.

```tsx
<Term id="governed">Governed</Term>
```

One glossary module, used everywhere the term appears, so the definition can never drift
between two screens. It also gives the About page a real glossary for free.

### Starter glossary

| Term | Hover definition | Add if useful |
|---|---|---|
| **Estate** | Everything StackGraph has discovered across your connected repositories: applications, services, repositories, and the technologies they use. | |
| **Evidence** | The specific scan result a statement came from. Every claim here links back to one. | |
| **Confidence** | How certain StackGraph is, based on how directly the evidence supports the claim. | |
| **Governed** | Someone has recorded a decision about which technologies are allowed here. | Ungoverned isn't a problem — it means no decision has been made yet. |
| **Ungoverned** | No target decision has been recorded for this concern yet. | Never reported as a violation. |
| **Preferred / Allowed / Discouraged / Prohibited** | The four decisions your architecture standard can record about a technology. | |
| **Exempted** | Normally not allowed here, but covered by a time-boxed exception. | |
| **Observed** | StackGraph looked and found it. | |
| **Not observed** | StackGraph could not look — a scan is missing, stale, or unsupported. | Different from "none found". |
| **None found** | StackGraph looked everywhere it could and found nothing. | |
| **Not yet modelled** | StackGraph has no way to detect this yet. Not a gap in your estate. | |
| **Applicability** | Whether this concern is required, recommended, optional, or doesn't apply to you. | |
| **Posture** | A summary of how healthy this area looks, from coverage, standardisation, currency, risk, and conformance. | |
| **Drift** | Where what you actually run differs from the standard you set. | |
| **Reference model** | StackGraph's canonical picture of what a stack contains. The frame; your profile is the fill. | |
| **Fingerprint** | A short checksum identifying this exact version, so two people can confirm they're looking at the same thing. | |

---

## 3. Suggestions by page

### 3.1 Global chrome

| Current | Suggested | Why |
|---|---|---|
| Nav: `Insights` → `/ask` | `Ask` or `Ask your estate` | The page's own tabs are "Overview" and "Ask", and the search box says "Ask your estate…". Three names for one thing. |
| Nav: `Estate Health` | `Scan health` or `Data health` | Users read "Estate Health" as *how healthy is my software*. It actually reports whether StackGraph can see enough to reason — a different question the page itself states well. |
| Status strip: `Coverage 9/12 repos · 75%` | `Scanned 9 of 12 repositories` | "Coverage" is ambiguous between test coverage and scan coverage. |
| Status strip: `Evidence 94%` | `94% of facts have evidence` | A bare percentage invites the wrong reading. |

### 3.2 Estate

| Current | Suggested | Why |
|---|---|---|
| "Every application, repository, service, and technology discovered across the connected repositories, grouped by domain and ranked by priority." | "Everything found across your connected repositories, grouped by domain and ranked by priority." | The list restates the four counts shown directly below it. |
| Lens: `CTO overview`, `EA standardization`, `CISO risk`, `Platform drift` | Keep, but add a one-line hover on each | Role initials are opaque to anyone outside that role. `EA standardization` especially. |
| `Couldn't load the estate summary. Retry, or check the API connection.` | Good — keep | What happened + what to do. |
| Filter: `Viability` | `Replaceability` or hover-define | "Viability" of what, in which direction, isn't guessable. |

### 3.3 Architecture (canvas)

The densest vocabulary in the product, and where hover definitions pay off most.

| Current | Suggested | Why |
|---|---|---|
| "A fixed frame of the concerns a stack must address, filled from evidence. Cells never move, so the same picture compares an application, the estate, and the governed target." | "The same picture every time: what a stack needs, and what you actually have. Because nothing moves, you can compare one application against another — or against your standard." | The current text explains the design principle. The suggestion says what it's for. |
| Control: `Emphasis` | `Colour by` | Names what it does. "Emphasis" names the mechanism. |
| Control: `Density` | `Size` or keep with hover | Minor. |
| Emphasis option hovers: "Tone follows the measured posture band." | "Colour cells by how healthy each area looks." | "Tone" and "posture band" are internal terms. |
| Cell state: `Not yet modelled` | Keep + hover: "StackGraph can't detect this yet. Not a gap in your estate." | The distinction from "None found" is the whole point and is currently invisible. |
| Panel: `Expectation / Applicability / Implementations / Allowed diversity` | `What's expected here` / `Required?` / `How many` / `How many different ones` | Four contract field names in a row. |
| Panel: `Observation` | `What we checked` | |
| Panel: `Measures` | `Scores` | |
| Panel: "No measures are produced for a cell in this state. Measurement requires an applicable expectation and a completed observation." | "Not scored yet — we need a completed scan and an applicable expectation first." | Passive, and "cell in this state" is jargon-on-jargon. |
| Panel: "No target decision has been recorded for this concern. An ungoverned cell is never reported as non-conformant." | "No standard set for this area yet. That's not counted against you." | Says the same thing without three contract terms. |
| Panel: `Required sensors / Supported sensors` | `Needs` / `Available` | |
| `Make this the standard` | Good — keep | Verb-first, outcome-clear. |
| Empty: `Canvas unavailable` + "The reference model, layout, or projection could not be loaded." | "Couldn't load the canvas. Graph and hierarchy views still work — try again, or check the API connection." | Three internal artifact names the user can't act on. |
| Drift status: `Cannot be evaluated` | Keep + hover: "We don't have enough scan data to judge this — it's not a violation." | The most important non-obvious rule in the product. |

### 3.4 Technologies

| Current | Suggested | Why |
|---|---|---|
| "Manifest technologies and their resolved dependencies, limited to connected repositories." | "Technologies declared in your manifests, and what they pull in." | "Resolved dependencies" and "limited to" are both jargon and hedge. |
| `Graph unavailable` / "The hierarchy remains available while this neighborhood is retried." | "Couldn't load the graph. The hierarchy on the left still works." | "Neighborhood" is a graph-theory term. |
| `Select a graph node` / "Its connections, dependent applications, and evidence will appear here." | "Pick anything in the graph to see what connects to it." | |

### 3.5 Modernization

Strongest page in the app — mostly leave alone.

| Current | Suggested | Why |
|---|---|---|
| "Modernization opportunities across the estate, ranked by priority, with the effort each one carries." | Keep | Clear, useful. |
| "Set an effort budget to see which initiatives fit inside it." | Keep | Model empty state: what it is, why empty, what to do. |
| `Portfolio value` | Hover-define | Value measured how? |
| "The scenario could not be calculated. The ranked portfolio remains available below." | "Couldn't calculate the scenario. The ranked list below still works." | |

### 3.6 Insights (`/ask`)

| Current | Suggested | Why |
|---|---|---|
| Page `Insights`, tabs `Overview` / `Ask`, nav `Insights`, input "Ask your estate…" | Settle on one name | See global chrome. |
| `Try asking` | Keep | Good affordance. |
| `Detach` | `Open in full` / `Pop out` | "Detach" doesn't say what happens. |
| "Insight reports couldn't be evaluated. Try refreshing this view." | "Couldn't build the insight reports. Try refreshing." | "Evaluated" is internal. |

### 3.7 Reviews

Best-written page in the app.

| Current | Suggested | Why |
|---|---|---|
| "Identity, capability, duplication, and modernization findings that need a human decision." | Keep | Exactly right. |
| "Nothing needs review. All current findings are confirmed, rejected, or not applicable." | Keep | Model empty state. |
| "Open the originating lens to review this finding." | "Open where this was found to review it." | "Lens" is internal; used nowhere else in the UI. |

### 3.8 Estate Health

| Current | Suggested | Why |
|---|---|---|
| `Analytical assurance` | `Can we trust this data?` | The page's actual question, and a much better section header. |
| `Analytically covered estate` | `Repositories we can fully analyse` | |
| `Decision intelligence` / `Insight readiness` | `Ready to answer` | Two abstract nouns for one idea. |
| "Code acquisition and enrichment telemetry. Refreshes every 15 seconds." | "Scan and enrichment activity. Updates every 15 seconds." | |
| "Operational telemetry is temporarily unavailable." | "Can't reach the operations data right now." | |
| `Unrecovered failures` | `Failed, needs attention` | |

### 3.9 Admin

| Current | Suggested | Why |
|---|---|---|
| "Control how often connected sources are rescanned. The scheduler creates the work; workers never invent their own loops." | "Control how often connected sources are rescanned." | Drop the second sentence — it reassures the author, not the user. |
| "Per-provider quota and backoff state, so throttling reads as intentional, not failure." | "Rate limits per provider. Throttling here is expected, not a failure." | Same idea, addressed to the reader. |
| "Reconciles missed webhook deliveries and re-checks changed repositories." | "Catches up on anything missed and re-checks changed repositories." | |
| "A non-empty allowlist is exclusive. Prohibited always takes precedence." | "If you list anything as allowed, everything else is blocked. Prohibited always wins." | The current sentence is precise and nearly unparseable. |
| "The picker is limited to the first 2,000 detected and curated technologies." | "Showing the first 2,000 technologies — search to narrow it down." | States a limit; should state the workaround. |
| "Policy saved. Existing repository results are now stale until reevaluated." | "Saved. Re-run the evaluation to update repository results." | Tells you the state; should tell you the next step. |
| "This revision overrides nothing, so every cell uses the reference model default." | "Nothing customised yet — every area uses StackGraph's defaults." | |
| `Fingerprint` | Keep + hover-define | Genuinely useful for support conversations; just needs a definition. |
| Publish warning: "Publishing makes this revision effective for every scope immediately. Drift and conformance across the estate are recomputed against it." | "Publishing applies this standard everywhere, immediately. Your whole estate is re-checked against it." | |

---

## 4. What I would do first

Ordered by benefit against effort.

1. **Ship the `<Term>` component and the glossary above.** One component, one data file. It fixes the largest problem — thirty undefined terms — without touching any layout, and lets the precise vocabulary stay precise.
2. **Delete design-rationale sentences from Admin and Scan.** Pure subtraction, ten minutes, immediately less intimidating.
3. **Fix the three-way `Insights` / `Ask` / `Overview` naming.** Users can't build a mental model of a page that won't say what it is.
4. **Rewrite the four bare error states** (Canvas, Graph, Scenario, Telemetry) onto the pattern Reviews already uses.
5. **Rename the canvas panel's field labels.** Highest jargon density in the product, and the panel is where a user goes specifically to understand something.

Left alone deliberately: Reviews and Modernization are already good, and the ontology terms (`DECLARED` / `OBSERVED` / `INFERRED`, confidence bands, evidence) should be *defined*, not simplified — they are the product's substance.

## 5. One gap worth naming

The design language documents typography, colour, spacing, motion, and iconography — and says nothing about words. Given that this product's entire proposition is stating precisely what it knows and how it knows it, a short voice section would be worth more here than in most products. Two rules would carry most of the weight:

- **Say what happened, then what to do.** Never state a system state without a next step.
- **Explain terms, don't avoid them.** The vocabulary is the product. Undefined vocabulary is the bug.
