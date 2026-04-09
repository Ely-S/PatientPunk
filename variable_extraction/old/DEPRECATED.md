# DEPRECATED -- Reference Only

> **Nothing in the codebase imports or calls these files.**
> **Do not add new code here. Do not modify these files.**
> They exist solely as historical reference. If you are reviewing
> this repo, skip this directory entirely.

These are the original flat scripts from before the `patientpunk/` library was
introduced. All active logic has been moved to `scripts/`. These copies exist
only as a reference in case the canonical versions in `scripts/` need to be
compared against the originals.

---

## Where the active code lives

| old/ script (deprecated)      | Active version              | patientpunk/ wrapper                          |
|--------------------------------|-----------------------------|-----------------------------------------------|
| `extract_biomedical.py`        | `scripts/extract_biomedical.py`        | `patientpunk.extractors.BiomedicalExtractor`  |
| `llm_extract.py`               | `scripts/llm_extract.py`               | `patientpunk.extractors.LLMExtractor`         |
| `discover_fields.py`           | `scripts/discover_fields.py`           | `patientpunk.extractors.FieldDiscoveryExtractor` |
| `records_to_csv.py`            | `scripts/records_to_csv.py`            | `patientpunk.exporters.CSVExporter`           |
| `make_codebook.py`             | `scripts/make_codebook.py`             | `patientpunk.exporters.CodebookGenerator`     |
| `extract_demographics_llm.py`  | `scripts/extract_demographics_llm.py`  | `patientpunk.extractors.DemographicsExtractor`|
| `code_demographics_llm.py`     | `scripts/code_demographics_llm.py`     | `patientpunk.extractors.DemographicCoder`     |
| `run_pipeline.py`              | `main.py run`                          | `patientpunk.Pipeline`                        |
