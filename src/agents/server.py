"""server.py — a tiny stdlib HTTP server exposing "The Trial" to a browser.

Modeled directly on Rūmī's ``poet_server.py``: a ``ThreadingHTTPServer`` +
``BaseHTTPRequestHandler``, a ``JOBS`` dict guarded by ``JOBS_LOCK``, and a
single ``RUN_LOCK`` that SERIALIZES trial runs (the Rumi debate driver is not
concurrency-safe — only one debate at a time). Each POST /trial spawns a daemon
thread and returns ``{job_id}``; the browser polls GET /poll?job_id until the
job is ``done``. Stdlib ONLY — no flask/fastapi.

The worker pushes the deterministic evidence packet FIRST (instant), then
appends each debate turn live via an ``on_turn`` callback (the UI watches it
unfold), then sets the synthesized briefing. Every turn is rendered through
``render_citations`` and tagged with its ``check_turn`` violations before it is
stored, so the UI shows real numbers/quotes and the gate verdict.

Run (PYTHONPATH=src so the bare ``agents.*`` imports resolve)::

    PYTHONPATH=src uv run python -m agents.server --db data/posts.db --port 8770

Read-only on the posts DB. NEVER imports ``patientpunk`` / ``variable_extraction``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from agents.packet import build_packet
from agents.synthesize import synthesize
from agents.validate import check_turn, render_citations
from agents.world import run_debate, _parse_drug_query

# ---------------------------------------------------------------------------
# Job state. One trial at a time (the Rumi debate driver is not concurrency-safe).
# ---------------------------------------------------------------------------
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()  # guards the JOBS dict
RUN_LOCK = threading.Lock()   # serializes run_debate() / trial runs

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(HERE, "trial.html")

# Defaults; main() may override DB_PATH / HOST / PORT from argv + env.
DB_PATH = "data/posts.db"
HOST = "127.0.0.1"
# Port: default 8770, override via --port or env TRIAL_PORT (NOT poet's 8765).
PORT = int(os.environ.get("TRIAL_PORT", "8770") or "8770")


def _new_job() -> dict:
    """A fresh job in its initial (pre-work) state — matches the poll contract."""
    return {
        "done": False,
        "stage": "resolving",
        "error": None,
        "packet": None,
        "turns": [],
        "briefing": None,
    }


def _serialize_packet(packet) -> dict:
    """dataclasses.asdict the packet, then FLATTEN .claims to {cid: render}.

    The frontend reads ``packet.claims`` as a flat cid->render string map (for
    the evidence chips). ``provenance`` is trimmed to {run_id, commit_hash} per
    the pinned contract; the full structured claim values are dropped on purpose
    (the renders carry everything the UI needs).
    """
    d = dataclasses.asdict(packet)
    claims = d.get("claims") or {}
    flat: dict[str, str] = {}
    for cid, c in claims.items():
        if isinstance(c, dict):
            flat[cid] = str(c.get("render", "") or "")
        else:
            flat[cid] = str(c)
    d["claims"] = flat
    prov = d.get("provenance") or {}
    d["provenance"] = {
        "run_id": prov.get("run_id"),
        "commit_hash": prov.get("commit_hash"),
    }
    return d


def _not_found_briefing(packet) -> dict:
    """Mirror run_trial's not-found branch: an honest, empty-handed briefing."""
    return {
        "found": False,
        "drug_query": packet.drug_query,
        "drug": packet.drug,
        "text": (
            f"No patient reports for {packet.drug_query!r} in our corpus. "
            "There is nothing to put on trial — we cannot say anything "
            "about it from this data. "
            "This is anecdotal patient data, not medical advice — please "
            "discuss with your doctor."
        ),
    }


