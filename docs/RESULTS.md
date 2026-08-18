# Results Summary

This summary records frozen held-out runs only. Raw source data and generated
result JSON remain local; the commands, frozen configurations, and exact
aggregate values are recorded here for repeatability.

## Held-out ranking results

| Stage | Full nDCG@10 | Baseline | Baseline nDCG@10 | Difference |
|---|---:|---|---:|---:|
| MINDlarge dev | 0.3903 | Frequency | 0.3860 | +0.0043 |
| KuaiSAR later segment | 0.4966 | Frequency | 0.4898 | +0.0068 |
| RLKWiC later segment | 0.9701 | Direct event matching | 0.9656 | +0.0045 |

### Frozen configurations

- **MINDlarge:** profile weight 0.65; 72-hour half-life; salience weights
  recency 0.15, frequency 0.50, context 0.15, graph 0.20; supplied history is
  used only for non-temporal signals.
- **KuaiSAR:** query weight 0.50; 24-hour half-life; equal weights across
  recency, frequency, action, context, and graph; 80/20 timestamp split.
- **RLKWiC:** context/event weight 0.80; 24-hour half-life; equal recency,
  frequency, context, and graph weights; 80/20 timestamp split.

## Paired user-cluster bootstrap

Each interval resamples users with replacement 1,000 times (seed `20260818`).
The comparison is full score minus the pre-specified baseline.

| Stage | User clusters | Slates / episodes | nDCG@10 difference | 95% interval | Positive draws |
|---|---:|---:|---:|---:|---:|
| MINDlarge | 251,721 | 369,454 | +0.0043 | [+0.0038, +0.0048] | 100.0% |
| KuaiSAR | 6,787 | 33,433 | +0.0068 | [+0.0047, +0.0092] | 100.0% |
| RLKWiC | 6 | 55 | +0.0045 | [-0.0217, +0.0439] | 54.7% |

MINDlarge and KuaiSAR show stable positive improvements under this check.
RLKWiC's point estimate is positive, but its interval crosses zero and must be
treated as inconclusive.

## Fixed signal-ablation diagnostics

These follow-on comparisons retain the existing held-out partitions and all
previously fixed values. They remove one salience signal, renormalise only the
remaining salience weights, and compare that removal with the frozen full
configuration using the same 1,000 user-cluster resamples. They are diagnostic
evidence, not another configuration-selection pass.

| Dataset | Removal | Full-minus-removal nDCG@10 | 95% interval | Interpretation |
|---|---|---:|---:|---|
| MINDlarge | Frequency | +0.0153 | [+0.0148, +0.0159] | Frequency materially supports the full score. |
| MINDlarge | Context | +0.0020 | [+0.0018, +0.0022] | Context materially supports the full score. |
| MINDlarge | Graph | +0.0002 | [-0.0001, +0.0004] | Inconclusive at this configuration. |
| MINDlarge | Recency | -0.0006 | [-0.0008, -0.0005] | Removal slightly improves the fixed score. |
| KuaiSAR | Graph | +0.0050 | [+0.0042, +0.0058] | Graph materially supports the full score. |
| KuaiSAR | Recency | +0.0023 | [+0.0017, +0.0030] | Recency materially supports the full score. |
| KuaiSAR | Context | -0.0007 | [-0.0011, -0.0002] | Removal slightly improves the fixed score. |
| KuaiSAR | Action | -0.0028 | [-0.0035, -0.0022] | Removal improves the fixed score. |
| KuaiSAR | Frequency | -0.0029 | [-0.0036, -0.0022] | Removal improves the fixed score. |

The signal mix is therefore dataset-dependent. The original frozen full score
remains the result of its train-only selection, but the diagnostic evidence
does not support a claim that every signal family is beneficial at equal or
fixed weight. In particular, the MINDlarge result relies strongly on frequency
and context, while KuaiSAR relies strongly on graph and recency.

## Controlled StableLow archive policy

The controlled lifecycle suite now includes an advisory archive policy. It
recommends an item for user review only when its bounded interaction salience
is at or below 0.28 both at the decision point and 30 days earlier, with no
direct interaction in the prior 90 days. It uses a 60-day half-life and weights
recency at 0.70, with frequency, context, and graph at 0.10 each.

Eight deterministic scenarios pass: pin/unpin, archive/restore, correction
redirect, graph disconnection, StableLow eligibility with reason codes, safety
gates for recent/pinned/protected/actively dependent items, persistence against
transient low salience, and user-controlled archive then restore. The policy
only returns an explanation and eligibility decision; it never archives an
item automatically.

This is controlled technical evidence of policy behaviour and reversibility.
It does not measure whether people would agree with a recommendation, find its
explanation useful, perceive it as safe, or accept an archive recommendation.

## Scope boundary

No structured human review is included. The results support technical
feasibility, reproducible ranking behaviour, sensitivity to signal removal,
and controlled lifecycle-policy behaviour. They do not support claims about
human understanding, trust, perceived safety, explanation usefulness, or
archive acceptance.

## Important boundaries

- MIND measures profile relevance plus salience on logged news impressions; it
  has no issued query and its clicks are implicit engagement labels.
- KuaiSAR has actual query tokens and exposed search slates, but its tokens are
  anonymized, its observation period is short, and its labels are implicit.
- KuaiSAR nDCG uses the graded `click_cnt` values. The earlier binary-only
  denominator was corrected before the final selection and held-out replay;
  MRR was unaffected.
- RLKWiC uses human-scored recommendation entities and real context/KG events,
  but only six participants contributed eligible held-out slates and entity-to-
  KG matching is lexical.
