# Diary bridge for the activity question

The bridge estimates how many activities the five-day window omits and how often a longer follow-up horizon
changes whether an attempt qualifies as cost-free. Use a small fixed list from the cognitive interviews and
have participants log ordinary activities. Schedule the target weeks before enrollment and follow attempts
through the reference horizon, including after each target week ends. In the export, retain partial diaries
and weeks with zero submissions. Participants provide their perceived link between an attempt and a later
cost. If a link is uncertain, record the follow-up as unresolved for that attempt.

## Export and run

Provide a JSON file with one fixed list of item IDs and one record per participant. The example describes
one scheduled week with one partial diary day. Start dates define seven consecutive local calendar days,
regardless of when a weekly questionnaire is completed.

```json
{
  "items": ["walk_15m", "phone_message"],
  "participants": [
    {
      "id": "demo-01",
      "severity": "moderate",
      "time_zone": "America/Los_Angeles",
      "week_starts": ["2026-01-05"],
      "days": [
        {
          "date": "2026-01-10",
          "complete": false,
          "attempts": [
            {
              "item": "walk_15m",
              "at": "2026-01-10T10:00:00-08:00",
              "followed_until": "2026-01-15T10:00:00-08:00",
              "cost_at": "2026-01-12T22:00:00-08:00"
            }
          ]
        }
      ]
    }
  ]
}
```

- `id` is a pseudonym unique to the participant. Use a baseline `severity` of `mild`, `moderate`, `severe`,
  `very_severe` or `unknown`. Give each participant their study time zone using an IANA name. Week start
  dates can have gaps, and each must be at least seven days from the next.
- Use `complete: true` when the participant has accounted for all pilot items for that local date. A
  complete day with `attempts: []` records no attempts. Use `complete: false` for a partial diary
  and omit the date if nobody logged it. Record each distinct attempt of each item, including activities
  followed by a cost and multiple attempts of the same item.
- `at` gives the attempt time with a UTC offset. `followed_until` indicates the end of continuous,
  interpretable follow-up since the attempt. Use `null` if follow-up is unavailable, and stop this field
  at the start of any gap even if the participant reports again later. `cost_at` gives the earliest onset
  of a known cost the participant connected to that attempt. Use `null` if they identified none. A known
  cost can be recorded even when follow-up is incomplete. Keep data with uncertain timing or attribution
  unresolved wherever that uncertainty affects classification.

Run from the repository root with Python 3.9 or newer and local time zone data. The command emits aggregate
JSON by severity and overall. Store exports and output containing small groups in the private study workspace.

```sh
python3 studies/baseline_check/next_version/diary_bridge.py /path/to/diary.json --reference-hours 120
```

## Read the results

| Comparison | Interpretation |
|---|---|
| Seven minus five days at 48 h | Added days at the same elapsed follow-up. The first five days approximate the current five-day window. The weekday counts show which logged attempts were outside it. |
| 72 h minus 48 h at seven days | Effect of waiting longer for each attempt, over the same activity dates. |
| Reference minus 72 h at seven days | Residual effect of a longer follow-up. Use the reference horizon set in the pilot protocol. 120 hours is the default research setting and can be changed for sensitivity analyses. |

An attempt has a known cost if the patient linked one with onset at or before the horizon. A cost-free
attempt requires observation through the horizon. A qualifying item has at least one cost-free attempt.
The bridge also counts items with both kinds of attempt, only cost-bearing attempts, and no attempt on a
fully recorded window. With incomplete days or unresolved attempts, a known qualifying attempt contributes
to the lower score bound. Any item that could still qualify contributes to the upper bound. A score is
exact when those bounds coincide, even if the finer distinction between mixed and only cost-free remains
unresolved.

Paired score differences are right minus left. Mean absolute differences and signed differences use weeks
with two exact scores and report their participant and week counts. The all-week bounds give a conservative
range for the mean difference, including weeks without exactly determined scores. The attempt-level table
uses the same recorded attempts at both horizons. Read `no_cost` → `cost` as a delayed cost that a shorter
horizon would miss, and `unknown` → `cost` as a known cost that was unresolved at the shorter horizon.
The reference also has an `unknown` column. Use `complete_days_by_weekday` alongside recorded and excluded
attempt counts, since gaps in activity recording can affect the apparent weekday pattern.

The output is descriptive and weights each week equally for score comparisons. When estimating sampling
uncertainty, resample participants with all of their weeks and attempts. The elapsed follow-up horizon is
held fixed for every attempt, so the comparisons isolate timing rules. A weekly questionnaire completed on
a specific day may capture additional follow-up for earlier attempts and introduce recall errors. Assess
that separately by comparing actual questionnaire answers with diary scores for the same dated windows.

## Synthetic verification

```sh
python3 -m unittest discover -s studies/baseline_check/next_version -p 'test_diary_bridge.py'
```

The fixture includes two weekend attempts that fall outside the five-day window. On the fully observed
week, the cost-free score rises by one when the weekend is included at 48 hours and falls by one at 72
hours. The tests also cover mixed attempts, partial and missed days, the effect of a clock change, and
invalid input. These are checks on scoring behavior using artificial data. Pilot estimates come from
prospective diaries.
