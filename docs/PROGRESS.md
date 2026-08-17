# Evaluation Progress

This file is the authoritative record of completed work, active work, evidence,
and blockers. Update it in the same commit that changes a stage's state.

## State vocabulary

| State | Meaning |
|---|---|
| `PENDING` | Not started. |
| `IN_PROGRESS` | Actively being implemented or executed. |
| `BLOCKED` | Cannot proceed without an external input or resource. |
| `VERIFIED` | Required checks and evidence are complete. |
| `COMPLETE` | Verified and no further work is required for this stage. |

## Stage register

| ID | Stage | State | Evidence / transition requirement |
|---|---|---|---|
| S0 | Shared replay core | `COMPLETE` | Chronological replay, profile/query/context intent types, local SQLite ordering, and four automated checks are committed. |
| S1 | MINDsmall train-only tuning | `IN_PROGRESS` | Add a reproducible configuration sweep. Select using train metrics only. |
| S2 | MINDsmall frozen validation | `PENDING` | Run exactly one held-out dev evaluation with the S1 configuration and record all baselines and ablations. |
| S3 | MINDlarge scale confirmation | `BLOCKED` | Requires locally supplied MINDlarge train and dev archives. No tuning is permitted at this stage. |
| S4 | KuaiSAR query-aware replay | `PENDING` | Add actual query-to-caption relevance, multi-action history, and exposed-slate ranking. |
| S5 | Controlled lifecycle validation | `PENDING` | Define deterministic pin, archive, restore, correction, and graph-disconnection scenarios. |

## Evidence recorded so far

### S0 — complete

- Initial implementation: `1d822b2`
- Archive-layout handling: `5071450`
- Non-temporal supplied-history option: `9860702`
- Profile-vector reuse: `74bfad9`
- Current terminology cleanup: `0840e45`
- Automated checks: 4 passing tests.

### Baseline MINDsmall replay — informational only

The default equal-weight configuration is a pipeline check, not a selected
configuration. It uses only timestamped, observed clicks as historical events.

| Split | Eligible episodes | Model | MRR | nDCG@5 | nDCG@10 |
|---|---:|---|---:|---:|---:|
| Train | 106,965 | Profile relevance | 0.2814 | 0.2591 | 0.3168 |
| Train | 106,965 | Frequency | 0.2992 | 0.2796 | 0.3378 |
| Train | 106,965 | Full score | 0.3011 | 0.2822 | 0.3397 |
| Dev | 23,152 | Profile relevance | 0.2567 | 0.2341 | 0.2972 |
| Dev | 23,152 | Frequency | 0.2763 | 0.2558 | 0.3206 |
| Dev | 23,152 | Full score | 0.2742 | 0.2563 | 0.3190 |

Interpretation: interaction evidence outperforms profile relevance, but the
default full score has not yet exceeded frequency on the dev MRR or nDCG@10
measure. S1 must determine whether a train-selected configuration changes that
result; otherwise frequency remains the stronger baseline.

## Next update

S1 will record the candidate configurations, selection metric, selected
configuration, and its train-only score before S2 begins.
