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
