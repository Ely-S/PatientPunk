#!/usr/bin/env python3
"""


Processes the corpus output from scrape_corpus.py and extracts structured
biomedical signals from post and comment text using regex pattern matching.

Usage:
    python extract_biomedical.py                            # base fields, default input path
    python extract_biomedical.py --input-dir ../output/     # explicit input path
    python extract_biomedical.py --text "I'm a 34F with POTS"  # test single string
    python extract_biomedical.py --schema schemas/covidlonghaulers_schema.json

Output:
    output/patientpunk_records_base.json          # v2.0 records (base fields only)
    output/patientpunk_records_{schema_id}.json   # v2.0 records with extension fields
    output/extraction_metadata_{schema_id}.json   # summary stats
"""


import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path



# =============================================================================
# SCHEMA CONSTANTS
# =============================================================================

BASE_FIELDS = frozenset({
    "age", "sex_gender", "location_country", "healthcare_system",
    "conditions", "onset_trigger", "diagnosis_source", "time_to_diagnosis",
    "misdiagnosis", "symptom_duration", "symptom_trajectory", "age_at_onset",
    "medications", "treatment_outcome", "procedures",
    # activity_level removed -- redundant with functional_status_tier (extension).
    "work_disability_status", "mental_health",
    "doctor_dismissal", "diagnostic_odyssey",
    "prior_infections", "hormonal_events", "family_history",
})

BASE_FIELD_CONFIDENCE: dict[str, str] = {
    "age": "medium",
    "sex_gender": "high",
    "location_country": "medium",
    "healthcare_system": "high",
    "conditions": "high",
    "onset_trigger": "medium",
    "diagnosis_source": "high",
    "time_to_diagnosis": "medium",
    "misdiagnosis": "medium",
    "symptom_duration": "low",
    "symptom_trajectory": "medium",
    "age_at_onset": "medium",
    "medications": "high",
    "treatment_outcome": "medium",
    "procedures": "high",
    "work_disability_status": "high",
    "mental_health": "medium",
    "doctor_dismissal": "medium",
    "diagnostic_odyssey": "medium",
    "prior_infections": "medium",
    "hormonal_events": "medium",
    "family_history": "medium",
}

CONDITION_ICD10_MAP: dict[str, str] = {
    "long covid": "U09.9",
    "post covid": "U09.9",
    "pasc": "U09.9",
    "pots": "G90.3",
    "postural orthostatic tachycardia": "G90.3",
    "mcas": "D89.42",
    "mast cell activation": "D89.42",
    "me/cfs": "G93.3",
    "chronic fatigue syndrome": "G93.3",
    "myalgic encephalomyelitis": "G93.3",
    "fibromyalgia": "M79.3",
    "lupus": "M32.9",
    "sle": "M32.9",
    "systemic lupus": "M32.9",
    "rheumatoid arthritis": "M06.9",
    "multiple sclerosis": "G35",
    "dysautonomia": "G90.9",
    "autonomic dysfunction": "G90.9",
    "gastroparesis": "K31.84",
    "endometriosis": "N80.9",
    "lyme disease": "A69.20",
    "sarcoidosis": "D86.9",
    "small fiber neuropathy": "G60.8",
    "functional neurological disorder": "F44.9",
    "ehlers-danlos": "Q79.6",
    "crohn's": "K50.90",
    "ulcerative colitis": "K51.90",
    "hashimoto's": "E06.3",
    "graves's": "E05.00",
    "ankylosing spondylitis": "M45.9",
    "psoriatic arthritis": "L40.50",
    "interstitial cystitis": "N30.10",
}


# =============================================================================
# PATTERNS
# =============================================================================

# ---------------------------------------------------------------------------
# 1. DEMOGRAPHICS
# ---------------------------------------------------------------------------

US_STATES = (
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|"
    r"maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|"
    r"nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|"
    r"north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    r"south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
    r"wisconsin|wyoming|district of columbia|washington d\.?c\.?"
)

# ME (Maine) and OR (Oregon) are excluded because in medical subreddits
# they almost always mean ME/CFS or the conjunction "or". Both states are
# still captured by their full names in US_STATES above.
US_STATE_ABBREVS = (
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|PA|RI|SC|SD|TN|TX|UT|VT|"
    r"VA|WA|WV|WI|WY|DC)\b"
)

COUNTRIES = (
    r"united states|united kingdom|canada|australia|germany|france|netherlands|"
    r"sweden|norway|denmark|finland|switzerland|austria|belgium|spain|italy|"
    r"portugal|ireland|new zealand|japan|south korea|brazil|india|mexico|"
    r"south africa|israel|u\.s\.a?\.?|u\.k\.?|usa|uk"
)

HEALTHCARE_SYSTEMS = r"nhs|medicare|medicaid|tricare|kaiser|va hospital|veterans affairs"

