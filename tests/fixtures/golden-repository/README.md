# Golden repository corpus

The versioned corpus the Phase 2 plan's §9.1 correctness objectives are measured against.
Without it, "canonical entity precision above 99%" and "no regression beyond 0.25 percentage
points" are sentences rather than gates.

## Layout

```
<case>/case.json   the label set
<case>/repo/       the fixture repository tree
```

A case with a `generate` block has its tree expanded at evaluation time. Large-repository
behaviour is a bounds property, and committing ten thousand near-identical files would make the
corpus expensive to review for no extra signal.

## What a label means

`expect.facts` are facts the scanner **must** emit. A missing one is a false negative.

`expect.absent_facts` are facts the scanner **must not** emit. These are the corpus's real
value: each one is a false positive somebody reviewed and ruled out — a dependency belonging to
a vendored package, a component the repository does not own, a sibling monorepo app dragged
into another's blast radius, declared configuration presented as a verified live deployment.
A present one is a false positive.

Precision and recall are computed over the labelled set only. Unlabelled facts are neither
credited nor penalised, because nobody has reviewed them. The corpus improves by labelling
more, never by assuming that silence means correctness.

Every matcher field is a wildcard when unset, so a label states exactly as much as its author
is willing to defend. Add a `note` explaining *why* a fact must or must not appear; a label
without a reason cannot be re-reviewed later.

## Cases

| Case | Protects |
| --- | --- |
| `npm-single-app` | Component promotion, declared dependencies, database inference from a driver, unused-dependency findings |
| `python-library` | PyPI requirement parsing, the pinned-version `PackageVersion` identity split, `LIBRARY_PACKAGE` |
| `pnpm-monorepo` | The S1 exit gate: `apps/payment-api` impact must not reach `apps/customer-ui` |
| `containerized-service` | Container build and base-image edges, compose workloads, declared-not-verified deployment |
| `kubernetes-terraform` | Provider detection and typed deployment edges instead of one lossy `hosted_on` tag |
| `serverless-app` | Serverless provider attribution and scoped-package purl encoding |
| `data-analytics` | dbt, notebook, SQL-migration, and data classifications |
| `malformed-input` | §9.1's rule that partial input never asserts absence |
| `generated-vendor-tree` | Installed and vendored trees never become owned components or dependencies |
| `large-bounded-repo` | Bounded scanning under a hard file limit, reported as `PARTIAL` |

## Running

```sh
make golden-corpus            # score and write artifacts/golden-corpus.json
make golden-corpus-compare    # fail if precision or recall regressed past the margin
make scanner-benchmark        # §9.2 latency, peak RSS, and throughput
```

The pytest gate (`services/enterprise-discovery/tests/test_golden_corpus.py`) runs in the
standard discovery suite and holds precision and recall at 1.0, because every expectation here
is curated rather than sampled.

## Adding a case

1. Write the tree under `<case>/repo/`.
2. Run the scanner against it and read the output before writing any label.
3. Label only what you can justify, and write the justification in `note`.
4. Add at least one `absent_facts` probe. A case that cannot fail on a false positive is not
   pulling its weight.
5. Add the case identifier to `test_the_corpus_covers_every_shape_the_plan_names`, so the
   corpus cannot silently shrink while the score still reads 100%.
