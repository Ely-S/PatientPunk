# Deduplication Sample Audit

**Generated:** 2026-05-07 16:42 UTC
**DB:** `data/historical_validation_2020-07_to_2022-12.db`
**Sample seed:** 42  
**Per-drug sample size:** 6  

This file samples multi-report (user, drug) pairs from the
analysis DB and shows each user's full set of reports for that
drug, with the report retained by the dedup rule clearly marked
(`** RETAINED **` row). The audit is for reviewers to spot-check
that the rule "most recent post wins (by full UTC timestamp);
signal_strength breaks ties on the same UTC timestamp" picked
sensibly — i.e., that we're not systematically picking against
the user's settled view. Exact-timestamp ties are rare, so the
signal-strength tiebreaker fires only occasionally; most picks
are simply the most-recent post.

If you find a case where the retained row looks like a poor
representation of the user's overall opinion, that's a
methodology finding worth raising in review.

---

## famotidine (Glynne et al. 2021)

Multi-report users in this drug's window: **113** (of which **32** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `44fe6112c9718d38…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-02-16 08:24 | negative | strong | `gnmln3k` |
|  | 2020-12-03 09:04 | positive | weak | `gegyp6l` |

### user `1b7a4764bb710a28…` (3 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-03-25 08:08 | negative | strong | `gs5cg6y` |
|  | 2021-03-12 13:57 | positive | strong | `gqouff2` |
|  | 2021-03-06 19:10 | positive | weak | `gpzzk9m` |

### user `86056fd047ec0b0e…` (5 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-05-24 12:22 | negative | strong | `gz9k7jh` |
|  | 2021-05-18 22:28 | positive | weak | `gymk1s1` |
|  | 2021-04-17 03:05 | negative | moderate | `gusuip0` |
|  | 2021-03-15 20:48 | positive | weak | `m5ui29` |
|  | 2021-03-10 01:55 | negative | strong | `gqef5pe` |

### user `819b25bd7c99f14e…` (16 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-05-29 11:57 | positive | weak | `gzv3cig` |
|  | 2021-05-26 22:48 | negative | weak | `nltmom` |
|  | 2021-05-19 19:11 | positive | moderate | `gyqd7ll` |
|  | 2021-05-12 21:04 | positive | weak | `gxwgvq7` |
|  | 2021-04-26 16:34 | positive | weak | `gvy2yvu` |
|  | 2021-04-15 15:48 | negative | weak | `gum7dl1` |
|  | 2021-03-25 20:05 | positive | moderate | `gs7nbhs` |
|  | 2021-03-12 23:18 | positive | weak | `gqqtlea` |
|  | 2021-03-12 22:01 | positive | strong | `gqqksc7` |
|  | 2021-03-09 23:21 | positive | strong | `gqdxo0z` |
|  | 2021-03-05 16:56 | positive | weak | `gpshjlk` |
|  | 2021-02-12 20:13 | negative | moderate | `gn3hbd5` |
|  | 2021-02-07 17:09 | positive | weak | `gmh29jy` |
|  | 2021-02-03 19:36 | positive | weak | `glwda0s` |
|  | 2021-01-22 21:22 | positive | weak | `gk8pf1x` |
|  | 2021-01-21 03:47 | positive | moderate | `gk0x3ng` |

### user `74f9167e051b2d26…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-06-03 12:55 | positive | weak | `h0fmls6` |
|  | 2021-06-03 12:04 | positive | weak | `h0fh4my` |

### user `3ab79ae7167b5b5e…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-04-22 21:15 | mixed | moderate | `gvhq95w` |
|  | 2021-04-03 15:48 | negative | moderate | `gt96gu7` |

---

## loratadine (Glynne et al. 2021)

Multi-report users in this drug's window: **39** (of which **9** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `182874d058f52d2a…` (3 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-04-06 20:14 | positive | strong | `gtlyg1k` |
|  | 2021-03-12 21:32 | positive | strong | `m3rpj3` |
|  | 2021-03-11 00:00 | negative | moderate | `m2ctu5` |

### user `f3c1a4f63916605d…` (6 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-04-20 18:25 | positive | weak | `gv8caq7` |
|  | 2021-04-12 19:15 | mixed | moderate | `guad8bx` |
|  | 2021-03-14 20:54 | positive | moderate | `gqxxoz6` |
|  | 2021-02-23 18:36 | positive | moderate | `goho54c` |
|  | 2021-02-19 17:49 | positive | weak | `go1278e` |
|  | 2021-01-27 22:05 | positive | weak | `gl09d55` |

### user `87b65a2f4371463c…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2020-12-24 16:52 | positive | moderate | `ggwtglb` |
|  | 2020-12-24 15:20 | mixed | strong | `ggwjynp` |

