"""Shared brain constants for The Trial — the IRON RULES + citation HOW-TO.

These two strings are the contract every debate agent operates under, embedded
byte-for-byte into both HOOPER_SYSTEM and DRVEX_SYSTEM so neither persona can
"forget" them. validate.check_turn() enforces them mechanically — the prose here
is the human-readable mirror of that gate.
"""

# ── Shared IRON RULES (verbatim in BOTH system prompts) ──────────────────────
# This block is the contract every debate agent operates under. It is embedded
# byte-for-byte into HOOPER_SYSTEM and DRVEX_SYSTEM so neither persona can
# "forget" it. validate.check_turn() enforces it mechanically — the prose here
# is the human-readable mirror of that gate.
IRON_RULES = (
    "IRON RULES (break any = lose the round):\n"
    '1. State a number/percent/count or quote ONLY via its claim_id: cite("S2"), '
    'quote("Q-pos-1"). Write cite() with NO number next to it.\n'
    "2. Never tell the user to start/stop/take/dose a drug.\n"
    "3. Cite ONLY claim_ids listed in the packet; never invent one."
)

# How the agents weave claim_ids into prose. Shared so both personas cite the
# same way and the validator's render step can find them. The #1 oss failure is
# typing the number AND citing — so the cite-alone rule leads.
_CITATION_HOWTO = (
    "HOW TO CITE:\n"
    '- For ANY number, percent, or count, write cite("<id>") ALONE — e.g. cite("S2"). '
    "Do NOT type the number yourself; the system prints the exact packet text. "
    'Writing "53% cite(\\"S2\\")" is WRONG; write just cite("S2").\n'
    '- For a patient quote, write quote("<id>") alone — e.g. quote("Q-pos-1"). Never '
    "retype the quote text.\n"
    "- The packet block below lists every claim_id. It is your ONLY evidence. To note "
    "something is MISSING (e.g. no negative quotes), say so in plain words — never "
    "wrap a non-existent id in cite()/quote()."
)
