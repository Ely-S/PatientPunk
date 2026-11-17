# Codebook: what change matters most to the author

Each post is a first-person Reddit post by someone with Long COVID or ME/CFS describing a change in their own health.
For each post, decide the ONE change that matters most to the author, judged from the text (what they emphasise,
what they say bothers or pleases them most, what they ask about). Code it into exactly one category:

- global       : the author frames what matters as their overall state, not one symptom or activity:
                 feeling like themselves / normal / healthy again, being recovered or in remission, "my life back"
                 as a whole, or a percent-of-my-old-self rating.
- symptom      : one or more specific symptoms (includes brain fog and other thinking problems, mood, sleep, pain,
                 heart rate, smell/taste, fatigue as a feeling).
- activity     : something they can or cannot do, or how much of it: work, study, walking, exercise, self-care,
                 chores, social life, driving, caring, time upright.
- both         : a symptom and an activity are equally central and cannot be separated.
- crashes      : crashes / PEM / flares themselves: how often, how bad, how long, what sets them off.
- trajectory   : the direction or prognosis without specific content: "keeps getting worse", relapse after
                 remission, fear of never improving, "will this get better?".
- unclear      : cannot tell what matters most.

Also record:
- global_wording: true if ANYWHERE in the post the author describes their own state with words like "feel like
  myself", "normal", "back to my old self", "recovered", "healthy again", or "N% of my old self/normal". false otherwise.
- quote: a short phrase (at most 25 words) copied EXACTLY, character for character, from the post that best supports
  your category. Do not paraphrase, fix spelling, or join separate sentences.

Output: one JSON object per line, in the order the posts appear:
{"id": "<post id>", "category": "<one of the 7>", "global_wording": true|false, "quote": "<exact text>"}