### user `445d14d95d5658d3…` (3 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-03-15 15:33 | positive | strong | `gr0sffb` |
|  | 2021-03-11 16:54 | negative | moderate | `gql9idk` |
|  | 2020-09-02 12:31 | negative | moderate | `g3plalk` |

### user `0ee2b443c5440128…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-04-05 02:15 | positive | moderate | `gtesyqv` |
|  | 2021-04-04 16:47 | positive | strong | `gtd1kix` |

### user `0d68198086fcf17c…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-05-12 15:48 | positive | strong | `gxv6bky` |
|  | 2021-05-11 17:46 | positive | strong | `na2wc3` |

---

## prednisone (Utrero-Rico et al. 2021)

Multi-report users in this drug's window: **131** (of which **67** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `32be2a69053b6f29…` (5 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-07-18 14:11 | neutral | weak | `h5mrj7t` |
|  | 2021-07-17 20:39 | negative | weak | `h5jxwe8` |
|  | 2021-07-14 18:55 | positive | weak | `h56p1tv` |
|  | 2021-07-05 21:32 | neutral | weak | `h464lmh` |
|  | 2021-07-05 20:52 | neutral | weak | `h45zw8r` |

### user `82b2fa6b7a735dfa…` (5 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-02-13 23:53 | negative | strong | `gnbjhx6` |
|  | 2021-02-09 21:25 | mixed | strong | `gmqsvp7` |
|  | 2021-02-08 15:58 | negative | moderate | `gmlbs1h` |
|  | 2021-02-04 21:32 | negative | weak | `gm1euz6` |
|  | 2021-02-04 19:48 | positive | weak | `gm0zex7` |

### user `8fe91f3551c26112…` (3 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-09-24 09:06 | mixed | strong | `he2jj7z` |
|  | 2021-09-24 08:55 | positive | weak | `he2itfk` |
|  | 2021-08-22 23:12 | mixed | strong | `h9yu5ck` |

### user `f521fb42e6873362…` (5 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-04-08 22:33 | positive | strong | `gtv66nz` |
|  | 2021-03-21 22:09 | positive | weak | `grqvznm` |
|  | 2021-03-14 04:06 | neutral | weak | `gqv9lbd` |
|  | 2021-02-13 22:31 | positive | strong | `gnb1qaa` |
|  | 2021-02-02 05:01 | positive | weak | `glp3b3y` |

### user `0e3d5772131108e2…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-01-29 04:32 | positive | weak | `gl70kfa` |
|  | 2021-01-19 23:11 | positive | strong | `gjvux34` |

### user `60b85be069da26ba…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-01-19 22:00 | mixed | strong | `gjvm439` |
|  | 2020-10-08 21:21 | negative | strong | `g85i4yc` |

---

## naltrexone (O'Kelly et al. 2022)

Multi-report users in this drug's window: **72** (of which **36** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `e8c1f5b813faa786…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-10-26 15:54 | neutral | weak | `hi4m35o` |
|  | 2021-10-25 17:38 | positive | weak | `qfm0ut` |

### user `a8b0e8e01067ad3b…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-06-16 09:05 | positive | weak | `ick8b3g` |
|  | 2022-06-02 11:25 | neutral | weak | `iaweipn` |

### user `5e85f74468b46e64…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-06-29 18:15 | neutral | weak | `ie7s8fu` |
|  | 2022-06-24 16:28 | positive | weak | `idkrpuz` |

### user `b49684f724999bac…` (7 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-05-01 06:51 | positive | strong | `i6voeb5` |
|  | 2021-08-27 04:06 | positive | strong | `haikq3k` |
|  | 2021-07-15 20:11 | positive | strong | `h5bdgzy` |
|  | 2021-07-15 20:01 | positive | moderate | `h5bc306` |
|  | 2021-07-15 03:10 | positive | weak | `h58du9y` |
|  | 2021-07-15 00:12 | positive | strong | `okh71q` |
|  | 2021-05-18 01:39 | mixed | strong | `gyiod8e` |

### user `75634836e13ab70e…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-03-30 21:22 | positive | weak | `i2rmi7c` |
|  | 2022-01-15 00:33 | positive | strong | `hspaq0p` |

### user `0c9bdfdf08e3b876…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-01-29 17:47 | positive | strong | `huqsrmm` |
|  | 2022-01-09 06:48 | positive | moderate | `hrvvfp2` |

---

## paxlovid (Geng et al. 2024 (STOP-PASC))

