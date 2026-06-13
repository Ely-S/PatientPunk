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
from urllib.error import HTTPError

API = "https://api.dispersed.com"


def _nonce() -> str:
    return os.urandom(16).hex()  # 16 bytes -> 32 hex chars


def _signed_request(method: str, path: str, body: dict | None = None,
                    *, pk: str, sk: str, query: str = "") -> dict:
    body_bytes = (json.dumps(body, separators=(",", ":")).encode()
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Ollama model tag, e.g. qwen2.5:32b")
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
    args = ap.parse_args(argv)

    pk = os.environ.get("DISPERSED_PUBLIC_KEY", "")
    sk = os.environ.get("DISPERSED_SECRET_KEY", "")
    if not pk or not sk:
        sys.exit("Set DISPERSED_PUBLIC_KEY (pk_...) and DISPERSED_SECRET_KEY (sk_...).")

    allowed_ip = args.allowed_ip
    if not allowed_ip:
        try:
            with urlopen("https://api.ipify.org", timeout=10) as r:
                allowed_ip = r.read().decode().strip() + "/32"
            print(f"  detected public IP -> allowed_ips = {allowed_ip}")
        except Exception:
            sys.exit("Could not detect public IP; pass --allowed-ip <cidr> explicitly.")

    docker_params: dict = {
        "image": args.image,
        "tag": "latest",
        "ports": [args.port],
        "allowed_ips": [allowed_ip],
        # Ollama must bind all interfaces to be reachable via node_urls.
        "env": {"OLLAMA_HOST": f"0.0.0.0:{args.port}"},
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

    print(f"Launching PERSISTENT job: image={args.image} port={args.port} "
          f"gpu={args.gpu_name or args.gpu_count}")
    created = _signed_request("POST", "/v1/jobs", body, pk=pk, sk=sk)
    uuid = created.get("uuid")
    if not uuid:
        sys.exit(f"No job uuid in response: {created}")
    print(f"  job uuid: {uuid}  status: {created.get('status')}")

    # Poll for node_urls (the reachable hostname/port).
    print("  waiting for the job to be assigned + reachable (node_urls)...")
    deadline = time.time() + args.poll_seconds
    node = None
    while time.time() < deadline:
        time.sleep(10)
        job = _signed_request("GET", f"/v1/jobs/{uuid}", pk=pk, sk=sk)
        status = job.get("status")
        urls = job.get("node_urls") or []
        if urls:
            node = next((u for u in urls if u.get("port") == args.port), urls[0])
            break
        print(f"    status={status} ...")
    if not node:
        sys.exit(f"Timed out waiting for node_urls. Check job {uuid} in the console.")

    host, port = node["hostname"], node["port"]
    scheme = "https" if node.get("tls") else "http"
    base = f"{scheme}://{host}:{port}"
    print(f"\n  Reachable at: {base}")

    if args.pull:
        print(f"  pulling model '{args.model}' via Ollama (one-time, can take minutes)...")
        try:
            req = Request(f"{base}/api/pull",
                          data=json.dumps({"name": args.model}).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=3600) as r:
                r.read()
            print("  pull complete.")
        except Exception as e:
            print(f"  ! pull request failed ({e}); pull manually: "
                  f"curl {base}/api/pull -d '{{\"name\":\"{args.model}\"}}'")

    print("\n=== point PatientPunk extraction at it ===")
    print(f"  export LLM_PROVIDER=openai")
    print(f"  export LLM_BASE_URL={base}/v1")
    print(f"  export LLM_API_KEY=EMPTY")
    print(f"  export MODEL_FAST={args.model}")
    print(f"  export MODEL_STRONG={args.model}")
    print(f"\n  then: validate the model (per-field, vs your Claude reference) before scaling:")
    print(f"    python variable_extraction/main.py validate --reference gold.csv --candidate <run>.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