PATTERNS = {

    # -------------------------------------------------------------------------
    # DEMOGRAPHICS
    # -------------------------------------------------------------------------

    # Age patterns: "28F", "28/F", "28 year old", "I am 34", "age 45", "mid-30s", "in my 40s"
    # AGE_RANGE restricts bare-number patterns to plausible adult ages (16-99),
    # filtering noise like "under age 8" or "Im 6 years in".
    "age": [
        # "28F", "36M", "19F" - NF/NM shorthand (no range needed, structure is unambiguous)
        re.compile(r"\b(\d{1,2})\s*[/|]?\s*[MFmf]\b"),
        re.compile(r"\b[MFmf]\s*/\s*(\d{1,2})\b"),
        # "50 year old", "30 year old woman" - self or other, but low noise
        re.compile(r"\b(\d{1,2})[\s-]?year[\s-]?old", re.I),
        # "age 40", "aged 49" - restrict to 16-99 to avoid "under age 8"
        re.compile(r"\bage[d]?\s+(1[6-9]|[2-9]\d)\b", re.I),
        # "I am 41", "I'm 52" - restrict to 16-99 AND require NOT followed by
        # "year(s)" (which signals duration: "I'm 3 years in") or "month(s)"
        re.compile(r"\bi(?:'m| am)\s+(1[6-9]|[2-9]\d)\b(?!\s*years?\b)(?!\s*months?\b)", re.I),
        # "turned 30" - low noise, keep as-is
        re.compile(r"\bturned\s+(\d{1,2})\b", re.I),
        # "mid-30s", "early 40s", "late 50s" - decade approximations
        re.compile(r"\b(mid|late|early)[- ](20s|30s|40s|50s|60s|70s)\b", re.I),
        # "in my 20s", "in my 40s"
        re.compile(r"\bin\s+my\s+(20s|30s|40s|50s|60s|70s)\b", re.I),
    ],

    # Sex / gender
    "sex_gender": [
        re.compile(r"\b\d{1,2}\s*/?\s*(male|female|woman|man|girl|boy|nonbinary|non-binary|enby|trans\w*)\b", re.I),
        re.compile(r"\b(male|female|woman|man|nonbinary|non-binary|enby)\s*,?\s*\d{1,2}\b", re.I),
        re.compile(r"\b\d{1,2}[/\s]?[MF]\b"),
        re.compile(r"\b[MF][/\s]?\d{1,2}\b"),
        re.compile(r"\bi(?:'m| am)\s+a\s+(woman|man|female|male|nonbinary|non-binary)\b", re.I),
        re.compile(r"\b(she/her|he/him|they/them|she/they|he/they)\b", re.I),
        re.compile(r"\bas\s+a\s+(woman|man|female|male)\b", re.I),
    ],

    # Location
    "location_us_state": [
        re.compile(r"\b(?:in|from|based in|located in|living in|i live in)\s+(" + US_STATES + r")\b", re.I),
        re.compile(r"\b(" + US_STATES + r")\b", re.I),
        re.compile(r"\b(?:in|from)\s+" + US_STATE_ABBREVS, re.I),
    ],
    "location_country": [
        re.compile(r"\b(?:in|from|based in|living in)\s+(" + COUNTRIES + r")\b", re.I),
        re.compile(r"\b(" + COUNTRIES + r")\b", re.I),
    ],
    "healthcare_system": [
        re.compile(r"\b(" + HEALTHCARE_SYSTEMS + r")\b", re.I),
    ],

    # Occupation
    "occupation": [
        re.compile(
            r"\b(?:i(?:'m| am) a|work(?:ing)? as(?: a)?|former(?:ly)?(?: a)?)\s+"
            r"(nurse|doctor|physician|teacher|engineer|lawyer|accountant|"
            r"paramedic|emt|firefighter|police|social worker|therapist|"
            r"pharmacist|dentist|veterinarian|scientist|researcher|professor|"
            r"student|caregiver|physical therapist|occupational therapist|"
            r"healthcare worker|medical professional|first responder)\b",
            re.I,
        ),
    ],

    # Ethnicity / race
    "ethnicity": [
        re.compile(
            r"\b(white|caucasian|black|african american|hispanic|latino|latina|"
            r"latinx|asian|east asian|south asian|middle eastern|native american|"
            r"indigenous|pacific islander|mixed race|biracial|multiracial)\b",
            re.I,
        ),
    ],

    # BMI / weight
    "bmi_weight": [
        re.compile(r"\bbmi\s+(?:of\s+)?(\d{2}(?:\.\d)?)\b", re.I),
        re.compile(r"\b(underweight|normal weight|overweight|obese|morbidly obese)\b", re.I),
        re.compile(r"\bweigh\s+(\d{2,3})\s*(?:lbs?|pounds?|kg|kilograms?)\b", re.I),
    ],

    # -------------------------------------------------------------------------
    # CONDITION & DIAGNOSIS
    # -------------------------------------------------------------------------

    # Common chronic / rare conditions
    "conditions": [
        re.compile(
            r"\b(long covid|long-covid|post covid|post-covid|pasc|"
            r"pots|postural orthostatic tachycardia|"
            r"mcas|mast cell activation|"
            r"me/cfs|chronic fatigue syndrome|myalgic encephalomyelitis|"
            r"dysautonomia|autonomic dysfunction|"
            r"fibromyalgia|fibro\b|"
            r"lupus|sle|systemic lupus|"
            r"ehlers.danlos|eds\b|hypermobile eds|heds\b|"
            r"small fiber neuropathy|sfn\b|"
            r"multiple sclerosis|ms\b|"
            r"rheumatoid arthritis|ra\b|"
            r"crohn.s|ulcerative colitis|ibd\b|ibs\b|"
            r"hashimoto.s|graves.s|thyroid disease|"
            r"sjogren.s|"
            r"ankylosing spondylitis|"
            r"psoriatic arthritis|"
            r"antiphospholipid syndrome|aps\b|"
            r"sarcoidosis|"
            r"interstitial cystitis|"
            r"endometriosis|"
            r"lyme disease|chronic lyme|"
            r"mold illness|cirs\b|"
            r"functional neurological disorder|fnd\b|"
            r"hypermobility spectrum disorder|hsd\b|"
            r"mito\b|mitochondrial disease|"
            r"gastroparesis|"
            r"pem\b|post.exertional malaise)\b",
            re.I,
        ),
    ],

    # Time to diagnosis
    "time_to_diagnosis": [
        re.compile(
            r"\b(?:took|waited|spent|after)\s+(\d+)\s+"
            r"(?:year|month|week)s?\s+(?:to\s+)?(?:get\s+)?(?:a\s+)?diagnos",
            re.I,
        ),
        re.compile(r"\b(\d+)\s+(?:year|month)s?\s+(?:diagnostic\s+)?odyssey\b", re.I),
        re.compile(r"\bdiagnos\w+\s+(?:after|in)\s+(\d+)\s+(?:year|month|week)s?\b", re.I),
        re.compile(r"\bfinally\s+diagnos", re.I),
        re.compile(r"\byears?\s+(?:of\s+)?(?:searching|looking|trying)\s+(?:for\s+)?(?:a\s+)?diagnos", re.I),
    ],

    # Misdiagnosis -- the second pattern requires a dismissal-context prefix so
    # it doesn't fire on genuine comorbidities ("I have anxiety from long COVID").
    "misdiagnosis": [
        re.compile(
            r"\b(misdiagnosed|wrongly diagnosed|told it was|thought it was|"
            r"dismissed as|written off as)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:misdiagnosed\s+(?:as|with)|dismissed\s+as|told\s+(?:it\s+was|I\s+(?:had|have))|"
            r"written\s+off\s+as|blamed\s+(?:on|it\s+on)|put\s+(?:it\s+)?down\s+to|"
            r"said\s+it\s+was)\s+"
            r"(anxiety|depression|hypochondria|psychosomatic|stress|all in (?:your|my) head)",
            re.I,
        ),
        re.compile(r"\b(diagnosed with .{3,60}? before (?:finally|eventually|they found|getting))\b", re.I),
    ],

    # Diagnosis source
    "diagnosis_source": [
        re.compile(
            r"\b(?:diagnosed by|confirmed by|told by)\s+(?:a\s+|my\s+)?"
            r"(gp|doctor|specialist|neurologist|cardiologist|rheumatologist|"
            r"immunologist|geneticist|long covid clinic|infectious disease|"
            r"endocrinologist|gastroenterologist|autonomic specialist)\b",
            re.I,
        ),
        re.compile(r"\b(self.diagnosed|self diagnosed|no official diagnosis|awaiting diagnosis)\b", re.I),
    ],

    # -------------------------------------------------------------------------
    # SYMPTOM ONSET & HISTORY
    # -------------------------------------------------------------------------

    # Age at onset
    # NOTE: the optional anchor (?:at\s+|when\s+i\s+was\s+)? means the first
    # pattern would match "symptoms started 5 years ago" (duration, not age).
    # Negative lookahead (?!\s*(?:years?|months?|weeks?|days?)) prevents that.
    "age_at_onset": [
        re.compile(
            r"\b(?:onset|symptoms?\s+(?:started|began)|got sick|became ill)"
            r"\s+(?:at\s+|when\s+i\s+was\s+)?(\d{1,2})\b(?!\s*(?:years?|months?|weeks?|days?))",
            re.I,
        ),
        re.compile(r"\b(?:started|began)\s+(?:at\s+age\s+|when\s+i\s+was\s+)(\d{1,2})\b", re.I),
    ],

    # Onset trigger
    "onset_trigger": [
        re.compile(
            r"\b(?:triggered|started|began|onset)\s+(?:after|following|by)\s+"
            r"(?:a\s+|an\s+)?(?:covid|infection|vaccine|vaccination|surgery|"
            r"accident|trauma|pregnancy|childbirth|stress|mold exposure|"
            r"virus|illness|flu|mono|ebv|epstein.barr|lyme)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:after|following)\s+(?:my\s+|a\s+|an\s+)?"
            r"(covid|vaccine|surgery|pregnancy|accident|infection|virus|flu|mono|lyme)\b",
            re.I,
        ),
        re.compile(r"\bno (?:known\s+)?(?:trigger|cause|reason)\b", re.I),
    ],

    # Symptom duration -- captures number + unit together (e.g. "3 years")
    # so the stored value is meaningful without context.
    "symptom_duration": [
        re.compile(r"\b(\d+\s+(?:year|month|week|day)s?)\s+(?:of\s+)?(?:symptoms?|sick|ill)\b", re.I),
        re.compile(r"\b(\d+\s+(?:year|month|week|day)s?)\s+(?:in|post|since)\b", re.I),
        re.compile(r"\b(?:for|over)\s+(\d+\s+(?:year|month|week|day)s?)\b", re.I),
    ],

    # Symptom trajectory
    "symptom_trajectory": [
        re.compile(
            r"\b(relapsing.remitting|relapse|flare|progressive|"
            r"getting worse|improving|stable|fluctuating|"
            r"boom.bust|push.crash|wax and wan[ei])\b",
            re.I,
        ),
        re.compile(r"\b(\d+\s*%\s*(?:better|worse|recovered|improved))\b", re.I),
        re.compile(r"\b(fully recovered|partially recovered|bedbound|housebound|back to normal)\b", re.I),
    ],

    # -------------------------------------------------------------------------
    # GENETICS & FAMILY HISTORY
    # -------------------------------------------------------------------------

    "family_history": [
        re.compile(
            r"\b(?:my\s+)?(mother|father|sister|brother|parent|sibling|"
            r"grandmother|grandfather|aunt|uncle|cousin|daughter|son|child|"
            r"family member)\s+(?:also\s+)?(?:has|had|was diagnosed with|"
            r"suffers? from|deals? with)\b",
            re.I,
        ),
        re.compile(r"\b(?:runs? in (?:my|the|our) family|hereditary|genetic|familial)\b", re.I),
        re.compile(r"\bfamily history\s+of\b", re.I),
    ],

    "genetic_testing": [
        re.compile(r"\b(23andme|ancestry\.com|genetic test|gene panel|whole genome|exome|snp\b)\b", re.I),
        re.compile(r"\b(mthfr|comt|brca|hla-b27|hla\b|cftr|factor [vx]|prothrombin)\b", re.I),
    ],

    # -------------------------------------------------------------------------
    # TREATMENTS & INTERVENTIONS
    # -------------------------------------------------------------------------

    # Medications (broad coverage for chronic illness communities)
    "medications": [
        re.compile(
            r"\b(ldn|low dose naltrexone|naltrexone|"
            r"hydroxychloroquine|plaquenil|"
            r"methotrexate|"
            r"ivermectin|"
            r"paxlovid|nirmatrelvir|"
            r"beta.?blocker|metoprolol|propranolol|atenolol|bisoprolol|"
            r"ivabradine|"
            r"fludrocortisone|florinef|"
            r"midodrine|"
            r"mestinon|pyridostigmine|"
            r"antihistamine|cetirizine|loratadine|fexofenadine|diphenhydramine|"
            r"h1 blocker|h2 blocker|famotidine|ranitidine|"
            r"cromolyn|"
            r"prednisone|prednisolone|corticosteroid|steroid\b|"
            r"ivig|intravenous immunoglobulin|"
            r"rituximab|"
            r"ssri\b|snri\b|fluoxetine|sertraline|venlafaxine|duloxetine|"
            r"tricyclic|amitriptyline|nortriptyline|"
            r"gabapentin|pregabalin|lyrica\b|"
            r"modafinil|armodafinil|"
            r"adderall|methylphenidate|ritalin|"
            r"levocarnitine|carnitine|"
            r"coq10|ubiquinol|coenzyme q|"
            r"nac\b|n-acetyl cysteine|"
            r"d-ribose|"
            r"magnesium\b|"
            r"b12\b|vitamin b12|methylcobalamin|"
            r"vitamin d\b|"
            r"omega.3|fish oil|"
            r"probiotics?\b|"
            r"melatonin\b|"
            r"medical cannabis|medical marijuana|cbd\b|thc\b|"
            r"ketamine\b|"
            r"naltrexone)\b",
            re.I,
        ),
    ],

    # Dosage
    "dosage": [
        re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|ug|ml|g\b|iu\b|units?)\b", re.I),
        re.compile(r"\b(low dose|high dose|standard dose|microdose)\b", re.I),
    ],

    # Treatment outcomes
    "treatment_outcome": [
        re.compile(
            r"\b(?:it|which|that|this)?\s*(?:really\s+|significantly\s+|slightly\s+|somewhat\s+)?"
            r"(helped|helped me|worked|cured|fixed|resolved|improved|made (?:it |things? )?better)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:it|which|that|this)?\s*(?:really\s+|significantly\s+|slightly\s+|somewhat\s+)?"
            r"(didn.t help|didn.t work|made (?:it |things? )?worse|"
            r"no (?:effect|improvement|difference|change)|worsened|crashed me|caused a flare)\b",
            re.I,
        ),
        re.compile(r"\b(\d+\s*%\s*(?:better|worse|improvement|reduction))\b", re.I),
    ],

    # Surgery / procedures
    "procedures": [
        re.compile(
            r"\b(surgery|operation|procedure|biopsy|infusion|injection|"
            r"tilt table test|autonomic testing|nerve conduction|emg\b|"
            r"mri\b|ct scan|pet scan|echocardiogram|holter monitor|"
            r"lumbar puncture|spinal tap|colonoscopy|endoscopy|"
            r"skin punch biopsy|epigenetic testing)\b",
            re.I,
        ),
    ],

    # Dietary interventions
    "dietary_interventions": [
        re.compile(
            r"\b(low histamine|low.fodmap|fodmap|gluten.free|dairy.free|"
            r"carnivore diet|keto|ketogenic|paleo|anti.inflammatory diet|"
            r"elimination diet|fasting|intermittent fasting|"
            r"mast cell diet|low oxalate|low salicylate)\b",
            re.I,
        ),
    ],

    # Alternative / complementary
    "alternative_treatments": [
        re.compile(
            r"\b(acupuncture|chiropractic|osteopath|naturopath|"
            r"homeopathy|homeopathic|herbal|ayurvedic|"
            r"hyperbaric oxygen|hbot\b|"
            r"ozone therapy|"
            r"infrared sauna|"
            r"grounding|earthing|"
            r"pacing|energy envelope|"
            r"mindfulness|meditation|breathwork|"
            r"cbt\b|cognitive behavioral therapy|"
            r"lightning process|gupta program|"
            r"stellate ganglion block)\b",
            re.I,
        ),
    ],

    # -------------------------------------------------------------------------
    # FUNCTIONAL & QUALITY OF LIFE
    # -------------------------------------------------------------------------

    "work_disability_status": [
        re.compile(
            r"\b(on disability|disability benefits|ssdi\b|ssi\b|pip\b|"
            r"universal credit|had to quit|lost my job|can.t work|unable to work|"
            r"working reduced hours|part.time|work from home|medical leave|"
            r"fmla\b|long.term sick|sick leave|still working|back to work)\b",
            re.I,
        ),
    ],

    # activity_level removed -- redundant with functional_status_tier (extension field).
    # Its patterns (bedbound, housebound, etc.) are already in the extension schema.

    "mental_health": [
        re.compile(
            r"\b(depression|depressed|anxiety|anxious|ptsd\b|"
            r"suicidal|burnout|grief|"
            r"mental health impact|"
            r"therapist|psychologist|psychiatrist|counseling|therapy)\b",
            re.I,
        ),
    ],

    "social_impact": [
        re.compile(
            r"\b(lost (?:my )?\w+ (?:friends?|relationships?|marriage|partner)|"
            r"partner left|family (?:doesn.t|don.t) believe|"
            r"isolated|isolation|lonely|alone|"
            r"caregiver|carer|dependent on)\b",
            re.I,
        ),
    ],

    # -------------------------------------------------------------------------
    # HEALTHCARE EXPERIENCE
    # -------------------------------------------------------------------------

    "doctor_dismissal": [
        re.compile(
            r"\b(doctor didn.t believe|told it was anxiety|"
            r"dismissed|gaslit|gaslighting|"
            r"all in (?:your|my) head|"
            r"psychosomatic|"
            r"told to exercise more|"
            r"doctor (?:said|told me) (?:i was|there was) (?:fine|nothing wrong|normal)|"
            r"tests? (?:came back |were? )?(?:all )?normal but|"
            r"no one believes?\s+me)\b",
            re.I,
        ),
    ],

    "diagnostic_odyssey": [
        re.compile(r"\b(?:saw|visited|been to)\s+(\d+)\s+(?:doctors?|specialists?|physicians?)\b", re.I),
        re.compile(r"\b(\d+)\s+(?:doctors?|specialists?)\s+(?:later|before|until)\b", re.I),
        re.compile(r"\byears?\s+(?:of\s+)?(?:searching|looking|trying)\b", re.I),
    ],

    "healthcare_costs": [
        re.compile(
            r"\b(?:paid|spent|cost(?:ing)?|out of pocket)\s+"
            r"\$[\d,]+|\b\$[\d,]+\s+(?:for|on|out)\b",
            re.I,
        ),
        re.compile(r"\b(can.t afford|insurance (?:won.t|denied|refused)|"
                   r"insurance coverage|out of pocket|self.pay|self.funded)\b", re.I),
    ],

    # -------------------------------------------------------------------------
    # EXPOSURES & RISK FACTORS
    # -------------------------------------------------------------------------

    "toxic_exposures": [
        re.compile(
            r"\b(mold|toxic mold|black mold|mycotoxin|"
            r"chemical exposure|pesticide|herbicide|heavy metal|"
            r"mercury|lead poisoning|arsenic|"
            r"silicone implant|breast implant illness|"
            r"tick bite|lyme|"
            r"military service|gulf war)\b",
            re.I,
        ),
    ],

    "trauma_history": [
        re.compile(
            r"\b(trauma|traumatic|abuse|childhood trauma|"
            r"ptsd\b|adverse childhood|aces\b|"
            r"sexual abuse|physical abuse|domestic violence)\b",
            re.I,
        ),
    ],

    "hormonal_events": [
        re.compile(
            r"\b(pregnancy|postpartum|post.partum|after (?:giving )?birth|"
            r"menopause|perimenopause|puberty|"
            r"hormonal|hormone|birth control|oral contraceptive|"
            r"hysterectomy|oophorectomy|endometriosis flare)\b",
            re.I,
        ),
    ],

    "prior_infections": [
        re.compile(
            r"\b(epstein.barr|ebv\b|mono\b|mononucleosis|"
            r"lyme disease|chronic lyme|"
            r"covid|sars.?cov|"
            r"herpes|hsv\b|"
            r"cmv\b|cytomegalovirus|"
            r"hpv\b|"
            r"parvovirus|slapped cheek|"
            r"ross river|"
            r"q fever)\b",
            re.I,
        ),
    ],

}


