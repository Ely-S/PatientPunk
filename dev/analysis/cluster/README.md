# Comment Clustering

`dev/analysis/cluster/` turns A4 evidence-reporting output into exploratory
comment clusters.

Input is an A4 report directory, or its `evidence_mart.sqlite`. The cluster code:

1. reads A4 claim rows from the `claims` table,
2. collapses claims to one document per `comment_id`,
3. joins the raw comment body from A0 `comments.sqlite` when available,
4. builds TF-IDF features from claim types, normalized labels, claim text,
   evidence quotes, and optionally raw comment body,
5. clusters comments with sklearn agglomerative clustering, and
6. writes assignments, summaries, similarities, top terms, examples, and a
   readiness report.

The output is useful for exploring possible themes after A2/A3/A4, but it is
not a replacement for the qualitative coding stages. The readiness report marks
tiny runs as `meaningful_clustering: false` so smoke tests are not mistaken for
interpretable findings.

## Helper API

```python
from dev.analysis.helpers import cluster_comments

result = cluster_comments(
    a4_report="dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>",
)

print(result["output_dir"])
print(result["meaningful_clustering"])
```

Read assignments:

```python
from dev.analysis.helpers import load_comment_cluster_assignments

rows = load_comment_cluster_assignments(result["output_dir"])
```

## CLI

```powershell
python dev/analysis/cluster/scripts/build_clusters.py `
  --a4-report dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>
```

Useful options:

- `--output-dir`: choose where cluster artifacts are written.
- `--n-clusters`: force a fixed number of clusters.
- `--distance-threshold`: use threshold clustering when `--n-clusters` is not set.
- `--no-comment-body`: cluster from A4 claim fields only.
- `--write-feature-matrix`: write a sparse-style TF-IDF CSV for inspection.

## Outputs

- `comment_cluster_assignments.csv`: one row per clustered comment.
- `cluster_summary.csv`: cluster sizes, claim counts, top claim types, top labels.
- `cluster_examples.csv`: representative claim/quote examples by assigned comment.
- `cosine_similarity.csv`: pairwise comment similarity.
- `top_tfidf_terms.csv`: strongest terms per comment.
- `cluster_terms.csv`: strongest terms per cluster.
- `cluster_manifest.json`: input paths and configuration.
- `cluster_readiness_report.json`: row counts, sklearn mode, warnings, and
  whether the run is large enough to interpret.
