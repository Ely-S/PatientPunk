#!/usr/bin/env python3
"""Launch a model-server job on Dispersed (render network) and print the endpoint
to point PatientPunk extraction at.

Dispersed runs Docker jobs (no command override), so we run the **Ollama** image
(its default entrypoint serves an OpenAI-compatible API) as a PERSISTENT job,
then pull the model via Ollama's HTTP API. The job's `node_urls` give the
hostname/port to reach it; the OpenAI-compatible endpoint is `<host>:<port>/v1`.

Then run extraction (from your laptop, or on-box) with:
    LLM_PROVIDER=openai
    LLM_BASE_URL=http://<host>:<port>/v1
    LLM_API_KEY=EMPTY
    MODEL_FAST=<model>   MODEL_STRONG=<model>

Auth: Dispersed signs each request (HMAC-SHA256 over
`publicKey|timestamp|nonce|METHOD|pathname|queryString|bodySha256`). Set
DISPERSED_PUBLIC_KEY (pk_...) and DISPERSED_SECRET_KEY (sk_...) in the env.
If you get 401, verify the canonical-string format against Dispersed's TypeScript
SDK / docs (signing schemes are finicky) -- the SDK/MCP server are the
authoritative auth path if this differs.

Usage:
    export DISPERSED_PUBLIC_KEY=pk_...  DISPERSED_SECRET_KEY=sk_...
    python dispersed/launch_job.py --model qwen2.5:32b --gpu-name "NVIDIA RTX 4090" \
        --allowed-ip <your.public.ip>/32 --pull
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API = "https://api.dispersed.com"


# --- HTTP / auth --------------------------------------------------------------

def _nonce() -> str:
    return os.urandom(16).hex()  # 16 bytes -> 32 hex chars


def _signed_request(method: str, path: str, body: dict | None = None,
                    *, pk: str, sk: str, query: str = "") -> dict:
    # Must match the SDK's `JSON.stringify(canonicalJson(body))`: canonicalJson
    # recursively sorts object keys, then stringify emits compact JSON. So:
    # sort_keys=True (recursive), compact separators, ensure_ascii=False (JS does
    # not \u-escape). The server recomputes bodySha256 the same way, so we both
    # sign+send these exact canonical bytes.
    body_bytes = (json.dumps(body, separators=(",", ":"), sort_keys=True,
                             ensure_ascii=False).encode("utf-8")
                  if body is not None else b"")
    body_sha = hashlib.sha256(body_bytes).hexdigest()
    ts = str(int(time.time() * 1000))
    nonce = _nonce()
    canonical = f"{pk}|{ts}|{nonce}|{method}|{path}|{query}|{body_sha}"
    sig = hmac.new(sk.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-API-Key": pk,
        "X-Time": ts,
        "X-Nonce": nonce,
        "X-Signature": sig,
        "Content-Type": "application/json",
    }
    url = API + path + (("?" + query) if query else "")
    req = Request(url, data=body_bytes if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except HTTPError as e:
        detail = e.read().decode(errors="ignore")
        sys.exit(f"HTTP {e.code} on {method} {path}: {detail}\n"
                 f"  (if 401: verify the signing canonical string against Dispersed's SDK/docs)")
    except (URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        sys.exit(f"Could not reach the Dispersed API at {url}: {reason}\n"
                 f"  (check network / DNS / the API host, or that the job's port is open)")


def _as_list(resp) -> list:
    """Dispersed list endpoints return either `{"data": [...]}` or a bare list.

    Always returns a list -- an unexpected scalar/None response yields [] rather
    than propagating a non-iterable to callers that len()/iterate over it.
    """
    if isinstance(resp, dict):
        data = resp.get("data")
        return data if isinstance(data, list) else []
    return resp if isinstance(resp, list) else []


# --- launch helpers -----------------------------------------------------------

def _detect_public_ip() -> str:
    """Return `<public-ip>/32`, or exit asking the caller to pass --allowed-ip."""
    try:
        with urlopen("https://api.ipify.org", timeout=10) as r:
            return r.read().decode().strip() + "/32"
    except Exception:
        sys.exit("Could not detect public IP; pass --allowed-ip <cidr> explicitly.")


def _build_job_body(args, allowed_ip: str) -> dict:
    """Assemble the PERSISTENT-job request body from parsed CLI args."""
    env: dict = {}
    if "ollama" in args.image.lower():
        # Ollama must bind all interfaces to be reachable via node_urls.
        env["OLLAMA_HOST"] = f"0.0.0.0:{args.port}"
    docker_params: dict = {
        "image": args.image,
        "tag": "latest",
        "ports": [args.port],
        "allowed_ips": [allowed_ip],
        "env": env,
    }
    body: dict = {
        "task": "PERSISTENT",   # long-running query-responsive server
        "title": args.title,
        "gpu_count": args.gpu_count,
        "min_vram_gb": args.min_vram_gb,
        "parameters": {"type": "docker", "parameters": docker_params},
    }
    if args.gpu_name:
        body["gpu_name"] = args.gpu_name
    return body


def _poll_for_node(uuid: str, port: int, deadline: float, *, pk: str, sk: str) -> dict | None:
    """Poll job-runs until one for `uuid` exposes node_urls; return the matching entry.

    node_urls lives on the job-RUN, not the job object. Each url's `port` is the
    EXTERNAL proxy port; its `description` is the container port (str) we asked
    for, so match on that to pick the right mapping. Returns None on timeout.
    """
    while time.time() < deadline:
        time.sleep(10)
        runs = _signed_request("GET", "/v1/job-runs", pk=pk, sk=sk)
        run = next((r for r in _as_list(runs) if r.get("job_uuid") == uuid), None)
        urls = (run or {}).get("node_urls") or []
        if urls:
            return next((u for u in urls if str(u.get("description")) == str(port)),
                        urls[0])
        status = run.get("status") if run else "?"
        print(f"    run status={status} ...")
    return None


def _pull_model(base: str, model: str) -> None:
    """Pull `model` into the running Ollama server via its HTTP API (best effort)."""
    print(f"  pulling model '{model}' via Ollama (one-time, can take minutes)...")
    try:
        req = Request(f"{base}/api/pull",
                      data=json.dumps({"name": model}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=3600) as r:
            r.read()
        print("  pull complete.")
    except Exception as e:
        print(f"  ! pull request failed ({e}); pull manually: "
              f"curl {base}/api/pull -d '{{\"name\":\"{model}\"}}'")


def _print_endpoint(base: str, model: str) -> None:
    """Print the env exports that point PatientPunk extraction at the server."""
    print("\n=== point PatientPunk extraction at it ===")
    print(f"  export LLM_PROVIDER=openai")
    print(f"  export LLM_BASE_URL={base}/v1")
    print(f"  export LLM_API_KEY=EMPTY")
    print(f"  export MODEL_FAST={model}")
    print(f"  export MODEL_STRONG={model}")
    print(f"\n  then: validate the model (per-field, vs your Claude reference) before scaling:")
    print(f"    python variable_extraction/main.py validate --reference gold.csv --candidate <run>.csv")


# --- subcommands --------------------------------------------------------------

def cmd_check(*, pk: str, sk: str) -> int:
    """Verify API auth with a read-only call. No job, no billing."""
    jobs = _signed_request("GET", "/v1/jobs", pk=pk, sk=sk)
    print(f"  auth OK -- API reachable (jobs visible: {len(_as_list(jobs))})")
    return 0


def cmd_stop(uuid: str, *, pk: str, sk: str) -> int:
    """Cancel a running job by uuid (stops billing)."""
    r = _signed_request("PUT", f"/v1/jobs/{uuid}/cancel",
                        {"reason": "stopped via launch_job.py"}, pk=pk, sk=sk)
    print(f"  cancel {uuid} -> status: {r.get('status')}")
    return 0


def cmd_launch(args, *, pk: str, sk: str) -> int:
    """Launch a PERSISTENT model-server job, wait for it, and print the endpoint."""
    if not args.model:
        sys.exit("--model is required to launch (or use --check to verify auth only).")

    allowed_ip = args.allowed_ip
    if not allowed_ip:
        allowed_ip = _detect_public_ip()
        print(f"  detected public IP -> allowed_ips = {allowed_ip}")

    body = _build_job_body(args, allowed_ip)
    print(f"Launching PERSISTENT job: image={args.image} port={args.port} "
          f"gpu={args.gpu_name or args.gpu_count}")
    created = _signed_request("POST", "/v1/jobs", body, pk=pk, sk=sk)
    uuid = created.get("uuid")
    if not uuid:
        sys.exit(f"No job uuid in response: {created}")
    print(f"  job uuid: {uuid}  status: {created.get('status')}")

    print("  waiting for a job-run with node_urls (reachable host:port)...")
    deadline = time.time() + args.poll_seconds
    node = _poll_for_node(uuid, args.port, deadline, pk=pk, sk=sk)
    if not node:
        sys.exit(f"Timed out waiting for node_urls. Check job {uuid} in the console.")

    host = node.get("hostname")
    port = node.get("port")
    if not host or port is None:
        sys.exit(f"Dispersed returned an incomplete node_urls entry: {node}")
    scheme = "https" if node.get("tls") else "http"
    base = f"{scheme}://{host}:{port}"
    print(f"\n  Reachable at: {base}")

    if args.pull:
        _pull_model(base, args.model)
    _print_endpoint(base, args.model)
    return 0


# --- CLI ----------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=None, help="Ollama model tag, e.g. qwen2.5:32b")
    ap.add_argument("--check", action="store_true",
                    help="Verify API auth with a read-only call and exit (no job, no billing).")
    ap.add_argument("--stop", metavar="UUID", default=None,
                    help="Cancel (stop) a running job by uuid and exit (stops billing).")
    ap.add_argument("--image", default="ollama/ollama", help="Server image (default: ollama/ollama).")
    ap.add_argument("--port", type=int, default=11434, help="Container port (Ollama: 11434).")
    ap.add_argument("--gpu-count", type=int, default=1)
    ap.add_argument("--gpu-name", default=None, help='e.g. "NVIDIA RTX 4090" (optional).')
    ap.add_argument("--min-vram-gb", type=int, default=24)
    ap.add_argument("--allowed-ip", default=None,
                    help="CIDR allowed to reach the job (default: detect your public IP /32).")
    ap.add_argument("--title", default="patientpunk-model-server")
    ap.add_argument("--pull", action="store_true",
                    help="After the job is reachable, pull --model via Ollama's API.")
    ap.add_argument("--poll-seconds", type=int, default=600,
                    help="How long to wait for node_urls (default 600s).")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    pk = os.environ.get("DISPERSED_PUBLIC_KEY", "")
    sk = os.environ.get("DISPERSED_SECRET_KEY", "")
    if not pk or not sk:
        sys.exit("Set DISPERSED_PUBLIC_KEY (pk_...) and DISPERSED_SECRET_KEY (sk_...).")

    if args.check:
        return cmd_check(pk=pk, sk=sk)
    if args.stop:
        return cmd_stop(args.stop, pk=pk, sk=sk)
    return cmd_launch(args, pk=pk, sk=sk)


if __name__ == "__main__":
    sys.exit(main())
