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
| S0 | Shared replay core | `COMPLETE` | Chronological replay, profile/query/context intent types, local SQLite ordering, and eight automated checks are committed. |
| S1 | MINDsmall train-only tuning | `COMPLETE` | Six variants were evaluated on train only; `a065_frequency_h72` was selected by nDCG@10. |
| S2 | MINDsmall frozen validation | `COMPLETE` | The frozen full score exceeds frequency on held-out dev nDCG@10 and MRR. |
| S3 | MINDlarge scale confirmation | `COMPLETE` | The S1-frozen configuration was run unchanged on labeled dev and exceeds frequency on MRR, nDCG@5, and nDCG@10. |
| S4 | KuaiSAR query-aware replay | `COMPLETE` | Graded nDCG correction preserved the train-selected configuration; the corrected frozen later-segment replay exceeds frequency on MRR, nDCG@5, and nDCG@10. |
| S5 | Controlled lifecycle validation | `COMPLETE` | Deterministic pin, archive, restore, correction, and graph-disconnection transitions all pass their asserted ranking invariants. |
| S6 | RLKWiC context-and-graph validation | `COMPLETE` | The train-selected context-and-graph score is frozen and exceeds direct event matching on the later human-scored segment; the small participant count remains an explicit limitation. |
| S7 | Paired uncertainty checks | `COMPLETE` | MINDlarge and corrected KuaiSAR have entirely positive user-cluster nDCG@10 intervals; RLKWiC is inconclusive at its small participant count. |
| S8 | Frozen signal-ablation diagnostics | `COMPLETE` | Fixed full-versus-signal-removal comparisons are complete with 1,000 paired user-cluster resamples; no configuration was selected. |
| S9 | Controlled StableLow archive policy | `COMPLETE` | The policy, reason codes, safety gates, and eight deterministic end-to-end scenarios are implemented and verified. |

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

### S4 — complete

- Downloaded release: KuaiSAR-small (`KuaiSAR.zip`)
- Archive SHA-256: `ed8afa12196cbf18a719511a03b0915522c4039a6c08ce306df69aaeddb9fa1c`
- Extracted source rows: 3,171,232 search candidates; 7,493,102 recommendation events; 4,157,219 item records.
- Implemented fields: actual query-to-caption lexical relevance, exposure-bound search slates, historical recommendation/search actions, and author/category graph support.
- Derived SQLite index: 4,157,218 items; 267,608 search sessions; 3,171,231 shown search candidates; 7,493,101 recommendation events.
- Smoke replay: 1,000 chronological sessions requested; 955 sessions with a positive label evaluated.
- Smoke output: `results/kuaisar-small-smoke.json` (local, not committed).
- Temporal partitioning verified: an 80/20 global session-time split has cutoff `2023-05-28T01:44:45.498000+00:00`; events at the same timestamp are excluded from the current session's history.
- Automated checks: 7 passing tests, including a synthetic single-boundary temporal partition test.
- Original train-only selection was recorded using a binary-only nDCG denominator even though `click_cnt` is graded. The original MRR values remain valid; its nDCG values are superseded.
- Corrected train-only selection: `results/kuaisar-small-train-sweep-corrected.json` (local, not committed); 267,608 sessions, 80/20 timestamp split, graded nDCG@10 selection metric.
- Selected variant remains `a050_balanced_h24`; full score nDCG@10 0.4968, compared with frequency 0.4926.
- Frozen configuration: `configs/kuaisar-frozen.json`; it must be run unchanged on the later time segment.
- The previously recorded frozen held-out nDCG values are superseded by the
  corrected replay. The configuration itself remains unchanged.
- Corrected frozen held-out run: `results/kuaisar-small-dev-bootstrap-corrected.json` (local, not committed); 33,433 sessions with a positive label evaluated.
- Full score: MRR 0.4369, nDCG@5 0.4241, nDCG@10 0.4966.
- Frequency baseline: MRR 0.4292, nDCG@5 0.4166, nDCG@10 0.4898.
- Difference versus frequency: +0.0077 MRR, +0.0075 nDCG@5, +0.0068 nDCG@10.

