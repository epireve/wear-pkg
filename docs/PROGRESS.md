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
| S1 | MINDsmall train-only tuning | `COMPLETE` | Six variants were evaluated on train only; `a065_frequency_h72` was selected by nDCG@10. |
| S2 | MINDsmall frozen validation | `COMPLETE` | The frozen full score exceeds frequency on held-out dev nDCG@10 and MRR. |
| S3 | MINDlarge scale confirmation | `BLOCKED` | Requires locally supplied MINDlarge train and dev archives. No tuning is permitted at this stage. |
| S4 | KuaiSAR query-aware replay | `IN_PROGRESS` | Begin with the direct-download small release; add actual query-to-caption relevance, multi-action history, and exposed-slate ranking. |
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

### S1 — complete

- Selection run: `results/mindsmall-train-sweep.json` (local, not committed)
- Eligible episodes: 156,073
- Selection metric: nDCG@10
- Selected variant: `a065_frequency_h72`
- Selected train nDCG@10: 0.3785
- Frequency-only train nDCG@10: 0.3713
- Frozen configuration: `configs/mindsmall-frozen.json`

The selection was performed entirely on the MINDsmall train split. The next
run must use the frozen values unchanged on the dev split.

### S2 — complete

- Frozen run: `results/mindsmall-dev-frozen.json` (local, not committed)
- Eligible episodes: 71,745
- Full score: MRR 0.3464, nDCG@5 0.3305, nDCG@10 0.3897
- Frequency baseline: MRR 0.3411, nDCG@5 0.3244, nDCG@10 0.3843
- Difference versus frequency: +0.0054 MRR, +0.0061 nDCG@5, +0.0054 nDCG@10

The held-out result preserves the train-selected improvement over frequency.
It completes the MINDsmall stage. The configuration is frozen for S3; changing
it would require a new, separately documented selection stage.

### S4 — in progress

- Downloaded release: KuaiSAR-small (`KuaiSAR.zip`)
- Archive SHA-256: `ed8afa12196cbf18a719511a03b0915522c4039a6c08ce306df69aaeddb9fa1c`
- Extracted source rows: 3,171,232 search candidates; 7,493,102 recommendation events; 4,157,219 item records.
- Implemented fields: actual query-to-caption lexical relevance, exposure-bound search slates, historical recommendation/search actions, and author/category graph support.
- Pending evidence: derived SQLite index, bounded smoke replay, and metric output.

## Next update

S4 will record the KuaiSAR release checksum, schema inspection, and the first
query-aware replay configuration.