Multi-report users in this drug's window: **84** (of which **36** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `362b2b4516b34819…` (4 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-12-06 19:49 | positive | moderate | `iz67gfo` |
|  | 2022-10-03 23:27 | positive | moderate | `iqy6w6m` |
|  | 2022-09-19 15:43 | mixed | moderate | `ip2rorm` |
|  | 2022-09-13 21:58 | positive | strong | `xdjxok` |

### user `9ab8f15ec70eb262…` (11 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-12-07 19:31 | positive | strong | `izavgnz` |
|  | 2022-12-07 19:25 | mixed | moderate | `izaum2a` |
|  | 2022-11-20 19:45 | negative | strong | `ix4vnkm` |
|  | 2022-09-01 02:47 | positive | weak | `imm03f8` |
|  | 2022-08-14 19:01 | mixed | moderate | `ikacgyw` |
|  | 2022-07-22 02:17 | positive | strong | `ih4xjue` |
|  | 2022-07-20 01:29 | positive | moderate | `iguyko1` |
|  | 2022-06-17 01:18 | positive | strong | `icnjujy` |
|  | 2022-06-10 20:21 | positive | strong | `ibwb0nu` |
|  | 2022-06-09 01:44 | positive | strong | `ibokegp` |
|  | 2022-05-15 02:02 | positive | strong | `i8ncc12` |

### user `5f0a28242fcf5b72…` (8 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-04-02 05:28 | positive | strong | `i32sd2a` |
|  | 2022-04-02 01:30 | positive | strong | `i323o8p` |
|  | 2022-04-01 20:20 | mixed | strong | `i3106a3` |
|  | 2022-03-29 02:21 | negative | moderate | `i2il3t9` |
|  | 2022-03-28 17:33 | positive | strong | `i2gndrn` |
|  | 2022-03-28 07:58 | positive | strong | `i2ews1z` |
|  | 2022-02-03 00:12 | positive | moderate | `hvcmxut` |
|  | 2022-02-01 08:26 | positive | strong | `hv3ye0j` |

### user `4f9e504270ba34a9…` (3 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-04-24 21:18 | negative | weak | `i61sj1c` |
|  | 2022-04-23 05:25 | negative | strong | `i5ug8r1` |
|  | 2022-04-11 01:27 | positive | strong | `i48letq` |

### user `3595fdb1ba84923b…` (4 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-07-08 04:58 | positive | strong | `ifb1g33` |
|  | 2022-05-25 00:16 | positive | strong | `i9vh37s` |
|  | 2022-05-13 08:18 | positive | moderate | `i8fejag` |
|  | 2022-05-07 13:27 | positive | strong | `ukdad1` |

### user `4990134303312f93…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-12-24 16:59 | positive | moderate | `zudsnx` |
|  | 2022-12-16 01:38 | positive | strong | `zn2pcb` |

---

## colchicine (Bassi et al. 2025)

Multi-report users in this drug's window: **38** (of which **21** are mixed-signal — pos+nonpos).
Showing 6 sampled users below.

### user `8164b08d0e7bfb45…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-03-19 08:34 | negative | moderate | `i19di9z` |
|  | 2021-04-10 18:40 | positive | weak | `moaet5` |

### user `20a1b6afa247c28f…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-04-27 07:39 | positive | strong | `i6dhui3` |
|  | 2022-04-26 17:51 | negative | strong | `i6alofi` |

### user `1d50c94a73d919c4…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-06-14 20:53 | mixed | strong | `icdjcy4` |
|  | 2022-06-14 19:33 | positive | strong | `icd7sqa` |

### user `8bbe1b1e00da8141…` (5 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-07-15 23:00 | negative | strong | `igbqtuf` |
|  | 2022-03-17 11:02 | negative | strong | `tg7mi6` |
|  | 2022-01-15 05:30 | mixed | strong | `hsqbg4v` |
|  | 2022-01-15 01:02 | positive | strong | `hspek1x` |
|  | 2021-12-26 18:08 | positive | weak | `hq1rq1x` |

### user `28f5ce443a7ab788…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2021-12-07 20:19 | negative | strong | `hnmtcy7` |
|  | 2021-11-11 10:31 | negative | strong | `hk6raje` |

### user `b2670d3a5c74df76…` (2 reports)

| | post_date (UTC) | sentiment | signal | post_id |
|---|---|---|---|---|
| **RETAINED** | 2022-07-08 02:38 | negative | strong | `ifal2p1` |
|  | 2022-07-05 20:37 | negative | strong | `iezlv2d` |

---

## Reproducibility

Re-running `scripts/dedup_sample_audit.py --db <db> --out <out> --seed 42 --per-drug 6` against the same DB reproduces the same sampled rows, aside from the `Generated` timestamp at the top of this file. Total sampled (user, drug) pairs: **36**.