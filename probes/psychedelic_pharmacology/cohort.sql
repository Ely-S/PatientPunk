SELECT DISTINCT
    tr.user_id AS author_hash,
    LOWER(t.canonical_name) AS target
FROM treatment_reports AS tr
JOIN treatment AS t ON t.id = tr.drug_id
WHERE tr.user_id IS NOT NULL
  AND LOWER(t.canonical_name) IN ('psilocybin', 'ketamine', 'lsd')
ORDER BY author_hash, target
