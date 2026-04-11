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

| Decision | Why it matters |
|---|---|
| One data point per patient per drug | A patient who posts about LDN ten times counts as one opinion, not ten — preventing prolific posters from drowning out the rest of the community |
| Results report problems, they don't hide them | Every analysis flags when sample sizes are too small, when data is sparse, or when results are unreliable — so the reader always knows how much to trust a finding |
| Usernames are scrambled before storage | Patients are stored as anonymous IDs. The database cannot be used to identify or trace individual Reddit users |
| AI only reads the direct reply, not the whole thread | Without this limit, the AI would tag drugs mentioned earlier in a conversation onto unrelated replies. Restricting context reduced this error from 55% of reports to 8% |
| Cheap model for bulk extraction, powerful model for analysis | Processing 17,000 posts with a top-tier AI would cost hundreds of dollars. We use a fast, inexpensive model to scan for drug mentions and a more capable one only where nuanced judgment is needed |
| Results exported as clean web pages | Findings are shared as readable web pages — no code visible, no software required to open them |
