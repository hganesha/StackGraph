Enterprise graph embeddings.

An enterprise application/dependency graph can become much more than a visualization of “what depends on what.” If modeled well, it can answer questions about operational risk, change blast radius, modernization, ownership, cost, resilience, security, and organizational architecture.
A useful model might have nodes such as:
Applications → Services → Deployments → Packages/Libraries → Databases → Infrastructure → APIs → Business Capabilities → Teams
with edges like DEPENDS_ON, DEPLOYED_ON, CALLS, OWNED_BY, IMPLEMENTS, USES_DATA_FROM, etc.
The interesting questions fall into several families.
1. Centrality → “What is secretly critical?”
Plain degree is useful, but betweenness centrality can be especially interesting.
A package/service may have only 15 direct consumers, but if it sits on paths connecting hundreds of applications, it may be an architectural choke point.
Business questions include:
- What components have the largest enterprise-wide dependency footprint?
- Which packages/services are hidden critical infrastructure?
- What components would cause the greatest disruption if unavailable?
- Which internal services deserve higher SRE/support investment?
- Which components are much more important than their current ownership/support tier suggests?
A particularly useful metric is something like:
Business Criticality × Betweenness × Downstream Reach
That tends to produce a much more meaningful “enterprise criticality” score than degree alone.
2. Reachability / transitive dependencies → “What is the blast radius?”
This is probably one of the highest-value graph questions.
Given:
App A → Service B → Package C → Package D
a vulnerability in D affects A even though A doesn't directly know D exists.
Questions:
If component X fails, what applications and business capabilities are potentially affected?

If Log4j/OpenSSL/library X has a vulnerability, where does it ultimately propagate?

If we retire database X, what breaks?

If team Y changes API Z, what is the downstream blast radius?

You can calculate both:
Downstream blast radius
X → *
and
Upstream dependency exposure
* → X
Then weight reachable nodes by business criticality rather than merely counting them.
3. Articulation points / bridges → “What are our single points of failure?”
This can reveal extremely interesting architecture risks.
An articulation point is a node whose removal disconnects parts of the graph.
A bridge is an edge whose removal does the same.
For example:
Payments Apps
      |
      v
 Legacy Integration Service
      |
      v
 Mainframe
That integration service might be the only connection between a large application estate and the mainframe.
Business insight:
“This obscure service is an architectural SPOF for $2B of revenue-generating applications.”
That's much more actionable than “this service has 37 dependencies.”
4. Community detection → “Where are the real architectural domains?”
Run Louvain/Leiden/community detection over the dependency graph.
You may discover clusters like:
Customer apps
   ↕
CRM services
   ↕
Customer databases
without relying on the enterprise's official application taxonomy.
Then ask:
- Do dependency communities correspond to stated business domains?
- Where are the unexpected cross-domain dependencies?
- Are supposed microservices actually one tightly coupled distributed monolith?
- Which applications belong architecturally together despite organizational boundaries?
This can uncover the de facto architecture versus the PowerPoint architecture.
5. Coupling → “Where are modernization efforts likely to fail?”
For each application/system calculate things like:
- inbound degree
- outbound degree
- transitive dependencies
- cross-domain dependencies
- dependency depth
- number of technologies
- number of owning teams
You could derive a coupling/modernization complexity score.
For example:
Application	Direct deps	Transitive deps	Teams	Domains	Modernization risk
A	8	21	2	1	Low
B	27	310	9	6	High
C	14	97	4	3	Medium


This can substantially improve application modernization planning.
6. Subgraph patterns → “What architectural anti-patterns repeat?”
Instead of asking about individual nodes, search for motifs.
For example:
App
 ↓
Shared Service
 ↓
Legacy DB
appearing 400 times.
Or:
App A ──→ DB
App B ──→ DB
App C ──→ DB
App D ──→ DB
indicating shared-database coupling.
Other motifs could identify:
- circular dependencies
- direct DB access bypassing APIs
- unsupported package chains
- shared credentials
- app → app → app dependency chains
- redundant middleware layers
- multiple applications implementing the same capability
This turns architecture standards into graph queries rather than documentation reviews.
7. Similarity → “Why do we have five systems doing the same thing?”
Graph embeddings or simpler neighborhood similarity can identify applications with nearly identical dependency structures.
For example:
App A → Oracle + Kafka + Customer API + Auth
App B → Oracle + Kafka + Customer API + Auth
App C → Oracle + Kafka + Customer API + Auth
Possible insight:
These applications may be consolidation candidates.
Questions:
- Which applications have >80% dependency similarity?
- Which applications implement the same business capability with similar technology?
- Where are there duplicate platforms?
- Which packages/services could be standardized?
This is particularly useful for application portfolio rationalization.
8. Dependency depth → “Where is operational complexity hiding?”
Consider:
App
 ↓