# =============================================================================
# POST-EXTRACTION CANONICALIZATION
# =============================================================================

# Condition synonyms -> canonical form. Checked in order, first match wins.
_CONDITION_CANONICAL: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:long[\s-]?covid|post[\s-]?covid|pasc|post[\s-]?acute sequelae)$", re.I), "long covid"),
    (re.compile(r"^(?:me/?cfs|myalgic encephalomyelitis|chronic fatigue syndrome)$", re.I), "me/cfs"),
    (re.compile(r"^(?:post[\s-]?exertional malaise|post[\s-]?exertional|pem)$", re.I), "pem"),
    (re.compile(r"^(?:post[\s-]?viral|post[\s-]?infectious)$", re.I), "post-viral"),
    (re.compile(r"^(?:small fiber neuropathy|sfn)$", re.I), "small fiber neuropathy"),
    (re.compile(r"^(?:ehlers[\s-]?danlos|eds|heds)$", re.I), "ehlers-danlos syndrome"),
]


def _canonicalize_conditions(values: list[str]) -> list[str]:
    """Normalize condition names to canonical forms and deduplicate."""
    seen: set[str] = set()
    canonical: list[str] = []
    for raw_value in values:
        normalized = raw_value.strip().lower()
        for pattern, replacement in _CONDITION_CANONICAL:
            if pattern.match(normalized):
                normalized = replacement
                break
        if normalized not in seen:
            seen.add(normalized)
            canonical.append(normalized)
    return canonical


