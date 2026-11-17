import json
D=dict(first_person_patient=True,describes_change=False,activity_capacity_change="not_mentioned",symptom_severity_change="not_mentioned",crash_change="not_mentioned",activity_restriction_explains_symptoms=False,cost_of_activity_mentioned=False,fluctuation_mentioned=False,self_rated_percent=None,current_severity="unstated",domains_changed=[],units=["none"],milestones=[],what_matters_most=None,questionnaire_gap=None,quote=None)
def w(id,**k):
    c=dict(D);c.update(k)
    open("chunk_3.jsonl","a").write(json.dumps({"id":id,"code":c})+"\n")
