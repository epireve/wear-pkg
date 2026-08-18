# Wear-PKG

This repository implements a chronological, leakage-safe re-ranking workflow
for MIND impression candidates using a
historical interaction profile and inspectable salience features.

MIND has no issued queries. The implementation therefore calls its relevance
signal **profile relevance**, never query relevance. The same core exposes a
query-aware intent interface for KuaiSAR and a context-aware interface for
RLKWiC; neither is fabricated from MIND labels or future candidates.

## What the MIND experiment claims

For each MIND impression, the system uses only clicks observed in earlier,
timestamped impressions for that user. It compares:

- profile relevance only;
- recency only;
- frequency only;
- recency plus frequency;
- full MIND-compatible salience: recency, frequency, contextual reuse, and
  graph support;
- profile relevance plus full salience.

The clicked candidates are implicit engagement labels under MIND's logged
news policy, not ground-truth relevance, importance, or archival behaviour.
The initial MIND `history` column is intentionally not used for timestamped
wear because its individual click times are unavailable.

## Install

The core has no third-party runtime dependency.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Download and run MINDsmall

```bash
.venv/bin/python scripts/fetch_mind.py --dataset small --split train
.venv/bin/python scripts/fetch_mind.py --dataset small --split dev

.venv/bin/wear-pkg mind-run \
  --dataset-dir data/MINDsmall_train \
  --output results/mindsmall-train.json
```

The legacy Microsoft Blob URLs currently reject unauthenticated requests. The
fetcher still attempts the official endpoint, but it also accepts a researcher-
authorised archive or URL without embedding a third-party mirror in the project:

```bash
.venv/bin/python scripts/fetch_mind.py --dataset small --split train --archive /path/to/MINDsmall_train.zip
```

Tune choices on the training output only. Freeze the configuration before
using `MINDsmall_dev` for a final small-scale result. Run the same frozen
configuration against MINDlarge afterwards; MINDsmall and MINDlarge are one
dataset family, not independent replications.

Useful options:

```bash
.venv/bin/wear-pkg mind-run --help
```

The runner creates a local SQLite event index beside the dataset on first run.
It allows MINDlarge to be replayed by user and timestamp without loading all
behaviour rows into memory.

## Train-only configuration selection

The checked-in MINDsmall grid selects the best `nDCG@10` result using training
data only. It uses the provided MIND history for non-temporal signals, but
never for recency.

```bash
.venv/bin/wear-pkg mind-sweep \
  --dataset-dir data/MINDsmall_train \
  --config configs/mindsmall-train-sweep.json \
  --output results/mindsmall-train-sweep.json
```

Copy only the selected configuration into the frozen dev command. Do not use
dev output to select another configuration.

## KuaiSAR query-aware replay

KuaiSAR provides actual hashed query tokens, shown search candidates, click
labels, and prior multi-action recommendation history. The runner matches each
query with item-caption tokens, then uses only earlier recommendation and
search interactions for salience.

```bash
.venv/bin/wear-pkg kuaisar-run \
  --dataset-dir data/KuaiSAR-small \
  --partition train \
  --train-fraction 0.8 \
  --max-sessions 1000 \
  --output results/kuaisar-small-smoke.json
```

Use the earlier temporal partition for configuration selection, then freeze the
selected values for one later-partition run. The split boundary is calculated
from all search-session timestamps; history still contains only events strictly
earlier than each scored session.

```bash
.venv/bin/wear-pkg kuaisar-sweep \
  --dataset-dir data/KuaiSAR-small \
  --config configs/kuaisar-train-sweep.json \
  --output results/kuaisar-small-train-sweep.json
```

The initial run is intentionally bounded. Remove `--max-sessions` only after
the derived SQLite index and smoke result have been verified.

## Controlled lifecycle validation

The deterministic lifecycle suite exercises state transitions that neither
logged corpus represents directly. It verifies that pinning overrides ordinary
ordering, archiving removes an item from the candidate set, restoration makes
it eligible again, corrections resolve to the replacement item, and a removed
graph edge provides no graph contribution.

```bash
.venv/bin/wear-pkg lifecycle-run \
  --output results/lifecycle-validation.json
```

The output is an inspectable record of each transition and its assertion.

The same suite now includes a controlled `StableLow` archive recommendation
policy. It recommends an item for user review only when interaction-based
salience remains at or below a fixed threshold both now and 30 days earlier,
and the item has been inactive for 90 days. Pinned, protected, corrected,
recently used, or actively graph-dependent items are excluded. The policy
returns reason codes and never archives an item by itself; archive and restore
remain explicit lifecycle operations.

## RLKWiC context-and-graph validation

RLKWiC supplies timestamped context events, personal-KG triples, actual
context labels, and human-scored entity recommendations. The runner ranks only
multi-candidate recommendation slates and reconstructs each context's history
from KG events strictly earlier than the recommendation timestamp.

```bash
.venv/bin/wear-pkg rlkwic-sweep \
  --dataset-dir data/RLKWiC \
  --config configs/rlkwic-train-sweep.json \
  --output results/rlkwic-train-sweep.json
```

Freeze the train-selected configuration before one later-segment replay. The
entity labels are public DBpedia URIs, but their link to the personal KG is
lexical; the result should be read as a construct check, not a scale estimate.

## Uncertainty checks

Use paired user-cluster bootstrap intervals only on a frozen held-out run. The
full score is compared with the stage's pre-specified strongest baseline;
resampling users rather than individual episodes preserves within-user
dependence.

```bash
.venv/bin/wear-pkg mind-run \
  --dataset-dir data/MINDlarge_dev \
  --bootstrap-samples 1000 \
  --bootstrap-seed 20260818 \
  --output results/mindlarge-dev-bootstrap.json
```

The result records the point difference, 95% percentile interval, and the
share of bootstrap draws above zero for MRR, nDCG@5, and nDCG@10.

## Fixed signal-ablation diagnostics

The ablation files remove one salience signal at a time while preserving the
previously selected score mix, temporal partition, history rule, and bootstrap
seed. They are diagnostic comparisons against the frozen full configuration,
not another selection pass.

```bash
PYTHONPATH=src python3 -m wear_pkg.cli mind-sweep \
  --dataset-dir data/MINDlarge_dev \
  --config configs/mindlarge-frozen-ablations.json \
  --output results/mindlarge-dev-ablations.json

PYTHONPATH=src python3 -m wear_pkg.cli kuaisar-sweep \
  --dataset-dir data/KuaiSAR-small \
  --config configs/kuaisar-frozen-ablations.json \
  --output results/kuaisar-small-dev-ablations.json
```

Each output includes paired user-cluster uncertainty for every removal versus
the declared full configuration.

## Dataset-agnostic intent contract

```text
RetrievalEpisode
  intent = QueryIntent | ProfileIntent | ContextIntent
  candidates = exposed or otherwise defined candidate items
  history = only events before the episode timestamp
```

- **MIND:** `ProfileIntent`; title, abstract and linked entities provide a
  profile-relevance baseline.
- **KuaiSAR:** `QueryIntent`; actual query tokens are matched with item
  captions, then historical multi-action salience re-ranks the exposed slate.
- **RLKWiC:** `ContextIntent`; user-defined work context is matched with
  resources/entities, then real personal-KG activity supplies salience.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

The tests use a tiny synthetic MIND corpus. They verify that future clicks are
not visible to earlier impressions, the first impression has no usable observed
history, and actual query relevance is independent from profile relevance.
