## Do not supply defaults for fields that require stated evidence

- functional_status_tier: Extract a tier only when the author explicitly states a tier word (bedbound, housebound, severe, moderate, mild, mostly functional) or an unambiguous global functional capacity (for example, "I can't leave the house"). Do NOT infer a tier from symptoms, distress, an episodic crash, or work/school status.
- infection_count: Extract a count only when the author explicitly states how many COVID infections they have had (for example, "twice" or "3 infections"). A single mention of having COVID does NOT establish infection_count: 1; return null unless a count is stated.
