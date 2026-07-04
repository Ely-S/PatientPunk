# A1 Samples

This folder stores ID-only sample manifests for prompt engineering and review.
The files intentionally do not contain comment bodies.

Generated files:

- `seed_review_ids.jsonl`: small mixed set for human reading.
- `prompt_dev_ids.jsonl`: frozen prompt-engineering set.
- `gold_holdout_ids.jsonl`: held-out set for later evaluation.
- `adversarial_context_ids.jsonl`: context-heavy and ambiguous cases.

Regenerate with:

```powershell
python dev/analysis/a1_coding_research/scripts/select_samples.py --replace
```

Rendered text and model outputs should be written under
`dataset/covidlonghaulers_comments/derived/a1_coding_research/`, which is
ignored by git.

