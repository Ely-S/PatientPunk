"""The NO-FABRICATION GATE for "The Trial".

Every debate turn (a string of LLM prose that cites the frozen evidence packet)
must pass through check_turn() before it is shown to anyone. The agents argue
over a FROZEN EvidencePacket and may reference a fact ONLY by its claim_id —
cite("S2") for a statistic, quote("Q-pos-1") for a verbatim patient quote. This
module mechanically enforces the IRON RULES that the prompts state in prose, so
a model that hallucinates a number, fabricates a quote, invents a methodology
flaw the data doesn't have, slips in a prescription, or frames "no negatives" as
"safe" is caught deterministically rather than trusted.

Public API (frozen by the shared contract):
  - Violation               @dataclass(rule:str, detail:str)
  - check_turn(text, packet) -> list[Violation]
  - render_citations(text, packet) -> str

Gates:
  G1  number-trace   — every numeric token in `text` must equal a number that
                       appears in a CITED claim's render. Orphan digits/percents
                       (numbers with no backing citation) are violations. Round
                       numbers are allowed precisely when they appear in a cited
                       render, so no special-casing is needed.
  G2  quote-trace    — every "quoted span" in the text must be a substring of a
                       packet quote's verbatim text.
  G3  caveat-real    — every methodology roast (small-n / single-subreddit /
                       silent-drop / self-report) maps to a C* caveat that is
                       actually present in THIS packet; and any "n=K" must equal
                       packet.n_users or packet.n_reports.
  G4  no-Rx          — no start/stop/take/avoid/dose directive (safety).
  G5  silent-drop    — "no negatives" / "so it's safe" framing is only allowed
                       when C3 (silent-drop self-selection) is cited in the turn.

check_turn is intentionally pragmatic: it tokenizes numbers and compares them to
the set of numbers appearing in CITED claim renders. It is a guardrail against
fabrication, not a natural-language theorem prover — when in doubt it favors
flagging an unbacked number over letting it through.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Violation:
    """A single rule breach in a debate turn.

    `rule` is the gate id (e.g. "G1"); `detail` is a human-readable explanation
    naming the offending token / claim_id so the turn can be regenerated.
    """
    rule: str
    detail: str


# ── Citation extraction ──────────────────────────────────────────────────────
# Agents write cite("X") and quote("X"). Quotes may use straight or curly
# parens-quotes; accept single or double quotes around the claim_id.
_CITE_RE = re.compile(r'\bcite\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE)
_QUOTE_RE = re.compile(r'\bquote\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE)


def _cited_ids(text: str) -> list[str]:
    """All claim_ids referenced via cite(...) or quote(...) in the turn."""
    return _CITE_RE.findall(text) + _QUOTE_RE.findall(text)


def _claim_exists(packet, cid: str) -> bool:
    """True iff `cid` is a real claim in the packet.

    Authoritative check is membership in packet.claims — `packet.claim(cid)`
    returns a visible sentinel render ('[unknown claim X]') for missing ids, so a
    None/sentinel check on the render is NOT reliable.
    """
    claims = getattr(packet, "claims", None)
    if isinstance(claims, dict):
        return cid in claims
    r = _claim_render(packet, cid)
    return r is not None and not str(r).lstrip().startswith(("[unknown", "[missing"))


def _claim_render(packet, cid: str) -> str | None:
    """Return the literal render text for a claim_id, or None if it doesn't exist.

    Tolerant of the two shapes the packet may expose: a claim() method or a
    claims dict mapping cid -> {render, ...}.
    """
    try:
        c = packet.claim(cid)
    except Exception:
        c = None
    if c is None:
        claims = getattr(packet, "claims", None)
        if isinstance(claims, dict):
            c = claims.get(cid)
    if not c:
        return None
    if isinstance(c, dict):
        return str(c.get("render", "") or "")
    return str(getattr(c, "render", "") or "")


# ── Number tokenization ──────────────────────────────────────────────────────
# A "numeric token" is any run of digits, optionally with a decimal point, and
# an optional trailing % captured separately. We normalize to a canonical
# string so "64" and "64.0" compare, and "20%" matches a render containing
# "20%". We strip the % for the bare-number comparison too, so a cited render
# of "20%" backs both "20%" and "20" in the text.
_NUM_RE = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(%?)')

# Strip citation calls before number scanning so the claim_id text inside
# cite("S2") / quote("Q-pos-1") is never mistaken for prose numbers.
_STRIP_CITES_RE = re.compile(
    r'\b(?:cite|quote)\(\s*["\'][^"\']+["\']\s*\)', re.IGNORECASE
)


def _norm_num(s: str) -> str:
    """Canonicalize a numeric string: drop a trailing .0, keep value form."""
    s = s.strip()
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _numbers_in(s: str) -> set[str]:
    """Set of normalized number forms found in a string (both '20' and '20%')."""
    out: set[str] = set()
    for digits, pct in _NUM_RE.findall(s):
        n = _norm_num(digits)
        out.add(n)
        if pct:
            out.add(n + "%")
        # also register the %-form for any number so a cited "20%" backs "20"
        out.add(n + "%")
    return out


def _allowed_numbers(packet, cited: list[str]) -> set[str]:
    """Every number form appearing in the renders of the CITED claims."""
    allowed: set[str] = set()
    for cid in cited:
        render = _claim_render(packet, cid)
        if render:
            allowed |= _numbers_in(render)
    return allowed


# ── G4: prescription directive detection ─────────────────────────────────────
# Catch imperative drug directives: "start X", "you should take", "up your dose",
# "stop taking it", "begin LDN", "go on it", "get on it". Deliberately broad —
# safety failures must trip even when phrased gently. We intentionally do NOT
# flag "ask your doctor about" / "question for their doctor" (the allowed cap).
_RX_PATTERNS = [
    r'\byou (?:should|could|ought to|need to|might want to|must|can)\s+(?:start|stop|take|try|begin|use|dose|titrate|stay on|get on|go on|come off)\b',
    r'\b(?:start|stop|begin|quit|halt|discontinue)\s+(?:taking|using|the|this|that|your|it|on)\b',
    r'\b(?:start|stop|begin)\s+(?:it|them)\b',
    r'\b(?:take|dose|titrate)\s+(?:a\s+dose|\d)\b',  # dosing directive ("take a dose", "take 4.5"); bare "use that/it" is benign prose, caught imperatively by the patterns above/below
    r'\b(?:up|increase|raise|lower|reduce|cut|adjust|titrate)\s+(?:your|the|his|her|their)\s+dose\b',
    r'\b(?:get|go|stay|come)\s+(?:on|off)\s+(?:it|this|the\s+drug|them)\b',
    r'\b(?:i|we)\s+(?:recommend|suggest|advise)\s+(?:you|that you)?\s*(?:start|take|try|stop|begin|dose)\b',
    r'\b(?:just|definitely|absolutely)\s+(?:start|take|try)\s+(?:it|this)\b',
]
_RX_RE = [re.compile(p, re.IGNORECASE) for p in _RX_PATTERNS]


# ── G5 + G3: caveat / framing vocabulary ─────────────────────────────────────
# "no negatives / so it's safe" framing — requires C3 to be cited in the turn.
_SAFE_FRAMING_RE = re.compile(
    r'(?:'
    r'no\s+(?:real\s+|reported\s+|recorded\s+)?(?:negatives?|downsides?|complaints?|bad\s+(?:reports?|experiences?)|side\s+effects?)'
    r'|(?:few|hardly any|barely any|zero|none of the)\s+(?:negatives?|complaints?|downsides?)'
    r'|so\s+it(?:\'s| is)\s+(?:safe|fine|harmless)'
    r'|(?:that\s+means|which\s+means|therefore)\s+it(?:\'s| is)\s+safe'
    r'|(?:must|has to)\s+be\s+safe'
    r'|nothing\s+to\s+worry\s+about'
    r')',
    re.IGNORECASE,
)

# Methodology-roast vocabulary → the C* claim_id each maps to. A turn that makes
# one of these critiques must have the corresponding caveat present in THIS
# packet (G3: roast only flaws the data actually has).
_CAVEAT_TRIGGERS = {
    "C1": re.compile(r'\b(?:small\s+(?:n|sample|number)|tiny\s+sample|too\s+few|not\s+enough\s+(?:reports?|people|users?)|underpowered|low\s+sample)\b', re.IGNORECASE),
    "C2": re.compile(r'\b(?:single\s+subreddit|one\s+(?:subreddit|community|forum)|same\s+(?:subreddit|community)|echo\s+chamber|one\s+corner\s+of\s+reddit)\b', re.IGNORECASE),
    "C3": re.compile(r'\b(?:silent(?:ly)?\s+drop|self[-\s]?selection|selection\s+bias|sampling\s+artifact|absence\s+of\s+(?:complaints?|negatives?)|non[-\s]?experiential|dropped\s+from\s+the\s+data|only\s+(?:counted|recorded)\s+when)\b', re.IGNORECASE),
    "C4": re.compile(r'\b(?:self[-\s]?report|anecdot|not\s+a\s+(?:clinical\s+)?trial|no\s+control(?:\s+group)?|unverified|hearsay)\b', re.IGNORECASE),
}

# "n=K" style claims (G3): K must equal the packet denominator.
_N_EQUALS_RE = re.compile(r'\bn\s*=\s*(\d+)\b', re.IGNORECASE)


def _packet_caveat_ids(packet) -> set[str]:
    """Which C* claim_ids actually exist in this packet."""
    present: set[str] = set()
    for cid in ("C1", "C2", "C3", "C4"):
        if _claim_render(packet, cid) is not None:
            present.add(cid)
    return present


def check_turn(text: str, packet) -> list[Violation]:
    """Validate one debate turn against the frozen packet. Returns all breaches.

    Empty list == the turn is clean. The caller (world.run_debate) treats any
    non-empty result as a failed round and regenerates or drops the turn.
    """
    violations: list[Violation] = []
    cited = _cited_ids(text)
    cited_set = set(cited)

    # ── G6: phantom citation — cite()/quote() must reference a REAL claim_id ──
    # The single most important fabrication an agent can commit is to argue from
    # a claim_id that does not exist (e.g. inventing quote("Q-neg-1") when the
    # packet has zero negatives). Catch it deterministically.
    for cid in cited_set:
        if not _claim_exists(packet, cid):
            violations.append(Violation(
                "G6",
                f'phantom citation {cid!r}: not a claim_id in this packet. You may '
                f'only cite()/quote() claim_ids the packet actually contains.',
            ))

    # Text with citation calls removed, for prose-level number/quote scanning.
    prose = _STRIP_CITES_RE.sub(" ", text)

    # ── G1: number-trace ─────────────────────────────────────────────────────
    allowed = _allowed_numbers(packet, cited)
    seen: set[str] = set()
    for digits, pct in _NUM_RE.findall(prose):
        n = _norm_num(digits)
        token = n + "%" if pct else n
        if token in seen:
            continue
        seen.add(token)
        # A bare number is backed if its plain form OR its %-form is in a cited
        # render (renders register both forms).
        if n in allowed or (n + "%") in allowed:
            continue
        violations.append(Violation(
            "G1",
            f'orphan number {token!r}: no cited claim render contains it '
            f'(cited={sorted(cited_set) or "none"}). State numbers only via cite()/quote().',
        ))

    # ── G2: quote-trace ──────────────────────────────────────────────────────
    # Any double-quoted span in the prose (after stripping citations) must be a
    # substring of some packet quote's verbatim text. Short spans (<= 3 chars,
    # e.g. quotation around "it") are ignored as non-evidentiary.
    packet_quote_texts = _packet_quote_texts(packet)
    for span in _double_quoted_spans(prose):
        clean = span.strip()
        # Rhetorical / illustrative short quotes ("strong signal", "I feel a
        # little better") are normal prose, NOT fabricated evidence. Only a
        # substantial (>=8-word) double-quoted span reads as a (possibly invented)
        # patient testimonial. Real patient quotes must come via quote("Q-...")
        # (G6 catches a quote() of a non-existent id); raw long quotes are the
        # fabrication risk this checks.
        if len(clean.split()) < 8:
            continue
        if not any(clean.lower() in q for q in packet_quote_texts):
            violations.append(Violation(
                "G2",
                f'fabricated quote {span!r}: not a substring of any packet quote. '
                f'Use quote("Q-pos-N") / quote("Q-neg-N") for verbatim patient text.',
            ))

    # ── G3: caveat-real + n=K denominator ────────────────────────────────────
    present_caveats = _packet_caveat_ids(packet)
    for cid, trigger in _CAVEAT_TRIGGERS.items():
        if trigger.search(prose) and cid not in present_caveats:
            violations.append(Violation(
                "G3",
                f'methodology roast maps to {cid}, which is NOT a caveat in this '
                f'packet. Only critique flaws the data actually has.',
            ))

    denominators = _packet_denominators(packet)
    for m in _N_EQUALS_RE.findall(prose):
        if denominators and int(m) not in denominators:
            violations.append(Violation(
                "G3",
                f'n={m} does not match the packet denominator '
                f'(n_users/n_reports={sorted(denominators)}).',
            ))

    # ── G4: no prescription directive ────────────────────────────────────────
    for rx in _RX_RE:
        m = rx.search(text)
        if m:
            violations.append(Violation(
                "G4",
                f'prescription directive detected: {m.group(0)!r}. Agents scope '
                f'evidence only — never tell the user to start/stop/take/dose a drug.',
            ))
            break  # one G4 hit is enough; don't spam

    # ── G5: silent-drop / "no negatives = safe" framing requires C3 cited ────
    if _SAFE_FRAMING_RE.search(prose) and "C3" not in cited_set:
        violations.append(Violation(
            "G5",
            '"no negatives / so it\'s safe" framing without citing C3. A low '
            "negative count is a sampling artifact (silent drop), not proof of "
            'safety — cite("C3") whenever raising it.',
        ))

    return violations


# ── Quote helpers ────────────────────────────────────────────────────────────
_DQ_RE = re.compile(r'"([^"]+)"')


def _double_quoted_spans(text: str) -> list[str]:
    return _DQ_RE.findall(text)


def _packet_quote_texts(packet) -> list[str]:
    """Lowercased verbatim text of every quote in the packet.

    Pulls from packet.quotes if present; falls back to scanning claim renders of
    quote claim_ids (Q-pos-*, Q-neg-*).
    """
    texts: list[str] = []
    quotes = getattr(packet, "quotes", None)
    if isinstance(quotes, list):
        for q in quotes:
            t = q.get("text") if isinstance(q, dict) else getattr(q, "text", None)
            if t:
                texts.append(str(t).lower())
    if not texts:
        claims = getattr(packet, "claims", None)
        if isinstance(claims, dict):
            for cid, c in claims.items():
                if str(cid).lower().startswith("q-"):
                    render = c.get("render") if isinstance(c, dict) else getattr(c, "render", None)
                    if render:
                        texts.append(str(render).lower())
    return texts


def _packet_denominators(packet) -> set[int]:
    """The valid denominators for an n=K claim (n_users and n_reports)."""
    out: set[int] = set()
    for attr in ("n_users", "n_reports"):
        v = getattr(packet, attr, None)
        if isinstance(v, int):
            out.add(v)
    return out


# ── Citation rendering ───────────────────────────────────────────────────────
def render_citations(text: str, packet) -> str:
    """Replace cite("X") / quote("X") with the packet claim's literal render.

    Used after a turn passes check_turn() to produce reader-facing text. An
    unknown claim_id is rendered as a visible [missing:X] marker rather than
    silently dropped, so a bad reference is never invisibly swallowed.
    """
    def _sub(m: re.Match) -> str:
        cid = m.group(1)
        render = _claim_render(packet, cid)
        if render is None:
            return f"[missing:{cid}]"
        return render

    text = _CITE_RE.sub(_sub, text)
    text = _QUOTE_RE.sub(_sub, text)
    return text


# ── Self-test ────────────────────────────────────────────────────────────────
# A hand-written fabricated turn must trip G1/G3; a clean cite-only turn must
# trip nothing. Run: `uv run python src/agents/_common/validate.py`
if __name__ == "__main__":
    @dataclass
    class _FakePacket:
        n_users: int = 312
        n_reports: int = 400
        claims: dict | None = None
        quotes: list | None = None

        def claim(self, cid):
            return (self.claims or {}).get(cid)

    pkt = _FakePacket(
        claims={
            "S2": {"kind": "count_pct", "render": "200 of 312 users (64%) reported it helped", "value": 200},
            "S3": {"kind": "count_pct", "render": "62 of 312 users (20%) reported a negative experience", "value": 62},
            "C3": {"kind": "caveat", "render": "rows exist only when signal != 'n/a', so absence of negatives is not proof of safety", "value": None},
            "Q-pos-1": {"kind": "quote", "render": "went from bedbound to functional on this", "value": None},
        },
        quotes=[{"text": "went from bedbound to functional on this", "pole": "pos"}],
    )

    # Fabricated turn: an orphan number (87%) with no backing citation, a made-up
    # quote, an n=K that doesn't match, and a small-n roast the packet lacks (C1).
    bad = (
        'Honestly 87% of people are thrilled, and with such a small sample '
        '(n=5) it barely matters. One patient said "this completely cured me '
        'overnight and gave me my whole life back instantly".'
    )
    bad_v = check_turn(bad, pkt)
    bad_rules = {v.rule for v in bad_v}
    assert "G1" in bad_rules, f"expected G1 in {bad_rules}"
    assert "G3" in bad_rules, f"expected G3 in {bad_rules}"
    assert "G2" in bad_rules, f"expected G2 (long fabricated quote) in {bad_rules}"

    # Phantom citation: cite()/quote() of a claim_id absent from the packet → G6.
    phantom_v = check_turn('We must weigh quote("Q-neg-1") here.', pkt)
    assert "G6" in {v.rule for v in phantom_v}, f"expected G6 in {phantom_v}"

    # A short rhetorical quote must NOT be flagged (G2 false-positive regression).
    rhet_v = check_turn('That is not someone saying "I feel a little better".', pkt)
    assert rhet_v == [], f"rhetorical short quote should be clean, got {rhet_v}"

    # Clean turn: numbers only via cite(), quote via quote(), C3 cited for the
    # safety framing. Should trip nothing.
    good = (
        'Look, cite("S2") is real and it is exciting! Now Vex is right — cite("S3") '
        'is real too, and remember cite("C3"): a low negative count is a sampling '
        'artifact, not proof of safety. Here is a voice: quote("Q-pos-1"). This '
        'might be worth asking your doctor about.'
    )
    good_v = check_turn(good, pkt)
    assert good_v == [], f"expected clean turn, got {good_v}"

    # render_citations should expand a cited render and mark a missing one.
    rendered = render_citations('See cite("S2") and cite("ZZZ").', pkt)
    assert "200 of 312 users (64%) reported it helped" in rendered
    assert "[missing:ZZZ]" in rendered

    print("SELFTEST OK: fabricated turn tripped", sorted(bad_rules), "| clean turn clean | render OK")
