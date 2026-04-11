# PatientPunk — Architecture Diagram

```mermaid
flowchart TD
    subgraph Sources["Data Sources"]
        AS["Arctic Shift API\nHistorical Reddit NDJSON"]
    end

    subgraph Ingest["Ingestion"]
        TR["transform_arctic_shift.py\nBulk NDJSON → JSON"]
        LDB["load_db.py\nETL → SQLite"]
    end

    subgraph DB["patientpunk.db (SQLite)"]
        direction LR
        P["posts\ntitle · flair · parent_id"]
        U["users\nSHA-256 hashed IDs"]
    end

    subgraph Polina["Drug Sentiment Pipeline (src/)"]
        E["extract_mentions\nLLM batch extraction"]
        C["canonicalize\nSynonym normalization"]
        CL["classify_sentiment\npositive · negative · mixed"]
        TR2["treatment_reports\n+ treatment table"]
    end

    subgraph Shaun["Variable Extraction Pipeline (variable_extraction/)"]
        VE["LLM extractors\ndemographics · conditions"]
        UP["user_profiles\nage · sex · location"]
        CO["conditions\nper-user diagnoses"]
    end

    subgraph Analytics["Analytics Engine (app/analysis/)"]
        ST["stats.py\n11 statistical tests\nbinomial · Mann-Whitney · logit\nCox PH · Kruskal-Wallis · ..."]
        MD["models.py\nPydantic v2 results\n+ structured warnings"]
    end

    subgraph Output["Output"]
        SK["Research Assistant Skill\nClaude generates notebooks"]
        NB["Jupyter Notebooks\nnotebooks/*.ipynb"]
        HTML["Static HTML Dashboards\nnbconvert --no-input"]
    end

    AS --> TR
    TR --> LDB
    LDB --> P & U

    P & U --> E
    E --> C --> CL --> TR2

    P & U --> VE
    VE --> UP & CO

    TR2 & UP & CO --> ST
    ST --> MD
    MD --> SK
    SK --> NB
    NB --> HTML
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| User-level aggregation | One data point per user per drug satisfies statistical independence |
| Warning-oriented results | `AnalysisWarning(code, severity, message)` instead of exceptions — small samples are reported, not crashed |
| SHA-256 user hashing | Privacy-preserving join key across tables |
| `--max-upstream-depth 1` | Limits context bleed from 55% → 8% in drug extraction |
| OpenRouter by default | Single key switches between Haiku (fast/cheap) and Sonnet (strong) |
| `nbconvert --no-input` | Voila doesn't work reliably on Windows; static HTML is equivalent |
