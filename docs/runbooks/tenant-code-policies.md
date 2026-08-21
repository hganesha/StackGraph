# Tenant code-policy governance

Tenant code policies define which technologies may implement a technical function and which are
strictly prohibited. They are managed in **Admin → Code Policies** and are isolated by tenant.

## Classification boundary

StackGraph's curated technology-to-function catalog remains the primary classifier. A tenant can
add a custom function for internal or otherwise unclassified usage, but cannot replace or retire a
primary function. Selecting a detected technology in a custom function acts as a governed overlay;
it does not rewrite the global catalog.

For each function:

- a non-empty allowed list is exclusive: another technology classified to that function is reported
  as `NOT_ALLOWED`;
- a prohibited technology is reported as `PROHIBITED` and takes precedence over the allowlist;
- the same technology cannot appear in both lists;
- retiring a custom function removes it from the active policy-set fingerprint without deleting its
  audit history.

## Repository evaluation

`POST /api/v1/admin/code-policies/evaluations` evaluates every tenant repository from current
`DEPENDS_ON`, `USES`, `RUNS_ON`, `BUILT_ON`, and `HAS_VERSION` facts. Catalog aliases are resolved to
their curated technology before policy matching. Every violation retains the source fact IDs used
for the decision.

Results are immutable for a `(repository, policy-set fingerprint, evidence fingerprint)` input. The
Admin console marks a result `STALE` when either the policy set changes or the repository's current
technology evidence differs from the evaluated fact set. Re-run the evaluation after a policy change
or completed repository scan.

Unclassified technologies are reported separately. Create a custom function and assign the detected
technology to an allowed or prohibited list to bring that usage under explicit tenant governance.

## Audit and rollout

Function-policy writes and estate evaluations append `admin_audit_log` records. For a pilot rollout:

1. Govern one well-understood primary function, such as client state management.
2. Evaluate the estate and review evidence for every misalignment.
3. Add custom functions only where the primary catalog genuinely lacks tenant context.
4. Re-scan representative repositories, confirm results become stale, and reevaluate.
5. Treat policy results as advisory until owners have reviewed false positives and classification gaps.