# =============================================================================
# EXTRACTION ENGINE
# =============================================================================

def extract_from_text(text: str, patterns: dict = None) -> dict:
    """Run all patterns against a single text string. Returns a dict of matches."""
    if patterns is None:
        patterns = PATTERNS
    results = {}
    for field, pattern_list in patterns.items():
        matches = []
        for pat in pattern_list:
            for m in pat.finditer(text):
                # Prefer captured group if present, else full match
                value = m.group(1) if m.lastindex else m.group(0)
                value = value.strip().lower()
                if value and value not in matches:
                    matches.append(value)
        if matches:
            results[field] = matches
    return results


def extract_from_texts(texts: list[str], patterns: dict = None) -> dict:
    """Merge extractions across multiple texts (all posts + comments for a user).

    After merging, applies field-specific canonicalization (e.g. normalizing
    condition names) so downstream aggregation is cleaner.
    """
    if patterns is None:
        patterns = PATTERNS
    merged: dict[str, list] = defaultdict(list)
    for text in texts:
        if not text:
            continue
        result = extract_from_text(text, patterns=patterns)
        for field, values in result.items():
            for v in values:
                if v not in merged[field]:
                    merged[field].append(v)

    # Canonicalize condition names to merge variants
    if "conditions" in merged:
        merged["conditions"] = _canonicalize_conditions(merged["conditions"])

    return dict(merged)


