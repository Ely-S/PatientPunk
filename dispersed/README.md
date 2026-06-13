# Running PatientPunk extraction on Dispersed

[Dispersed](https://dispersed.com) (Render Network's GPU compute platform) runs
**Docker jobs** on decentralized GPUs (~$0.69/GPU-hr). It is *not* a ComfyUI
service and *not* a hosted LLM API — you run a container, and reach it via the
job's `node_urls`. So the plan is: **serve an open model on a Dispersed job, then
point the pipeline at it** with the OpenAI-compatible provider we built
(`LLM_PROVIDER=openai`).

Two facts shape everything (verified against the API/OpenAPI):
- The job API has **no command/args override** (only `image`, `env`, `ports`,
  `sshkey`, `allowed_ips`, `gpu_*`, `volumes`). So either the image's *default*
  command serves your model (Ollama, or a custom vLLM image), or you SSH in.
- A running job exposes **`node_urls`** (`hostname`, `port`, `protocol`, `tls`);
  reach the server there. `allowed_ips` gates who can connect.
- Auth is **HMAC-signed** (`X-API-Key`/`X-Time`/`X-Nonce`/`X-Signature`).
  `launch_job.py` implements it; if you hit 401, verify the canonical string
  against Dispersed's TypeScript SDK / MCP server (the authoritative auth path).

Prereqs: a Dispersed account + API keys (`pk_…`, `sk_…`), this repo, and — to use
the `validate` gate — a small gold set (see `variable_extraction` `validate
--export-template`).

---

## Path A — Ollama job, run extraction from your laptop (simplest, no build)

Good for the `validate` gate and moderate runs. Ollama's default entrypoint
serves an OpenAI-compatible API; you pull the model via its API.

```bash
export DISPERSED_PUBLIC_KEY=pk_...  DISPERSED_SECRET_KEY=sk_...
python dispersed/launch_job.py --model qwen2.5:32b --gpu-name "<gpu>" --min-vram-gb 24 --pull
# -> prints LLM_BASE_URL=http://<node-host>:<port>/v1  (your IP auto-whitelisted)
```
Then locally (repo + corpus already here):
```bash
export LLM_PROVIDER=openai LLM_BASE_URL=http://<node-host>:<port>/v1 LLM_API_KEY=EMPTY
export MODEL_FAST=qwen2.5:32b MODEL_STRONG=qwen2.5:32b
python variable_extraction/main.py validate --reference gold.csv --candidate <run>.csv
```
Note: Ollama is single-stream-ish — fine for ~hundreds of records (validation),
slow for the full 100k. Use Path B for the full run.

## Path B — custom vLLM image, max throughput (for the full corpus)

vLLM's continuous batching is the right tool for 100k items. Since there's no
command override, bake the model into the image (`dispersed/vllm.Dockerfile`):

```bash
docker build -f dispersed/vllm.Dockerfile -t <registry>/pp-vllm-qwen:latest .
docker push <registry>/pp-vllm-qwen:latest
python dispersed/launch_job.py --image <registry>/pp-vllm-qwen --port 8000 \
    --model Qwen/Qwen2.5-32B-Instruct --gpu-name "<gpu>" --min-vram-gb 80
```
(`launch_job.py` skips the Ollama pull when the model is baked in — omit `--pull`.)
Then set `MODEL_FAST/STRONG=Qwen/Qwen2.5-32B-Instruct`, `LLM_BASE_URL=http://<node>:8000/v1`.

## Path C — SSH box, serve + extract on-box (fastest end-to-end)

Launch a PERSISTENT `ubuntu:24.04` job with your SSH key + `ports`, SSH in, and
run `bootstrap.sh` — it installs the server, pulls the model, clones+installs the
repo, writes `.env`, and smoke-tests the endpoint through our adapter. Running
extraction on the same box avoids per-call network latency over the full run.

```bash
ssh -i ~/.ssh/dispersed -p <port> duser@<node-host>
SERVER=vllm MODEL=Qwen/Qwen2.5-32B-Instruct bash bootstrap.sh   # or SERVER=ollama
```

---

## After the model is reachable — the run sequence

1. **Gate it (do not skip):** score the open model **per field** against your
   Claude reference on the gold set. Decide per-field whether it's good enough.
   ```bash
   python variable_extraction/main.py validate --reference gold.csv --candidate <model_run>.csv
   ```
2. **Extract** (deductive, promoted schema) over the corpus:
   ```bash
   python variable_extraction/main.py run --schema <promoted>.json --input-dir <corpus>
   ```
   `output/llm_provenance.json` records the model/endpoint/temperature for the run.
3. **Build the clustering matrix + readiness check:**
   ```bash
   python variable_extraction/main.py cluster-prep --records <corpus>/records.csv --min-coverage 0.3
   ```

## Networking
`node_urls` exposes the job's port to IPs in `allowed_ips`. To reach it off-box
(Path A/B from your laptop), `launch_job.py` whitelists your detected public IP;
pass `--allowed-ip <cidr>` to override. If your port isn't reachable, run on-box
(Path C) or open an SSH tunnel: `ssh -L <port>:localhost:<port> …`.

## Model sizing (start here, then let `validate` decide)
- `Qwen/Qwen2.5-32B-Instruct` or `Llama-3.3-70B-Instruct` — strong at JSON/extraction.
- Smaller (7–14B) is cheaper but may stumble on the ~95-field structured output —
  `validate` will tell you, per field. Quantized (AWQ/GPTQ) variants cut VRAM.
