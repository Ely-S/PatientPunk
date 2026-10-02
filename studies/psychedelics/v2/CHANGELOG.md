# v2 study changelog

Revision history that used to sit in the notebooks' reader-facing prose. The notebooks
state the current method only.

## Earlier drafts of notebook 3

- **`energy_pem` composite retired.** A single regular expression matched `pem`, `fatigue`,
  `energy`, `tired`, `exhaust`, `crash`, `exertion`, `stamina` and `cfs`, and the result was
  reported as post-exertional malaise. It is split into `pem_explicit`, `exertion_intolerance`,
  `fatigue_general` and `low_energy`, and the fatigue deficit is no longer described as a PEM
  finding.
- **First-match symptom classification replaced by multilabel membership.** The old rule
  returned on the first matching pattern, so pattern order decided which class a record landed
  in, and fatigue-bearing targets were pulled out of the energy classes.
- **Omnibus comparison replaced by one-factor contrasts.** Each drug-symptom cell used to be
  compared against the whole rest of the corpus, which moved drug, symptom class, indication,
  route, access pattern and reporter mix at once.
- **Adverse-event × `worsened` scan removed.** It screened drug × adverse-event category against
  the `worsened` direction and reported nine "FDR survivors" as its leading results. Those
  comparisons are close to tautological, because the AE record and the worsened direction are
  usually extracted from the same passage. The leading row rested on two reporter accounts.
- **Dose–outcome join narrowed to the claim.** Doses were joined to outcomes on reporter and
  drug, which copied a reporter's whole outcome summary onto every dose bin they had mentioned.
- **Tiering rules replaced.** A two-sided binomial p-value against the pooled rate promoted
  below-baseline cells to "Strong reporting signal" with no sign attached; an
  `n ≥ 15 or p < 0.10` rule promoted unseparated cells to "Moderate reporting signal"; a
  "reporting NNT analog" column read as a number needed to treat and blanked for every
  below-baseline cell; and a later version compared a cell's marginal interval with a corpus
  rate treated as a known constant. Tiers now come from the contrast's own bootstrap
  distribution.
- **Unsourced label-bias claim withdrawn.** A limitation stated that positive labels are
  over-called by 10–20%. It had no source in the repository.

## Earlier drafts of notebook 1

- The actual-use filter was applied a second time and described as a restriction. It removes
  nothing; `P.actual_use()` asserts the identity instead.

## Phase 1 corrections (v3 handoff)

- Blog post leads with the mutually exclusive outcome profiles and the general-fatigue
  finding. The model-graded 7–10 intensity count (282 accounts) moved lower and is labelled
  as a secondary, model-derived measure.
- The blog's "positive labels may be over-called" limitation was removed, matching the
  withdrawal above.
- Printed outputs and display labels say "reporter accounts" instead of "patients". The
  loader's `patient` column is unchanged.
- Repeated setting and limitation caveats in notebook 2 and notebook 3 were reduced to
  pointers. The full limitations remain in notebook 1 §10 and notebook 3 §11.
- `docs/psychedelic_probe_run_report.md` §6d now separates the units that recovered after the
  timeout fix from the 14 units that are still failed.
