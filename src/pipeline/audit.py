"""Read-only, subscription-backed audit of persisted pipeline decisions."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from string import Formatter
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "src" / "audit_prompts"
MODEL_CLAUDE = "claude-opus-5-5"
MODEL_CODEX = "gpt-6-astra"
CODEX_MODELS = frozenset({"gpt-6-astra", "gpt-6.1-sol"})
_WORDS = re.compile(r"\b[\w]+\b")
_LOG = logging.getLogger(__name__)


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    post_id: str
    report: str
    parent: str = ""
    treatment: str
    aliases: list[str] = Field(default_factory=list)
    excluded_compounds: list[str] = Field(default_factory=list)
    subreddit: str | None = None


class SentimentValue(BaseModel):
    kind: Literal["sentiment"] = "sentiment"
    sentiment: str
    signal_strength: str
    side_effects: list[str]


class DoseValue(BaseModel):
    kind: Literal["dose"] = "dose"
    low: float | None = None
    high: float | None = None
    unit: str | None = None
    route: str | None = None
    outcome: str | None = None
    quote: str | None = None


class EffectValue(BaseModel):
    kind: Literal["effect"] = "effect"
    domain: str
    symptom: str
    direction: str
    severity: str | None = None
    attribution: str
    quote: str
    dose_id: int | None = None
    linked_dose: DoseValue | None = None


class NoRowValue(BaseModel):
    kind: Literal["no_dose", "no_effect"]


DecisionValue = SentimentValue | DoseValue | EffectValue | NoRowValue


class AuditTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    report_id: int
    run_id: int
    record_id: int | None
    source: Source
    value: DecisionValue = Field(discriminator="kind")


IssueCode = Literal[
    "none", "wrong_compound", "not_self_use", "unsupported_quote", "wrong_dose",
    "wrong_route", "wrong_effect", "wrong_sentiment", "missing_extraction",
    "insufficient_context", "other",
]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judgment: Literal["supported", "unsupported", "unclear"]
    issue_code: IssueCode
    evidence_quote: str | None = None
    rationale: str = Field(min_length=8, max_length=1200)

    @model_validator(mode="after")
    def check_code(self) -> Verdict:
        if self.judgment == "supported" and self.issue_code != "none":
            raise ValueError("supported verdict must use issue_code=none")
        if self.judgment == "unsupported" and self.issue_code in {"none", "insufficient_context"}:
            raise ValueError("unsupported verdict needs a specific issue_code")
        if self.judgment == "unclear" and self.issue_code != "insufficient_context":
            raise ValueError("unclear verdict must use insufficient_context")
        return self


class JudgeRound(BaseModel):
    round_number: int
    opus: Verdict | None = None
    codex: Verdict | None = None
    errors: list[str] = Field(default_factory=list)


class AuditResult(BaseModel):
    task: AuditTask
    status: Literal["supported", "flagged", "unresolved"]
    rounds: list[JudgeRound]
    judge_models: dict[str, str]
    prompt_sha256: dict[str, str]
    completed_at: str


class AuditCounts(BaseModel):
    supported: int = 0
    flagged: int = 0
    unresolved: int = 0
    skipped: int = 0


class Judge(Protocol):
    def review(self, prompt: str) -> Verdict: ...


class JudgeUnavailableError(RuntimeError):
    """A CLI or subscription failure should pause the run, not mislabel every decision."""


def _source_quote_valid(quote: str | None, report: str) -> bool:
    if quote is None:
        return True
    quote = " ".join(quote.split())
    report = " ".join(report.split())
    return len(_WORDS.findall(quote)) >= 3 and quote.casefold() in report.casefold()


def _verify_verdict(verdict: Verdict, task: AuditTask) -> Verdict:
    if not _source_quote_valid(verdict.evidence_quote, task.source.report):
        raise ValueError("evidence_quote is too short or absent from the author's report")
    if (verdict.judgment in {"supported", "unsupported"}
            and not isinstance(task.value, NoRowValue)
            and verdict.evidence_quote is None):
        raise ValueError("row verdict requires an exact evidence_quote")
    if verdict.judgment == "unsupported" and verdict.evidence_quote is None:
        raise ValueError("unsupported verdict requires an exact evidence_quote")
    return verdict


def _render_prompt(name: str, task: AuditTask, previous: list[JudgeRound]) -> str:
    template = (PROMPTS / name).read_text(encoding="utf-8")
    expected = {"task"} if not previous else {"task", "verdicts"}
    fields = {field for _, field, _, _ in Formatter().parse(template) if field}
    if fields != expected:
        raise ValueError(f"{name} template fields {fields} do not match {expected}")
    values = {"task": task.model_dump_json(indent=2)}
    if previous:
        values["verdicts"] = json.dumps([round_.model_dump() for round_ in previous], indent=2)
    return template.format(**values)


def prompt_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((PROMPTS / name).read_bytes()).hexdigest()
            for name in ("initial.txt", "discussion.txt")}


def _subscription_environment() -> dict[str, str]:
    """Never pass pay-as-you-go credentials or provider overrides to either CLI."""
    blocked = (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    )
    return {key: value for key, value in os.environ.items() if key not in blocked}


class CliJudge:
    """One fresh, tool-restricted CLI session for each independent verdict."""

    def __init__(self, backend: Literal["opus", "codex"], model: str, timeout: int = 240):
        self.backend = backend
        self.model = model
        self.timeout = timeout

    def review(self, prompt: str) -> Verdict:
        schema = Verdict.model_json_schema()
        schema["required"] = list(schema["properties"])
        with tempfile.TemporaryDirectory(prefix="patientpunk-audit-") as directory:
            work = Path(directory)
            if self.backend == "opus":
                command = [
                    "claude", "--bare", "-p", "--model", self.model,
                    "--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*",
                    "--no-session-persistence", "--output-format", "json",
                    "--json-schema", json.dumps(schema),
                ]
            else:
                schema_path = work / "schema.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                command = [
                    "codex", "exec", "--model", self.model, "--sandbox", "read-only",
                    "--skip-git-repo-check", "--ephemeral", "--output-schema", str(schema_path), "-",
                ]
            try:
                completed = subprocess.run(
                    command, input=prompt, text=True, capture_output=True, cwd=work,
                    env=_subscription_environment(), timeout=self.timeout, check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise JudgeUnavailableError(f"{self.backend} CLI unavailable or timed out") from exc
        if completed.returncode:
            if self.backend == "opus":
                try:
                    message = str(json.loads(completed.stdout).get("result", "")).casefold()
                except (ValueError, AttributeError):
                    message = ""
                if "oauth session expired" in message or "not logged in" in message:
                    raise JudgeUnavailableError("Claude subscription session expired; run claude auth login")
            raise JudgeUnavailableError(f"{self.backend} CLI failed (exit {completed.returncode}); "
                                        "check subscription access and model availability")
        payload = json.loads(completed.stdout)
        if self.backend == "opus":
            payload = payload.get("structured_output") or json.loads(payload["result"])
        return Verdict.model_validate(payload)


def preflight() -> None:
    """Fail closed unless both local CLIs are using saved subscription logins."""
    env = _subscription_environment()
    checks = (("claude", ["claude", "auth", "status"]),
              ("codex", ["codex", "login", "status"]))
    for name, command in checks:
        try:
            result = subprocess.run(command, capture_output=True, text=True, env=env,
                                    timeout=30, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"{name} CLI unavailable: {exc}") from exc
        if result.returncode:
            raise RuntimeError(f"{name} is not logged in; authenticate its subscription CLI first")
        if name == "claude":
            method = json.loads(result.stdout).get("authMethod")
            if method != "claude.ai":
                raise RuntimeError("Claude auth is not claude.ai subscription login")
        elif "Logged in using ChatGPT" not in result.stdout + result.stderr:
            raise RuntimeError("Codex auth is not a ChatGPT subscription login")


def _task(report_id: int, run_id: int, record_id: int | None,
          source: Source, value: DecisionValue) -> AuditTask:
    stable = json.dumps([report_id, run_id, record_id, source.model_dump(),
                         value.model_dump()], sort_keys=True, ensure_ascii=False)
    return AuditTask(decision_id=hashlib.sha256(stable.encode()).hexdigest(),
                     report_id=report_id, run_id=run_id, record_id=record_id,
                     source=source, value=value)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def load_tasks(db_path: Path, drug: str | None = None,
               kinds: set[str] | None = None) -> list[AuditTask]:
    """Load every persisted latest decision, including processed reports with zero rows."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        query = """
            SELECT tr.report_id, tr.run_id, tr.post_id, tr.user_id, tr.sentiment,
                   tr.signal_strength, tr.side_effects, t.canonical_name, t.aliases,
                   p.title, p.body_text, p.parent_id, pp.title, pp.body_text, pp.parent_id,
                   u.source_subreddit
            FROM treatment_reports tr JOIN treatment t ON t.id=tr.drug_id
            JOIN extraction_runs sentiment_run ON sentiment_run.run_id=tr.run_id
            JOIN posts p ON p.post_id=tr.post_id
            LEFT JOIN posts pp ON pp.post_id=p.parent_id
            LEFT JOIN users u ON u.user_id=p.user_id
            WHERE sentiment_run.finished_at IS NOT NULL
              AND tr.report_id=(SELECT MAX(tr2.report_id) FROM treatment_reports tr2
                JOIN extraction_runs er2 ON er2.run_id=tr2.run_id
                WHERE tr2.post_id=tr.post_id AND tr2.drug_id=tr.drug_id
                AND er2.finished_at IS NOT NULL)
        """
        params: tuple[str, ...] = ()
        if drug:
            query += " AND lower(t.canonical_name)=lower(?)"
            params = (drug,)
        query += " ORDER BY tr.report_id"
        tasks: list[AuditTask] = []
        has_runs = _table_exists(conn, "report_runs")
        for row in conn.execute(query, params):
            (report_id, sentiment_run, post_id, user_id, sentiment, strength, effects,
             treatment, aliases, title, body, parent_id, parent_title, parent_body,
             parent_parent, subreddit) = row
            report = f"{title or ''} {body or ''}".strip() if parent_id is None else body or ""
            parent = (f"{parent_title or ''} {parent_body or ''}".strip()
                      if parent_parent is None else parent_body or "")
            run_config_row = conn.execute("SELECT config FROM extraction_runs WHERE run_id=?",
                                          (sentiment_run,)).fetchone()
            run_config = json.loads(run_config_row[0] or "{}") if run_config_row else {}
            excluded = run_config.get("drug_excluded_compounds")
            if excluded is None:
                excluded = (run_config.get("drug_excluded_aliases") or [])[:1]
            source = Source(post_id=post_id, report=report[:8000], parent=parent[:1500],
                            treatment=treatment, aliases=json.loads(aliases or "[]"),
                            excluded_compounds=excluded, subreddit=subreddit)
            value: DecisionValue
            if kinds is None or "sentiment" in kinds:
                value = SentimentValue(sentiment=sentiment, signal_strength=strength,
                                       side_effects=json.loads(effects or "[]"))
                tasks.append(_task(report_id, sentiment_run, report_id, source, value))
            if not has_runs:
                continue
            for kind, table, key in (("dose", "report_doses", "dose_id"),
                                     ("effect", "report_effects", "effect_id")):
                if kinds is not None and kind not in kinds or not _table_exists(conn, table):
                    continue
                latest = conn.execute("""
                    SELECT MAX(rr.run_id) FROM report_runs rr JOIN extraction_runs er
                    ON er.run_id=rr.run_id WHERE rr.report_id=? AND er.extraction_type=?
                    AND er.finished_at IS NOT NULL
                """, (report_id, "report_doses" if kind == "dose" else "report_effects")).fetchone()[0]
                if latest is None:
                    continue
                conn.row_factory = sqlite3.Row
                records = conn.execute(f"SELECT * FROM {table} WHERE report_id=? AND run_id=? ORDER BY ordinal",
                                       (report_id, latest)).fetchall()
                conn.row_factory = None
                for record in records:
                    if kind == "dose":
                        value = DoseValue(**{k: record[k] for k in
                                             ("low", "high", "unit", "route", "outcome", "quote")})
                    else:
                        linked = None
                        if record["dose_id"] is not None:
                            dose_row = conn.execute("SELECT low, high, unit, route, outcome, quote "
                                                    "FROM report_doses WHERE dose_id=? AND report_id=?",
                                                    (record["dose_id"], report_id)).fetchone()
                            if dose_row:
                                linked = DoseValue(**dict(zip(("low", "high", "unit", "route",
                                                              "outcome", "quote"), dose_row)))
                        value = EffectValue(**{k: record[k] for k in
                                               ("domain", "symptom", "direction", "severity",
                                                "attribution", "quote", "dose_id")}, linked_dose=linked)
                    tasks.append(_task(report_id, latest, record[key], source, value))
                if not records:
                    tasks.append(_task(report_id, latest, None, source,
                                       NoRowValue(kind="no_dose" if kind == "dose" else "no_effect")))
        return tasks
    finally:
        conn.close()


def _agreed(first: Verdict, second: Verdict) -> bool:
    if first.judgment != second.judgment or first.issue_code != second.issue_code:
        return False
    if first.judgment == "unsupported":
        left = " ".join((first.evidence_quote or "").casefold().split())
        right = " ".join((second.evidence_quote or "").casefold().split())
        return left == right
    return True


def adjudicate(task: AuditTask, opus: Judge, codex: Judge,
               max_rounds: int = 10) -> AuditResult:
    """Independent first pass; exchange prior verdicts only after disagreement."""
    if not 1 <= max_rounds <= 10:
        raise ValueError("max_rounds must be between 1 and 10")
    rounds: list[JudgeRound] = []
    for number in range(1, max_rounds + 1):
        prompt = _render_prompt("initial.txt" if number == 1 else "discussion.txt",
                                task, rounds)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {"opus": pool.submit(opus.review, prompt),
                       "codex": pool.submit(codex.review, prompt)}
            results: dict[str, Verdict] = {}
            errors: list[str] = []
            for name, future in futures.items():
                try:
                    results[name] = _verify_verdict(future.result(), task)
                except (ValueError, json.JSONDecodeError) as exc:
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
        round_ = JudgeRound(round_number=number, opus=results.get("opus"),
                            codex=results.get("codex"), errors=errors)
        rounds.append(round_)
        if errors:
            break
        if _agreed(results["opus"], results["codex"]):
            break
    last = rounds[-1]
    status: Literal["supported", "flagged", "unresolved"]
    if last.opus and last.codex and _agreed(last.opus, last.codex):
        if last.opus.judgment == "supported":
            status = "supported"
        elif last.opus.judgment == "unsupported":
            status = "flagged"
        else:
            status = "unresolved"
    else:
        status = "unresolved"
    return AuditResult(task=task, status=status, rounds=rounds,
                       judge_models={"opus": MODEL_CLAUDE, "codex": MODEL_CODEX},
                       prompt_sha256=prompt_hashes(),
                       completed_at=datetime.now(timezone.utc).isoformat())


def run_audit(source_db: Path, output_db: Path, drug: str | None = None,
              kinds: set[str] | None = None, limit: int = 0,
              max_rounds: int = 10, opus: Judge | None = None,
              codex: Judge | None = None, check_auth: bool = True,
              codex_model: str = MODEL_CODEX) -> AuditCounts:
    """Resume by decision ID and persist each verdict immediately outside the repo."""
    if output_db.resolve().is_relative_to(ROOT):
        raise ValueError("Audit output database must live outside the repository")
    if source_db.resolve() == output_db.resolve():
        raise ValueError("Audit output database must differ from source database")
    if codex_model not in CODEX_MODELS:
        raise ValueError(f"codex_model must be one of {sorted(CODEX_MODELS)}")
    if not 1 <= max_rounds <= 10:
        raise ValueError("max_rounds must be between 1 and 10")
    if check_auth:
        preflight()
    tasks = load_tasks(source_db, drug=drug, kinds=kinds)
    opus = opus or CliJudge("opus", MODEL_CLAUDE)
    codex = codex or CliJudge("codex", codex_model)
    output_db.parent.mkdir(parents=True, exist_ok=True)
    counts = {"supported": 0, "flagged": 0, "unresolved": 0, "skipped": 0}
    with sqlite3.connect(output_db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_results (
            decision_id TEXT PRIMARY KEY, source_db TEXT NOT NULL,
            status TEXT NOT NULL, result_json TEXT NOT NULL, completed_at TEXT NOT NULL
        )""")
        for task in tasks:
            old = conn.execute("SELECT result_json FROM audit_results WHERE decision_id=?",
                               (task.decision_id,)).fetchone()
            if old:
                AuditResult.model_validate_json(old[0])
                counts["skipped"] += 1
                continue
            if limit and sum(counts[key] for key in ("supported", "flagged", "unresolved")) >= limit:
                break
            started = time.monotonic()
            result = adjudicate(task, opus, codex, max_rounds=max_rounds)
            result.judge_models["codex"] = codex_model
            conn.execute("INSERT INTO audit_results VALUES (?, ?, ?, ?, ?)",
                         (task.decision_id, source_db.name, result.status,
                          result.model_dump_json(), result.completed_at))
            conn.commit()
            counts[result.status] += 1
            _LOG.info(json.dumps({"phase": "audit", "run_id": output_db.stem,
                                  "schema_id": "audit_result_v1", "status": result.status,
                                  "decision_id": task.decision_id, "rounds": len(result.rounds),
                                  "duration": round(time.monotonic() - started, 3)}))
    return AuditCounts.model_validate(counts)
