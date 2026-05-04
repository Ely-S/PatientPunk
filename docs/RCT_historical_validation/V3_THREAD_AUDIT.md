# V3 Thread Reconstruction Audit

**Run at:** 2026-05-04 17:53 UTC  
**DB:** `data\historical_validation\historical_validation_2020-07_to_2022-12.db`  
**Sample seed:** 42  
**Sample size:** 50

---

## 1. Posts vs comments

| Metric | Value |
|---|---|
| Total rows in `posts` | 731,526 |
| Submissions (`parent_id IS NULL`) | 47,442 (6.5%) |
| Comments (`parent_id IS NOT NULL`) | 684,084 (93.5%) |

## 2. Orphan parents

Comments whose `parent_id` is set but doesn't match any `post_id` in the DB.

**Orphans found: 0**  
All `parent_id` values resolve to an existing post. PASS.

## 3. Cycle detection

Full DFS over the parent edge graph (`731,526` nodes).

**Cycles found: 0**  
Parent graph is a forest (no cycles). PASS.

## 4. Sampled reply chains

Random sample of 50 comments (seed `42`); each walked to its root.

| Property | Result |
|---|---|
| Chains reaching a root submission | **50 / 50** |
| Chains hitting a cycle | 0 |
| Timestamp pairs checked (parent vs child) | 113 |
| Timestamp violations (child older than parent) | 0 |

**Chain depth histogram (sample):**

| Depth (hops) | Count |
|---|---|
| 2 | 22 |
| 3 | 11 |
| 4 | 8 |
| 5 | 3 |
| 6 | 5 |
| 9 | 1 |

All sampled chains complete, cycle-free, and timestamp-monotonic. PASS.

## Reproducibility

Re-running with the same `--db`, `--seed`, and same DB contents produces an identical report. The sample is deterministic given the seed.