# =============================================================================
# SCHEMA LOADING & COMPILATION
# =============================================================================

def load_extension_schema(schema_path: Path) -> dict:
    """Load and validate a JSON extension schema file.

    Raises SystemExit with a clear human-readable message on any failure.
    """
    import sys

    if not schema_path.exists():
        sys.exit(f"Schema file not found: {schema_path}")

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as exc:
        sys.exit(f"Schema file is not valid JSON: {schema_path}\n  {exc}")

    if "schema_id" not in schema or not isinstance(schema["schema_id"], str):
        sys.exit(f"Schema missing required string field 'schema_id': {schema_path}")

    for field in schema.get("include_base_fields", []):
        if field not in PATTERNS:
            sys.exit(
                f"Schema 'include_base_fields' references unknown field '{field}'. "
                f"Available base-optional fields: {sorted(set(PATTERNS.keys()) - BASE_FIELDS)}"
            )

    for field, override in schema.get("override_base_patterns", {}).items():
        if "mode" not in override or override["mode"] not in ("append", "replace"):
            sys.exit(
                f"Schema 'override_base_patterns.{field}' must have 'mode' of "
                f"'append' or 'replace'."
            )
        if "patterns" not in override or not isinstance(override["patterns"], list):
            sys.exit(
                f"Schema 'override_base_patterns.{field}' must have a 'patterns' list."
            )
        for i, p in enumerate(override["patterns"]):
            try:
                re.compile(p, re.I)
            except re.error as exc:
                sys.exit(
                    f"Schema 'override_base_patterns.{field}.patterns[{i}]' "
                    f"failed to compile: {exc}"
                )

    for field, defn in schema.get("extension_fields", {}).items():
        if "patterns" not in defn or not isinstance(defn["patterns"], list):
            sys.exit(
                f"Schema 'extension_fields.{field}' must have a 'patterns' list."
            )
        for i, p in enumerate(defn["patterns"]):
            try:
                re.compile(p, re.I)
            except re.error as exc:
                sys.exit(
                    f"Schema 'extension_fields.{field}.patterns[{i}]' "
                    f"failed to compile: {exc}"
                )

    return schema