def _run_trial_job(job_id: str, prompt: str, rounds: int) -> None:
    """Background worker: resolve -> packet -> (short-circuit | debate -> synth).

    Pushes the packet first (instant, deterministic), then streams each debate
    turn live (rendered + violations-tagged), then the briefing. Never raises —
    any failure lands in job["error"] with stage "error", and done is always set.
    """
    job = JOBS[job_id]

    with RUN_LOCK:
        try:
            # ── resolve the drug query ──────────────────────────────────────
            with JOBS_LOCK:
                job["stage"] = "resolving"
            drug = _parse_drug_query(prompt)

            # ── build the deterministic evidence packet (push it FIRST) ─────
            packet = build_packet(drug, DB_PATH)
            with JOBS_LOCK:
                job["packet"] = _serialize_packet(packet)
                job["stage"] = "packet"

            # ── short-circuit: no reports -> no debate, honest briefing ─────
            if not packet.found:
                with JOBS_LOCK:
                    job["briefing"] = _not_found_briefing(packet)
                    job["stage"] = "done"
                    job["done"] = True
                return

            # ── the debate: stream each turn live via on_turn ───────────────
            with JOBS_LOCK:
                job["stage"] = "debating"

            def _push(turn: dict) -> None:
                # Render cites/quotes to literal packet text, tag gate violations.
                try:
                    rendered = render_citations(turn["text"], packet)
                except Exception:
                    rendered = turn.get("text", "")
                try:
                    viols = [v.rule for v in check_turn(turn["text"], packet)]
                except Exception:
                    viols = []
                with JOBS_LOCK:
                    job["turns"].append(
                        {
                            "agent": turn["agent"],
                            "text": rendered,
                            "violations": viols,
                        }
                    )

            transcript = run_debate(packet, rounds=rounds, on_turn=_push)

            # ── synthesize the verdict briefing ─────────────────────────────
            with JOBS_LOCK:
                job["stage"] = "synthesizing"
            briefing = synthesize(packet, transcript)
            # The packet object isn't JSON-safe; drop it from the wire briefing.
            briefing = {
                k: v for k, v in briefing.items() if k not in ("packet", "transcript")
            }
            with JOBS_LOCK:
                job["briefing"] = briefing
                job["stage"] = "done"
                job["done"] = True
        except Exception as e:  # noqa: BLE001 — never crash the server
            with JOBS_LOCK:
                job["error"] = f"{type(e).__name__}: {e}"
                job["stage"] = "error"
                job["done"] = True


class Handler(BaseHTTPRequestHandler):
    # --- helpers -----------------------------------------------------------
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # quieter console
        pass

    # --- routes ------------------------------------------------------------
    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                try:
                    with open(HTML_PATH, "r", encoding="utf-8") as f:
                        html = f.read()
                except FileNotFoundError:
                    self._send_html(
                        404,
                        b"<h1>trial.html not found</h1>"
                        b"<p>Expected a sibling file next to server.py.</p>",
                    )
                    return
                self._send_html(200, html.encode("utf-8"))
                return

            if parsed.path == "/poll":
                qs = parse_qs(parsed.query)
                job_id = (qs.get("job_id") or [""])[0]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    snapshot = dict(job) if job is not None else None
                if snapshot is None:
                    self._send_json(404, {"error": "unknown job_id"})
                    return
                self._send_json(200, snapshot)
                return

            self._send_json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001 — never crash the server
            try:
                self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
            except Exception:
                pass

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/trial":
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {}
            prompt = (data.get("prompt") or "").strip()
            if not prompt:
                self._send_json(400, {"error": "missing 'prompt'"})
                return
            try:
                rounds = int(data.get("rounds", 2))
            except (TypeError, ValueError):
                rounds = 2
            if rounds < 1:
                rounds = 1

            job_id = uuid.uuid4().hex
            with JOBS_LOCK:
                JOBS[job_id] = _new_job()

            t = threading.Thread(
                target=_run_trial_job, args=(job_id, prompt, rounds), daemon=True
            )
            t.start()

            self._send_json(200, {"job_id": job_id})
        except Exception as e:  # noqa: BLE001 — never crash the server
            try:
                self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    global DB_PATH, HOST, PORT
    parser = argparse.ArgumentParser(
        prog="agents.server",
        description="Serve 'The Trial' web UI (stdlib http.server).",
    )
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help="Path to the read-only SQLite posts DB (default: data/posts.db).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help="Port to listen on (default: 8770, or env TRIAL_PORT).",
    )
    parser.add_argument(
        "--host",
        default=HOST,
        help="Host/interface to bind (default: 127.0.0.1).",
    )
    args = parser.parse_args(argv)

    DB_PATH = args.db
    HOST = args.host
    PORT = args.port

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"The Trial ready -> http://{HOST}:{PORT}  (db: {DB_PATH})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
