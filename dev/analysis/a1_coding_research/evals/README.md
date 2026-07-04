# A1 Evals

This folder is for evaluation definitions and human-review rubrics. Model run
outputs are not stored here; they belong under the ignored derived dataset
folder.

Initial metrics tracked by `scripts/summarize_eval.py`:

- attempted rows
- successful structured rows
- failed rows
- codeable rows
- skipped rows
- claim count
- used-context count
- low-attribution-confidence count
- token and cost metadata when OpenRouter returns it

These are smoke metrics only. A real A1 gate still needs manual or adjudicated
labels for attribution leakage, missed claims, wrong experiencer, unsupported
evidence, and skip correctness.