def compile_extension_patterns(schema: dict) -> tuple[dict, set]:
    """Compile a loaded extension schema into active patterns and extension field names.

    Returns:
        active_patterns: dict mapping field name → list of compiled regex patterns
        extension_field_names: set of field names added/reactivated beyond BASE_FIELDS
    """
    # Start with base fields only
    active_patterns = {k: PATTERNS[k] for k in BASE_FIELDS if k in PATTERNS}

    # Reactivate base-optional fields
    for field in schema.get("include_base_fields", []):
        active_patterns[field] = PATTERNS[field]

    # Override/append patterns for existing fields
    for field, override in schema.get("override_base_patterns", {}).items():
        compiled = [re.compile(p, re.I) for p in override["patterns"]]
        if override["mode"] == "append":
            active_patterns[field] = active_patterns.get(field, []) + compiled
        else:  # replace
            active_patterns[field] = compiled

    # Add entirely new extension fields (skip llm_discovered - those are handled
    # by discover_fields.py Phase 3 which has timeout protection and per-text processing)
    for field, defn in schema.get("extension_fields", {}).items():
        if defn.get("source") == "llm_discovered":
            continue
        active_patterns[field] = [re.compile(p, re.I) for p in defn["patterns"]]

    extension_field_names = (
        set(schema.get("include_base_fields", []))
        | set(schema.get("extension_fields", {}).keys())
    )

    return active_patterns, extension_field_names