The corrected later-segment result uses the unchanged train-selected
configuration and exceeds frequency on every recorded metric. S4 is complete.

### S3 — complete

- Source archives moved to `data/source_archives/` and extracted locally.
- Archive SHA-256: train `120dbabba3c889b47f55070bdfe37ba1384c1aa5a3db20fac468d6c695e46840`; dev `a9ce423cf21b1040e8bafb03ee7283cf5cb170b727e3c49fc054ca0b754e66c8`; test `bad558abb96ebdce67a89b60e626da49e7489a82f79e5994dd2cc000b9b693e6`.
- Extracted rows: train 101,527 items / 2,232,748 impressions; dev 72,023 items / 376,471 impressions; test 120,961 items / 2,370,727 impressions.
- Frozen run: `results/mindlarge-dev-frozen.json` (local, not committed).
- Eligible episodes: 369,454.
- Full score: MRR 0.3469, nDCG@5 0.3307, nDCG@10 0.3903.
- Frequency baseline: MRR 0.3435, nDCG@5 0.3260, nDCG@10 0.3860.
- Difference versus frequency: +0.0034 MRR, +0.0047 nDCG@5, +0.0043 nDCG@10.

The S1-frozen configuration was applied unchanged to the labeled dev split;
the train and test splits did not influence configuration selection. The
improvement over frequency is smaller than on MINDsmall but remains positive
on every recorded ranking metric.

### S5 — complete

- Suite: `results/lifecycle-validation.json` (local, not committed).
- Command: `wear-pkg lifecycle-run --output results/lifecycle-validation.json`.
- Result: 4 of 4 deterministic state-transition scenarios passed.
- Pin/unpin: a pinned item overrides ordinary score order, and unpinning
  restores the original order.
- Archive/restore: an archived item is removed from the candidate set; a
  restored item becomes eligible again at its ordinary score.
- Correction redirect: an outdated item resolves to its correction and never
  surfaces separately.
- Graph disconnection: removing the only graph edge reduces its graph feature
  to zero and removes its ranking advantage.

### S6 — complete

- Downloaded source archive: `RLKWiC.zip` (local, ignored); SHA-256 `e7594a1a054425e10a08ba98ce2be7088d1cfda82eb25d0f6fa5b88f513bf1dd`.
- Downloaded human-score files: `Recommendations.csv` SHA-256 `f4f7efae7c6b2d43d93266b08e1ae589ff2fb8c0a191f49823a4c7b12e962380`; `Scores.csv` SHA-256 `717dfb030acee9f034a2ca3b9a92c5c40fefebe8f1401d75ab89b22ad2552b54`.
- Extracted only participant contexts, events, KG resources/triples, sessions,
  and term tables needed for replay.
- Replay unit: timestamped recommendation slates with at least two candidates
  and at least one human-positive score; 278 such slates are available.
- Train-only selection: `results/rlkwic-train-sweep.json` (local, not
  committed); 207 eligible slates, 80/20 timestamp split, nDCG@10 selection
  metric.
- Selected variant: `a080_equal_h24`; full score nDCG@10 0.9469. The
  event-lexical baseline is higher at 0.9504, so this benchmark must not be
  presented as evidence that the full score dominates direct event matching.
- Frozen configuration: `configs/rlkwic-frozen.json`; it must be run unchanged
  on the later time segment.
- Frozen held-out run: `results/rlkwic-dev-frozen.json` (local, not committed);
  55 eligible human-scored slates evaluated.
- Full score: MRR 0.9727, nDCG@5 0.9681, nDCG@10 0.9701.
- Direct event-lexical baseline: MRR 0.9606, nDCG@5 0.9635, nDCG@10 0.9656.
- Difference versus direct event matching: +0.0121 MRR, +0.0046 nDCG@5,
  +0.0045 nDCG@10.

The later-segment result uses the train-selected configuration unchanged. It
reverses the small train-segment deficit against direct event matching, but its
55-slate / eight-participant scope means it is evidence of construct behavior,
not a scale estimate. S6 is complete.

### S7 — complete

