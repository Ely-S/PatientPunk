"""TheTrialAgent manifest — plain metadata (dr-hiro manifest shape)."""

AGENT_NAME = "TheTrialAgent"
ROLE = "orchestrator"
DESCRIPTION = (
    "The arena for The Trial: parse the drug query, build the deterministic "
    "evidence packet, run the Hooper vs. Dr. Vex debate over it, and synthesize "
    "a grounded patient-facing briefing."
)
DEPENDS_ON = ["HooperAgent", "DrVexAgent"]