def build_record(
    raw_extracted: dict,
    source: str,
    author_hash: str,
    text_count: int,
    extension_field_names: set,
    schema: dict | None,
    post_id: str | None = None,
) -> dict:
    """Assemble a structured PatientPunk v2.0 record.

    Args:
        raw_extracted: field → [values] dict from extract_from_texts
        source: "user_history" or "subreddit_post"
        author_hash: SHA-256 hashed username
        text_count: number of text segments processed
        extension_field_names: set of fields that belong in the extension namespace
        schema: loaded extension schema dict, or None for base-only run
        post_id: post identifier for subreddit_post records
    """
    provenance = "self_reported" if source == "user_history" else "mentioned_by_other"

    # Build base namespace - all 24 BASE_FIELDS always present
    base: dict = {}
    for field in sorted(BASE_FIELDS):
        values = raw_extracted.get(field) or None
        confidence = BASE_FIELD_CONFIDENCE.get(field)

        if field == "conditions" and values:
            icd10_candidates = {
                v: CONDITION_ICD10_MAP[v]
                for v in values
                if v in CONDITION_ICD10_MAP
            }
            base[field] = {
                "values": values,
                "icd10_candidates": icd10_candidates if icd10_candidates else None,
                "provenance": provenance if values else None,
                "confidence": confidence if values else None,
            }
        else:
            base[field] = {
                "values": values,
                "provenance": provenance if values else None,
                "confidence": confidence if values else None,
            }

    # Build extension namespace
    extension: dict | None = None
    if schema is not None:
        extension = {}
        ext_confidence_overrides = {
            field: defn.get("confidence", "medium")
            for field, defn in schema.get("extension_fields", {}).items()
        }
        for field in sorted(extension_field_names):
            values = raw_extracted.get(field) or None
            conf = ext_confidence_overrides.get(field, "medium")
            extension[field] = {
                "values": values,
                "provenance": provenance if values else None,
                "confidence": conf if values else None,
            }

    record: dict = {
        "_patientpunk_version": "2.0",
        "_schema_id": schema["schema_id"] if schema else "base",
        "_extracted_at": datetime.now(timezone.utc).isoformat(),
        "record_meta": {
            "author_hash": author_hash,
            "source": source,
            "text_count": text_count,
            "post_id": post_id,
        },
        "base": base,
    }
    if schema is not None:
        record["extension"] = extension
    return record


# =============================================================================
# CORPUS PROCESSING
# =============================================================================

_REDDIT_REMOVED = frozenset({"[removed]", "[deleted]"})


def _keep_text(raw: str | None) -> str | None:
    """Strip whitespace and return None for empty or Reddit-removed placeholders."""
    cleaned = (raw or "").strip()
    return cleaned if cleaned and cleaned not in _REDDIT_REMOVED else None


def collect_texts_from_user(user_data: dict) -> list[str]:
    """Collect non-empty, non-removed text segments from a user history dict."""
    texts: list[str] = []
    for post in user_data.get("posts", []):
        for raw in (post.get("title"), post.get("body")):
            kept = _keep_text(raw)
            if kept:
                texts.append(kept)
    for comment in user_data.get("comments", []):
        kept = _keep_text(comment.get("body"))
        if kept:
            texts.append(kept)
    return texts


def collect_texts_from_post(post: dict) -> list[str]:
    """Collect non-empty, non-removed text segments from a subreddit post."""
    texts: list[str] = []
    for raw in (post.get("title"), post.get("body")):
        kept = _keep_text(raw)
        if kept:
            texts.append(kept)
    for comment in post.get("comments", []):
        kept = _keep_text(comment.get("body"))
        if kept:
            texts.append(kept)
    return texts


