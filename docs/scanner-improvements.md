# Phase 2 Scanner Improvements


The scanner is currently leaving value on the table if it primarily extracts dependencies/entities. A repository is one of the richest evidence sources in the enterprise. If we're already paying the cost to clone/read/parse it, we should produce a **Repository Intelligence Profile** that captures structure, execution model, deployment topology, containers, ownership/change patterns, and temporal behavior.

The important distinction: don't turn this into a pile of tags. These signals should become **typed StackGraph facts and relationships** because they substantially improve recommendations and the Change Compiler.

### 1. Repository classification should become first-class

A repository should be able to have multiple classifications rather than one simplistic `repo_type`.

For example:

```text
github:acme/customer-platform

RepositoryProfile

architecture
  MONOREPO

contains
  FRONTEND_APP
  API_SERVICE
  SHARED_LIBRARY
  DATABASE_MIGRATIONS

frameworks
  Next.js
  FastAPI

data_workloads
  none

deployment_profiles
  VERCEL
  AWS

confidence
  0.98
```

Another:

```text
github:acme/customer-analytics

architecture
  DATA_PLATFORM_REPO

contains
  DATABRICKS_JOBS
  DLT_PIPELINES
  NOTEBOOKS
  DBT_PROJECT
  SQL_MIGRATIONS

deployment_profiles
  DATABRICKS
  AZURE
```

Useful classifications go much further than `frontend/backend`.

I'd detect things like monorepo, full-stack application, microservice, library/package, CLI, IaC repo, data/analytics repo, Databricks bundle/job, Fabric project, dbt project, ML project, notebooks, SQL/schema migration repo, API definitions, documentation, mobile application, serverless app, platform repo, GitOps repo and deployment-only repo.

And importantly:

```text
Repository
   HAS_COMPONENT → Component
```

rather than pretending one repository has one identity.

A monorepo may contain 30 independently deployable components.

---

## 2. Introduce `Component` between repository and application/service

I think this is actually a necessary graph-model enhancement.

Today many enterprise graphs jump:

```text
Repository → Application
```

That breaks down for monorepos.

Instead:

```text
Repository
   │
   ├─ CONTAINS → WebApp
   │
   ├─ CONTAINS → PaymentAPI
   │
   ├─ CONTAINS → Worker
   │
   ├─ CONTAINS → SharedLibrary
   │
   └─ CONTAINS → SQLMigrations
```

Each component can independently have:

```text
language
framework
package ecosystem
build system
runtime
container
deployment profile
data dependencies
APIs
ownership
entry points
```

That will dramatically improve blast-radius precision.

Instead of:

> "Repo X is affected."

you can eventually say:

> "`apps/payment-api` is affected; `apps/customer-ui` in the same monorepo is not."

That's a meaningful maturity jump.

---

## 3. Docker/container resolution is absolutely worth doing

I'd treat containers as real graph entities.

From:

```dockerfile
FROM python:3.13-slim
...
```

derive:

```text
Component
   BUILDS → ContainerImage

ContainerImage
   BASED_ON → python:3.13-slim
```

But go farther when the image can be resolved:

```text
ContainerImage
  digest
  registry
  architecture
  OS
  base layers
  packages
  runtimes
  exposed ports
  entrypoint
  user
```

Potential graph:

```text
Service
   ↓ DEPLOYED_AS
ContainerImage
   ↓ BASED_ON
BaseImage
   ↓ CONTAINS
OSPackage
   ↓
Runtime / Library
```

This makes questions possible such as:

> "If Debian base image X becomes unsupported, what is affected?"

or:

> "Which production workloads contain Log4j even though the application manifests don't declare it?"

or:

> "How many different Python runtime images do we actually ship?"

That feeds directly into both recommendation and simulation.

For implementation, image **digest** should be the canonical identity wherever possible. Tags such as `latest` aren't identities.

---

## 4. Deployment Profile should be a major concept

Your list—Supabase, Vercel, AWS, GCP, Azure, Databricks, Fabric, Runway, etc.—is exactly where I'd go.

But model it as detected **deployment capabilities**, not simply `hosted_on`.

For example StackGraph detects:

```text
vercel.json
package.json
next.config.ts
```

and derives:

```text
DeploymentProfile

provider     VERCEL
workload     WEB_APPLICATION
evidence
  vercel.json
  framework configuration

confidence   0.99
```

Another repository:

```text
databricks.yml
resources/jobs.yml
notebooks/
```

becomes:

