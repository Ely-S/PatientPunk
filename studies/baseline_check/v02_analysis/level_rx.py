import re
LEVEL = re.compile(r"\b(?:i'?m|i am|im|i feel(?: like)?|i'?d say i'?m|currently|now)\s+(?:at\s+)?(?:about\s+|around\s+|maybe\s+|roughly\s+|only\s+|like\s+)?(\d{1,3})\s?%\s*(?:of\s+(?:my\s+)?(?:normal|old self|former self|usual self|pre[- ]?(?:covid|illness|sick)\w*|healthy self|capacity|functioning|function|old life|baseline)|functional|functioning|recovered|back to normal|normal|healthy|of normal|capacity)\b"
                   r"|\bi'?m\s+at\s+(?:about\s+|around\s+|maybe\s+|roughly\s+|only\s+|like\s+)?(\d{1,3})\s?%"
                   r"|\b(\d{1,3})\s?%\s+(?:of\s+(?:my\s+)?(?:normal|old self|former self|usual self|pre[- ]?(?:covid|illness|sick)\w*|healthy self|old life)|functional|functioning|recovered|back to normal|of normal)\b", re.I)
EXCL = re.compile(r"\b(better|improv|worse|sure|chance|percent of (people|patients)|of people|of patients|battery|oxygen|o2|spo2|sat)")
