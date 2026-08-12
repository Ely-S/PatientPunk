# trial_superset has moved

**This directory is retired. Do not edit it — changes here will not reach anyone.**

All of this work now lives in one repository, so that a single checkout runs the pipeline and
carries its own documentation:

> **[Airwhale/naturalv2 @ `shaun/patientpunk-integration`](https://github.com/Airwhale/naturalv2/tree/shaun/patientpunk-integration)**

`main` on that fork is byte-identical to [nikitadhawan/naturalv2](https://github.com/nikitadhawan/naturalv2),
so the branch diff is exactly the set of our changes.

## Where things went

| was here | is now |
|---|---|
| `trial_superset/*.py`, `litlabels/`, `config/` | `patientpunk/analysis/` — how the study was built: trial selection, coverage measurement, papers-as-labels, audits |
| `trial_superset/docs/*.md` | `docs/patientpunk/` |
| `trial_superset/docs/bugs.md` | `docs/patientpunk/findings.md` — the bug registry, now the only copy |
| `dispersed/` (repo root) | `patientpunk/serving/` |
| the run scripts | `patientpunk/scripts/` |
| `trial_superset/data/` | **S3 only** — `s3://patientpunk/trial_superset/`. No data belongs in a git repository |

Start with `patientpunk/README.md` to run something, or `docs/patientpunk/pipeline_overview.md`
for what the method does and where it is weak.

## Why it moved

Two copies of the same documents drift. The bug registry had already diverged once — a defect count
and two statuses were stale in one copy and correct in the other — which is the failure this move
prevents.

This directory is left in place rather than deleted because the history is worth keeping and because
`data/` here is a local mirror of S3. Treat it as an archive.