```text
DeploymentProfile

provider     DATABRICKS
workload     JOB
resources
  4 workflows
  17 tasks
```

An enterprise app may have multiple:

```text
Application
   ├─ DEPLOYS_TO → Vercel
   ├─ USES → Supabase
   ├─ STORES_DATA_IN → Azure
   └─ RUNS_JOBS_ON → Databricks
```

That's much richer than saying "cloud = Azure."

---

## 5. Detecting deployment profiles gives you architectural inference

This is where this becomes much more than inventory.

Suppose StackGraph sees:

```text
Next.js
Vercel
Supabase
Stripe
GitHub Actions
OpenAI
```

It can derive an architecture profile:

```text
Web application
 ├─ frontend/server runtime: Vercel
 ├─ database/auth: Supabase
 ├─ payments: Stripe
 ├─ CI/CD: GitHub Actions
 └─ AI dependency: OpenAI
```

Now compare that to another service:

```text
.NET
AKS
Azure SQL
Key Vault
Service Bus
Azure DevOps
```

The estate begins to expose **architectural archetypes**.

That allows StackGraph to discover:

```text
Architecture archetypes

Serverless SaaS stack       84 apps
Azure enterprise stack     312 apps
Databricks data stack       67 repos
Legacy Java middleware     119 apps
Bespoke / anomalous         28 apps
```

And then recommendations become much smarter:

> "These 14 applications appear functionally identical to your standard Vercel/Supabase architecture but use a bespoke deployment pattern."

That's extremely valuable.

---

# The temporal dimension may be even more important

I strongly agree with you here.

Right now most enterprise estate systems capture:

```text
STATE
What exists now?
```

StackGraph should capture:

```text
STATE + BEHAVIOR
What exists?
How did it get here?
How fast is it changing?
Who/what changes it?
```

A repo's history can yield signals such as:

```text
RepositoryActivityProfile

age
4.2 years

commits_90d
287

PRs_90d
73

contributors_90d
14

change_velocity
HIGH

deployment_frequency
DAILY

dependency_change_rate
12/month

major_refactors_12m
3

ownership_concentration
0.61

hotspots
  src/payments/
  src/auth/

stability
MODERATE
```

Now risk becomes dramatically better.

Two services may have identical dependency graphs.

But:

```text
Service A
47 changes/week
14 active maintainers
95% test coverage
daily releases
```

versus:

```text
Service B
last meaningful change 18 months ago
1 maintainer
unknown deployment pipeline
no integration tests
```

An upgrade should not get the same risk score.

---

# PR intelligence is worth extracting

Absolutely capture things like:

```text
PR count
merge frequency
time-to-merge
review depth
reviewer count
change size
revert frequency
failed builds
dependency PRs
automated PRs
AI-assisted PR signals
human-generated PR signals
```

But I would be careful with **AI vs human**.

Don't claim:

```text
AI generated this code
```

unless there is authoritative evidence.

Instead model:

```text
AuthorshipSignal

source:
  GitHub Copilot metadata

type:
  AI_ASSISTED

confidence:
  HIGH
```

versus:

```text
source:
  commit style + PR text + code patterns

type:
  POSSIBLY_AI_ASSISTED

confidence:
  LOW
```

There are legitimate signals:

- known bot accounts;
- Copilot/agent metadata when exposed;
- PR provenance from coding-agent workflows;
- standardized generated commit/PR messages;
- agent branch conventions;
- API/tool integration metadata.

Code-style detection by itself should never be considered authoritative.

That distinction will matter increasingly as enterprises want to ask:

> "What percentage of changes are agent initiated?"

or more importantly:

> "Do AI-authored changes behave differently?"

---

# That leads to a fascinating future dataset

Instead of being obsessed with:

```text
AI vs Human
```

I'd collect:

```text
ChangeActor

HUMAN
BOT
DEPENDENCY_BOT
CI_AUTOMATION
AI_AGENT
AI_ASSISTED_HUMAN
UNKNOWN
```

Then correlate with outcome.

StackGraph could eventually discover:

```text
Changes over last 90 days

Human initiated              62%
AI assisted                  23%
AI agent                      8%
Automation                    7%

Rollback rate
Human                       1.8%
AI assisted                 1.5%
AI agent                    3.1%

Average review time
Human                      14.2h
AI assisted                 7.8h
AI agent                    2.4h
```

I'm using illustrative numbers there, but **the model itself is extremely valuable**.

Now StackGraph becomes capable of understanding how AI adoption is actually changing an engineering estate.

---

# Temporal signals deserve their own graph model