- Method: 1,000 deterministic paired bootstrap resamples at the user cluster
  level, seed `20260818`.
- Comparisons: MINDlarge full score versus frequency; KuaiSAR full score versus
  frequency; RLKWiC full score versus direct event matching.
- Output fields: point difference, percentile 95% interval, and share of
  resamples above zero for MRR, nDCG@5, and nDCG@10.
- MINDlarge versus frequency: nDCG@10 +0.0043, 95% interval [+0.0038,
  +0.0048], 100.0% positive draws; 251,721 user clusters / 369,454 episodes.
- Corrected KuaiSAR versus frequency: nDCG@10 +0.0068, 95% interval
  [+0.0047, +0.0092], 100.0% positive draws; 6,787 user clusters / 33,433
  sessions.
- RLKWiC versus direct event matching: nDCG@10 +0.0045, 95% interval
  [-0.0217, +0.0439], 54.7% positive draws; 6 user clusters / 55 slates.

MINDlarge and corrected KuaiSAR have stable positive intervals. RLKWiC's
point estimate remains positive but is inconclusive at its available scale.

## Next update

### S8 — complete

- Purpose: identify the contribution of each signal family without changing
  any selected value or treating the held-out partition as a new tuning set.
- Frozen MINDlarge diagnostic configuration:
  `configs/mindlarge-frozen-ablations.json`.
- Frozen KuaiSAR diagnostic configuration:
  `configs/kuaisar-frozen-ablations.json`.
- Protocol: the existing full configuration is the declared reference. Each
  ablation removes exactly one salience signal and renormalises the remaining
  signal weights; alpha, history rules, time split, half-life, labels, and
  bootstrap seed remain fixed. The existing frequency baseline is retained in
  each replay output.
- Inference: 1,000 paired user-cluster bootstrap samples, seed `20260818`,
  compare the unchanged full configuration with each removal. These are
  diagnostic follow-on analyses, not additional configuration selection.
- MINDlarge output: `results/mindlarge-dev-ablations.json` (local, not
  committed). Full nDCG@10 0.3903. Removing frequency reduced nDCG@10 by
  0.0153 (95% interval [+0.0148, +0.0159]); removing context reduced it by
  0.0020 ([+0.0018, +0.0022]). Graph removal was inconclusive (+0.0002,
  [-0.0001, +0.0004]), while removing recency improved nDCG@10 by 0.0006
  (full-minus-ablation interval [-0.0008, -0.0005]).
- KuaiSAR output: `results/kuaisar-small-dev-ablations.json` (local, not
  committed). Full nDCG@10 0.4966. Removing graph reduced it by 0.0050
  ([+0.0042, +0.0058]) and removing recency reduced it by 0.0023
  ([+0.0017, +0.0030]). Removing action, frequency, or context instead
  improved the fixed score; these components are not supported at equal
  weighting on this later segment.
- The initial MINDlarge output was produced before generic sweep reporting was
  corrected to label comparison files as diagnostics. Commit `182c781`
  supersedes that presentation label: no configuration was selected, and no
  fixed value changed.

### S9 — complete

- Policy implementation: `ArchivePolicy` in `src/wear_pkg/lifecycle.py`.
- Fixed rule: recommend an item only when its bounded interaction-based
  salience is at or below `0.28` both now and 30 days earlier, and it has no
  direct interaction within 90 days. The fixed half-life is 60 days; weights
  are recency 0.70 and frequency/context/graph 0.10 each.
- Safety gates: corrected, already archived, pinned, protected, recently used,
  and actively graph-dependent items are not recommended.
- Recommendations are advisory only. An archive transition still requires an
  explicit call, and restore returns the item to the active candidate set.
- Implemented controlled cases: stable-low eligibility and reason codes;
  recent/pinned/protected/dependent safeguards; persistence against transient
  low salience; explicit archive then restore.
- Initial local validation: 8 of 8 deterministic scenarios pass in
  `results/lifecycle-stablelow-validation.json` (local, not committed).

All technical evaluation stages currently planned are complete. A structured
human review or an explicit scope statement remains a separate approval and
writing decision; it has not been represented as completed evidence.