API
 ↓
Service
 ↓
Library
 ↓
Agent
 ↓
Platform
 ↓
Database
Two applications might each have 10 direct dependencies, but one has a maximum dependency depth of 3 and another 17.
Deep dependency chains often correlate with:
- difficult incident diagnosis
- slower deployments
- more organizational coordination
- greater upgrade complexity
- larger vulnerability exposure
So dependency depth itself becomes an interesting enterprise architecture KPI.
9. Ownership graph → “Where does technical architecture conflict with organization design?”
Add:
Component → OWNED_BY → Team
Now you can ask:
Which business transactions cross the most team boundaries?

For example:
Checkout
 ↓
Service A — Team 1
 ↓
Service B — Team 2
 ↓
Service C — Team 3
 ↓
Platform D — Team 4
 ↓
Database — Team 5
A technical dependency graph becomes a Conway's Law analyzer.
Interesting metrics include:
team crossings per business capability
and
cross-team edges / total edges
High values can predict coordination cost.
10. Change propagation → “Which changes are dangerous?”
If you add deployment/change history, the graph gets even more interesting.
Suppose deployments to component X frequently precede incidents in A, B and C.
Now ask:
Which components have historically caused the largest downstream incident footprint?

You can combine topology with observed operational data:
Structural blast radius × historical incident propagation
That produces a much better change-risk score than topology alone.
11. Security → “Where is systemic vulnerability concentrated?”
Overlay CVEs onto package nodes.
You can then answer:
CVE
 ↓
Package
 ↓
Service
 ↓
Application
 ↓
Business Capability
Instead of saying:
1,742 servers contain vulnerable package X.

you can say:
Vulnerability X transitively affects 38 applications, including 4 Tier-1 business capabilities, with 72% of the exposure flowing through two shared platforms.

That's a much stronger executive/security insight.
12. Graph anomalies → perhaps the most interesting category
Rather than defining every architectural rule manually, find nodes whose graph characteristics are unusual.
For example:
“Apps in this domain normally have 5–15 dependencies. This application has 93.”
Or:
“Services of this type normally serve 3 applications. This one serves 147.”
Or:
“These two systems are classified as unrelated but share 91% of their dependency neighborhood.”
Graph anomaly detection can reveal things you weren't specifically looking for.
I would build an “Enterprise Graph Intelligence” layer around ~8 derived signals
For every application/component, calculate:
Signal	Interpretation
In-degree	How many things rely on me?
Out-degree	How much do I rely on?
Transitive reach	True blast radius
Betweenness	Am I a hidden choke point?
PageRank/eigenvector centrality	Am I connected to important things?
Dependency depth	How complex is my stack?
Community membership	What architecture/domain do I really belong to?
Articulation/bridge score	Am I a structural SPOF?


Then enrich those with business attributes:
revenue impact + business criticality + incidents + CVEs + cost + lifecycle/EOL + team ownership + deployment frequency.
That's where the graph becomes genuinely powerful.
For example, instead of ranking components by centrality, rank:
Modernization Priority = EOL Risk × Business Criticality × Transitive Reach × Centrality × Change Failure Rate
or:
Systemic Risk = Vulnerability Severity × Reachability × Business Criticality × SPOF Score
The key idea is that graph metrics become much more valuable when multiplied by business context. A highly central component supporting internal cafeteria scheduling isn't necessarily important; a moderately central component sitting in the payment authorization path might be extremely important.
A particularly compelling end state is a natural-language interface where an executive or architect can ask: “What are the top 10 architectural risks that could affect customer checkout, why are they risky, and which modernization investments would reduce the most systemic risk?” The graph gives the structural reasoning needed to answer that rather than merely retrieving metadata.