I would avoid stuffing everything into current-state properties like:

```text
repo.prCount = 482
```

Keep current aggregates for query speed, but introduce an event model conceptually:

```text
Repo
 │
 ├─ OBSERVED_EVENT → Commit
 ├─ OBSERVED_EVENT → PullRequest
 ├─ OBSERVED_EVENT → Release
 ├─ OBSERVED_EVENT → Deployment
 ├─ OBSERVED_EVENT → DependencyChange
 ├─ OBSERVED_EVENT → ArchitectureChange
 └─ OBSERVED_EVENT → Incident
```

You don't necessarily need every Git commit represented as a heavyweight graph node forever. A historical/event store plus graph-derived summaries may be better.

But conceptually StackGraph should support:

```text
Estate(t)
```

rather than only:

```text
Estate(now)
```

That's fundamental to the Change Simulator because eventually:

```text
Observed historical mutation
        ↓
Graph at time t
        ↓
Actual outcome
```

becomes training/evidence for future simulations.

---

# I'd introduce a `RepositoryFingerprint`

One scanner output could be something like:

```text
RepositoryFingerprint
────────────────────────────────

Identity
github:acme/payments

Structure
MONOREPO

Components
3 applications
2 services
4 shared libraries
1 migration project

Languages
TypeScript 62%
Python     28%
SQL        10%

Frameworks
Next.js
FastAPI

Data
PostgreSQL
Supabase

Containers
3 images
python:3.13-slim
node:22-alpine

Deployment profiles
Vercel
Supabase
GitHub Actions

Architecture
FULL_STACK_WEB
API_BACKEND
ASYNC_WORKER

Activity
84 PRs / 90d
18 contributors
HIGH change velocity

Change actors
Human dominant
AI-assisted observed
Dependabot active

Lifecycle
ACTIVE

Confidence
0.97
```

And every line should link back to evidence.

That's an extremely compelling "repo page" too.

---

# More importantly, this gives the Recommendation Engine vastly better features

Today a recommendation might be driven by:

```text
package version
runtime version
dependency
```

Tomorrow:

```text
RecommendationContext

technical state
+ architectural archetype
+ deployment profile
+ business criticality
+ change velocity
+ maintainer activity
+ historical upgrade behavior
+ container composition
+ test posture
+ AI change rate
```

Now you can make differentiated recommendations such as:

> "Do not prioritize this Java upgrade despite its age: the application has been inactive for 24 months and is scheduled for retirement."

or:

> "Prioritize these 23 repositories first. They match the organization's standard architecture profile, have active maintainers, automated testing, and historically successful runtime upgrades."

That's much closer to how a good enterprise architect reasons.

---

# And it materially improves the Change Compiler

This is the important strategic point.

Everything you've described feeds the capability we're discussing:

```text
                    REPOSITORY SCANNER
                           │
     ┌─────────────────────┼──────────────────────┐
     ↓                     ↓                      ↓
Structure             Runtime state        Temporal state
     │                     │                      │
components             containers               PRs
architecture           deployment               commits
frameworks             dependencies              actors
data workloads         infrastructure            velocity
     │                     │                      │
     └─────────────────────┼──────────────────────┘
                           ↓
                    STACKGRAPH ESTATE
                           ↓
                    CHANGE COMPILER
                           ↓
                       SIMULATION
```

So I would not see this as scope creep.

I see it as **improving the sensory system of StackGraph**.

The Change Compiler can only be as intelligent as the estate representation underneath it.

---

## What I would prioritize

If we're updating the Phase 2 roadmap, I'd put the scanner work roughly in this order:

1. **Component decomposition + repo classification.** This fixes the abstraction level, especially for monorepos.
2. **Deployment profile detection.** Very high information value for relatively modest scanning effort.
3. **Container/image intelligence.** Important for true runtime composition and transitive dependencies.
4. **Temporal/change profile.** PRs, commits, deployments, contributors, velocity, hotspots.
5. **Change actor provenance.** Human/bot/agent/AI-assisted where reliable evidence exists.
6. **Architecture archetype inference.** Once the lower-level facts are solid, derive standard estate patterns.

I would make all six part of Phase 2, although only the first three necessarily need to block the initial simulator MVP.

The broader strategic shift is worth making explicit:

> **StackGraph shouldn't just index enterprise assets. It should fingerprint how each asset is built, packaged, deployed, operated, changed, and evolved.**

That richer estate model is exactly what makes a deterministic enterprise Change Compiler defensible rather than just another graph traversal tool.
