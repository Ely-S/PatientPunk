"""Prompt for demographic and condition extraction from user posts."""

DEMOGRAPHICS_PROMPT = """\
Given these Reddit posts by a single user, extract ONLY explicitly stated information.
Return a JSON object with these fields (use null if not stated):
- age_bucket: age range, one of "18-24", "25-34", "35-44", "45-54", "55-64", "65+"
- sex: "M", "F", or "NB"
- location: country or US state
- conditions: list of objects {condition_name: str, condition_type: "illness" or "symptom"}

Only include what the user says about THEMSELVES. Do not infer.

Posts:
"""
