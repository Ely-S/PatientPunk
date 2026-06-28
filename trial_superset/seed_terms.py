"""Single source of truth for the broadened universe.

CLUSTER: the 5 mechanistically-adjacent conditions. For each:
  - `filter` : the condition string passed to HER find_condition_ncts (her substring
               match, both directions, against the trial's mesh+conditions terms).
  - `scope`  : a BROAD CT.gov `query.cond` superset for the download (must be broader
               than `filter`, since her substring filter can match general terms — see
               docs/test_universe_status.md and the Long-COVID "covid" quirk).

CANDIDATE_DRUGS: the candidate-drug seed. Mirrors TrialScout's DRUGS but ADDS IVIG,
which is missing there (a locked candidate drug). Used for drug-anchored augmentation
and M3 papers-as-labels.
"""

from __future__ import annotations

# condition slug -> {filter conditions (hers; list, ANY-match), broad download scope}.
# `filter` is a LIST passed to her find_condition_ncts. The download `scope` already
# limits the pool, so multi-string filters can't pull in unrelated trials (e.g. the
# me_cfs "Chronic Fatigue Syndrome" entry only matches within the CFS/ME scope pool).
CLUSTER: dict[str, dict] = {
    "long_covid": {
        "filter": ["Long Covid"],
        # "COVID" alone MISSES trials tagged "Post-Acute Sequelae of SARS-CoV-2" / "PASC" /
        # "Post-COVID-19 Condition" (no "COVID" substring, and CT.gov doesn't auto-expand).
        # Broadened scope recovers +4 results:with and +33 results:without genuine LC trials
        # (verified 2026-06-27). The CLASSIFY classifier still narrows to genuine long-COVID.
        "scope": ("COVID OR SARS-CoV-2 OR PASC OR Post-Acute Sequelae of SARS-CoV-2 OR "
                  "Post-COVID-19 Condition OR Chronic COVID OR Long-haul COVID"),
    },
    "me_cfs": {
        # "Myalgic Encephalomyelitis" alone misses CFS-tagged trials -> broaden the filter.
        "filter": ["Myalgic Encephalomyelitis", "Chronic Fatigue Syndrome"],
        "scope": "Myalgic Encephalomyelitis OR Chronic Fatigue Syndrome",
    },
    "fibromyalgia": {
        "filter": ["Fibromyalgia"],
        "scope": "Fibromyalgia",
    },
    "dysautonomia": {
        "filter": ["Postural Orthostatic Tachycardia Syndrome"],
        "scope": "Dysautonomia OR Orthostatic Intolerance OR POTS OR Postural Tachycardia",
    },
    "chronic_lyme": {
        "filter": ["Post-Treatment Lyme Disease Syndrome"],
        "scope": "Lyme",
    },
}

# IMPROVED-MODE condition classifier (deviates from her substring matcher - see
# docs/condition_filter_audit.md). A trial is in-condition if ANY mesh+conditions term
# CONTAINS one of these tokens (one-directional substring). This recovers the under-matched
# wins (dysautonomia orthostatic/autonomic, long-COVID post-acute) and drops the over-matched
# noise (acute-COVID, generic "fatigue"). Faithful mode (run_study/broaden) is unchanged.
CLASSIFY: dict[str, list[str]] = {
    "long_covid": ["long covid", "long-covid", "post-covid", "post covid", "postcovid",
                   "pasc", "post-acute covid", "post-acute sequelae"],
    "me_cfs": ["myalgic", "chronic fatigue", "fatigue syndrome, chronic", "me/cfs",
               "post-viral fatigue", "post viral fatigue", "post-exertional"],
    "fibromyalgia": ["fibromyalgia", "fibro"],
    "dysautonomia": ["dysautonomia", "orthostatic", "postural tachycardia", "pots", "autonomic"],
    "chronic_lyme": ["lyme", "borrelia", "neuroborreliosis"],
}

# Candidate drugs (canonical -> aliases). IVIG added vs TrialScout's DRUGS dict.
CANDIDATE_DRUGS: dict[str, list[str]] = {
    "naltrexone_ldn": ["ldn", "low-dose naltrexone", "low dose naltrexone", "naltrexone"],
    "pyridostigmine": ["pyridostigmine", "mestinon"],
    "tirzepatide": ["tirzepatide", "mounjaro", "zepbound"],
    "ivig": ["ivig", "immunoglobulin", "intravenous immunoglobulin",
             "privigen", "gamunex", "octagam", "gammagard"],
}
