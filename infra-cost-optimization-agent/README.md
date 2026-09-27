# CostGuard

CostGuard is a cross-platform cloud infrastructure cost-optimization agent.
It analyzes resource utilization, recommends cost-saving actions, classifies
each one's risk, and — for the safest ones only — executes them automatically.
Everything else waits for a human.

## Safety model (read this first)

- **`plan` is always a dry run.** It never changes anything. `apply` is the
  only command that executes actions.
- **Production-tagged or completely untagged resources are never
  auto-executed — no exceptions, and this cannot be turned off via config.**
  It's hardcoded in `src/risk_classifier.py`. Untagged resources are treated
  as the *highest* risk, not the lowest.
- Only **LOW**-risk actions on tagged, non-production resources are ever
  auto-executed: deleting orphaned volumes, releasing unused Elastic IPs,
  and stopping (never terminating) idle dev/test instances outside business
  hours.
- **MEDIUM** (resize down a tier, switch to spot) and **HIGH** (production
  resources, database resizes, cross-region migration, critical=true, or
  no tags at all) always require explicit approval — via the CLI, a
  webhook, or by editing `state/approvals.json`.
- A **blast-radius cap** (`max_auto_actions_per_run` in `config/thresholds.yaml`,
  default 10) limits how many actions a single `apply` run can auto-execute.
- Every execution is written to an append-only audit log
  (`logs/audit.jsonl`) with what changed, who/what approved it, and the
  exact rollback command.
- A **dead-man's switch**: if there isn't enough utilization data for a
  resource (a metrics gap, or it's younger than the lookback window),
  CostGuard skips it rather than guessing.

## Supported providers

| Provider | Services | Status |
|---|---|---|
| AWS | EC2, EBS, Elastic IPs, RDS | Fully implemented |
| Azure | VMs, Managed Disks, SQL Database | Stub adapter (TODO) |
| GCP | Compute Engine, Persistent Disks, Cloud SQL | Stub adapter (TODO) |

Adding a new provider or service means writing one new adapter implementing
`CloudProvider` in `src/providers/` — nothing else in the codebase needs to
change.

## Setup

```bash
cp .env.example .env    # fill in credentials / profile names
pip install -r requirements.txt
```

Cloud credentials always come from environment variables or each SDK's
default credential chain (an AWS profile, `DefaultAzureCredential`,
Application Default Credentials) — never from a config file.

Edit `config/providers.yaml` to list the accounts/subscriptions/projects to
scan, `config/thresholds.yaml` for idle cutoffs and the lookback window, and
`config/tag_policy.yaml` for which tag keys/values mean prod/dev/critical.

## Workflow

```bash
# 1. See what CostGuard would recommend — makes no changes.
python src/main.py plan

# 2. Decide on anything that needs approval, either:
python src/main.py apply --interactive     #   ...prompt for each on the CLI, or
#   edit state/approvals.json directly (flip "status" to "approved"/"denied"), or
#   configure APPROVAL_WEBHOOK_URL in .env to get notified elsewhere

# 3. Execute: auto-executes LOW-risk findings, plus anything now approved.
python src/main.py apply

# 4. Made a mistake, or the app just needs it back? Roll it back.
python src/main.py rollback <finding_id>

# 5. See what's been saved, and what's still waiting on a human.
python src/main.py report
```

`python src/main.py analyze` runs just the data-collection step, useful for
sanity-checking connectivity before generating a plan.

## Tests

```bash
pip install -r requirements.txt
pytest tests/
```

`test_risk_classifier.py` and `test_recommender.py` use mocked utilization
data — no live cloud calls, no credentials required.

## Project layout

```
config/
  thresholds.yaml    # idle cutoffs, lookback window, blast-radius cap
  tag_policy.yaml    # which tag keys/values mean prod / dev-test / critical
  providers.yaml     # which accounts/subscriptions/projects to scan
src/
  main.py            # CLI: analyze / plan / apply / rollback / report
  analyzer.py         # loads config, builds providers, aggregates metrics
  recommender.py      # turns metrics into findings (dead-man's switch lives here)
  risk_classifier.py  # LOW/MEDIUM/HIGH + the hardcoded prod/untagged gate
  executor.py          # executes findings, persists rollback records
  approval.py          # CLI / file / webhook approval store
  audit_log.py         # append-only audit trail + structured JSON logging
  providers/
    base.py            # CloudProvider interface every adapter implements
    aws_provider.py     # full implementation
    azure_provider.py   # stub
    gcp_provider.py      # stub
tests/
  test_risk_classifier.py
  test_recommender.py
```
