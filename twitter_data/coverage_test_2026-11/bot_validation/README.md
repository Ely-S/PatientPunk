# Hand labels for the bots section of the news-cycle post

`labels.csv`: 220 X posts, read and labelled by hand on 2026-11-20 (Claude, reviewed in session).
Sample: seed 11, 30 vendor, 30 flood, 15 coordinated, 30 headline relay, 15 other repeat, 40 organic
(from `twitter_data_news_blog/analysis/dedupe.roles` at Jaccard 0.6), plus 60 more organic (seed 12).
`sampled_as` is the role when sampled; the analysis re-joins current roles.

Labels: M = marketing or sales; A = automated or repetitive campaigning (same text pasted under many
threads, auto-posting accounts, hashtag stuffing); N = news, paper or press-release share; P = a personal
post or opinion. Contains post ids only; the text stays in tweets.db.
