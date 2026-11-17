import json, sys
KEYS = ["first_person_patient","describes_change","activity_capacity_change","symptom_severity_change","crash_change",
 "activity_restriction_explains_symptoms","cost_of_activity_mentioned","fluctuation_mentioned","self_rated_percent",
 "current_severity","domains_changed","units","milestones","what_matters_most","questionnaire_gap","quote"]
def w(path, rows):
    with open(path, "a") as f:
        for r in rows:
            i, vals = r[0], r[1:]
            assert len(vals) == len(KEYS), (i, len(vals))
            f.write(json.dumps({"id": i, "code": dict(zip(KEYS, vals))}) + "\n")