def process_corpus(
    input_dir: Path,
    active_patterns: dict = None,
    extension_field_names: set = None,
    schema: dict | None = None,
) -> tuple[list[dict], dict]:
    users_dir = input_dir / "users"
    posts_file = input_dir / "subreddit_posts.json"

    extractions = []
    field_hit_counts: dict[str, int] = defaultdict(int)

    # Process user files
    if users_dir.exists():
        user_files = list(users_dir.glob("*.json"))
        print(f"Processing {len(user_files)} user files...")
        for i, user_file in enumerate(user_files, 1):
            if i % 10 == 0:
                print(f"  {i}/{len(user_files)}")
            with open(user_file, encoding="utf-8") as f:
                user_data = json.load(f)

            texts = collect_texts_from_user(user_data)
            extracted = extract_from_texts(texts, patterns=active_patterns)
            for field in extracted:
                field_hit_counts[field] += 1

            extractions.append(build_record(
                raw_extracted=extracted,
                source="user_history",
                author_hash=user_data.get("author_hash"),
                text_count=len(texts),
                extension_field_names=extension_field_names or set(),
                schema=schema,
            ))

    # Process subreddit posts
    if posts_file.exists():
        print("Processing subreddit posts file...")
        with open(posts_file, encoding="utf-8") as f:
            posts = json.load(f)

        for post in posts:
            texts = collect_texts_from_post(post)
            extracted = extract_from_texts(texts, patterns=active_patterns)
            for field in extracted:
                field_hit_counts[field] += 1

            extractions.append(build_record(
                raw_extracted=extracted,
                source="subreddit_post",
                author_hash=post.get("author_hash"),
                text_count=len(texts),
                extension_field_names=extension_field_names or set(),
                schema=schema,
                post_id=post.get("post_id"),
            ))

    metadata = {
        "total_records_processed": len(extractions),
        "field_hit_counts": dict(sorted(field_hit_counts.items(), key=lambda x: -x[1])),
        "fields_available": sorted((active_patterns or PATTERNS).keys()),
        "schema_id": schema["schema_id"] if schema else "base",
        "extension_fields_active": sorted(extension_field_names) if extension_field_names else [],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }

    return extractions, metadata


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract biomedical signals from PatientPunk corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Step 1 of the PatientPunk extraction pipeline. Fast, free, no API key needed.
Regex patterns match across 24 base fields plus any hand-crafted extension schema
fields. Extension fields with source="llm_discovered" are SKIPPED here - those
are handled exclusively by discover_fields.py Phase 3, which has timeout
protection and per-text-segment processing to prevent cross-post bleed.

Examples:
  python extract_biomedical.py
  python extract_biomedical.py --schema schemas/covidlonghaulers_schema.json
  python extract_biomedical.py --text "34F with POTS, diagnosed after 3 years"
  python extract_biomedical.py --input-dir /path/to/output

Output:
  output/patientpunk_records_base.json         one v2.0 record per user/post
  output/patientpunk_records_{schema_id}.json  with extension schema fields
  output/extraction_metadata_{schema_id}.json  field hit counts and summary

Every base field is always present (null if not extracted). Conditions include
ICD-10 candidates. All fields include provenance and confidence tiers.

Next step: python llm_extract.py  (fills gaps with Claude Haiku; --merge is on by default)
        """,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data",
        help="Path to the output/ directory from scrape_corpus.py "
             "(default: ../output/ relative to this script)",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Test mode: extract from a single string and print results.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to a JSON extension schema file. Adds bespoke fields on top of the "
             "universal base. Example: schemas/covidlonghaulers_schema.json",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=None,
        help="Directory for intermediate output files (default: {input-dir}/temp/). "
             "Keeps output/ clean - only records.csv and codebook.csv stay at the top level.",
    )
    args = parser.parse_args()

    # Load schema and build active patterns
    schema = None
    active_patterns = {k: PATTERNS[k] for k in BASE_FIELDS if k in PATTERNS}
    extension_field_names: set = set()

    if args.schema:
        schema = load_extension_schema(args.schema)
        active_patterns, extension_field_names = compile_extension_patterns(schema)

    # Test mode
    if args.text:
        results = extract_from_text(args.text, patterns=active_patterns)
        base_results = {k: v for k, v in results.items() if k in BASE_FIELDS}
        ext_results = {k: v for k, v in results.items() if k in extension_field_names}

        print("=== Base fields ===")
        print(json.dumps(base_results, indent=2))
        if schema is not None:
            print("\n=== Extension fields ===")
            print(json.dumps(ext_results, indent=2))
        return

    # Full corpus mode
    output_dir = args.input_dir
    if not output_dir.exists():
        print(f"Error: {output_dir} does not exist. Run scrape_corpus.py first.")
        return

    temp_dir = args.temp_dir if args.temp_dir else output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting biomedical signals from {output_dir}...\n")

    extractions, metadata = process_corpus(
        output_dir,
        active_patterns=active_patterns,
        extension_field_names=extension_field_names,
        schema=schema,
    )

    # Write outputs to temp/
    schema_id = schema["schema_id"] if schema else "base"
    extractions_file = temp_dir / f"patientpunk_records_{schema_id}.json"
    metadata_file = temp_dir / f"extraction_metadata_{schema_id}.json"

    with open(extractions_file, "w", encoding="utf-8") as f:
        json.dump(extractions, f, ensure_ascii=False, indent=2)

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    schema_label = schema["schema_id"] if schema else "base only"
    ext_count = len(extension_field_names)
    reactivated = len(schema.get("include_base_fields", [])) if schema else 0
    new_ext = len(schema.get("extension_fields", {})) if schema else 0

    print(f"\nDone!")
    print(f"  Records processed : {metadata['total_records_processed']}")
    print(f"  Base fields       : 24 (always)")
    print(f"  Schema            : {schema_label}")
    if schema:
        print(f"  Extension fields  : {new_ext} new + {reactivated} reactivated")
    print(f"  Output            : {extractions_file}")
    print(f"\n  Field hit counts:")
    for field, count in metadata["field_hit_counts"].items():
        print(f"    {field:<30} {count}")


if __name__ == "__main__":
    main()
