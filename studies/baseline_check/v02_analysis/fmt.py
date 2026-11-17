import json,sys
D=dict(first_person_patient=False,describes_change=False,activity_capacity_change="not_mentioned",symptom_severity_change="not_mentioned",crash_change="not_mentioned",activity_restriction_explains_symptoms=False,cost_of_activity_mentioned=False,fluctuation_mentioned=False,self_rated_percent=None,current_severity="unstated",domains_changed=[],units=["none"],milestones=[],what_matters_most=None,questionnaire_gap=None,quote=None)
def w(path,rows):
    with open(path,"a") as f:
        for i,o in rows:
            c=dict(D);c.update(o);assert set(c)==set(D)
            f.write(json.dumps({"id":i,"code":c})+"\n")
