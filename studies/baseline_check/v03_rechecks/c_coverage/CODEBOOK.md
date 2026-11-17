# Codebook: would this weekly questionnaire capture the change?

Each post is a Reddit post by someone with Long COVID or ME/CFS. Judge whether a draft weekly questionnaire
(below) would register the main change in health the author describes, if they answered it honestly in a week
when that change was happening.

## The questionnaire (recall: the past 7 days)
- Q1 Crash days: on how many of the past 7 days were you in a crash? (0-7). A crash means feeling noticeably
  worse after doing something, whether physical, mental, emotional or sensory, even if it started one to three days later.
- Q2 Activities done at least once this week WITHOUT paying for it later (tick each; count 0-19):
  Everyday basics: sit up for most of the day; shower or bathe; make a simple meal; have a 30-minute conversation;
    read or watch something for 30 minutes and follow it; leave the house.
  Getting out and keeping up: walk 15 minutes outside; stand for 20 minutes; do household chores; go grocery
    shopping or run errands; see friends or family for an hour or more outside your home; work, study or volunteer
    for half a day (about 4 hours).
  Full days and beyond: do light exercise on purpose; walk 45 minutes or more; do 3+ hours of focused mental work;
    do a full day (about 8 hours) of work, study or caring without needing to lie down; go out for an evening or an
    outing of 3+ hours; keep up a full week of your usual responsibilities with no days lost; be as physically
    active as before you got sick.
- Q3 Overall symptoms on a typical day this week, 0 (none) to 10 (as bad as you can imagine).
- Q4 How close you felt to your pre-illness self this week, 0-100%.
- Q5 Compared with your last check: much worse / worse / a little worse / about the same / a little better / better / much better.
- (Q6 is free text. Do NOT count it when judging coverage.)

## For each post
1. describes_change: does the author describe a change over time in their OWN health? If false, leave the rest null.
2. change: the main change, as a short phrase in your own words.
3. captured:
   - "fully"  : a patient answering honestly would show this change on the named question(s) within a 7-day window,
                and the questions reflect what the change actually is (not just that "something got worse").
   - "partly" : the questions would register some movement, but miss the main content of the change, or only show it
                as a shift in one broad number (e.g. Q3 or Q5) that would not tell a reader what changed.
   - "not"    : the questionnaire would not register this change at all.
4. captured_by: list of questions that would register it, e.g. ["Q1","Q2:walk 15 min","Q3"].
5. missing: short phrase saying what the questionnaire would miss, or null.

Output: one JSON object per line, in the order the posts appear:
{"id": "...", "describes_change": true|false, "change": "...", "captured": "fully"|"partly"|"not"|null,
 "captured_by": [...], "missing": "..." | null}
