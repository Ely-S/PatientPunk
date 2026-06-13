#!/usr/bin/env bash
# Bootstrap a Dispersed (or any) GPU box to serve an open model AND run the
# PatientPunk extraction on-box. Use this for the SSH / ubuntu:24.04 path, or
# whenever you want the model + corpus + extraction co-located (fastest for the
# full 100k-item run -- no per-call network latency).
#
# Usage (after you SSH into the box):
#   curl -fsSL <raw-url>/dispersed/bootstrap.sh -o bootstrap.sh   # or scp it
#   SERVER=ollama MODEL=qwen2.5:32b REPO_URL=https://github.com/Ely-S/PatientPunk \
#     bash bootstrap.sh
#
# Env knobs:
#   SERVER     ollama | vllm        (default: ollama -- most reliable to install)
#   MODEL      model id/tag         (ollama: qwen2.5:32b ; vllm: Qwen/Qwen2.5-32B-Instruct)
#   PORT       server port          (default: 11434 ollama / 8000 vllm)
#   REPO_URL   git URL to clone     (default: https://github.com/Ely-S/PatientPunk)
#   BRANCH     branch               (default: shaun/analysis)
#   REPO_DIR   existing repo path   (skip clone if set)
set -euo pipefail

SERVER="${SERVER:-ollama}"
BRANCH="${BRANCH:-shaun/analysis}"
REPO_URL="${REPO_URL:-https://github.com/Ely-S/PatientPunk}"
if [ "$SERVER" = "vllm" ]; then
  MODEL="${MODEL:-Qwen/Qwen2.5-32B-Instruct}"; PORT="${PORT:-8000}"
else
  MODEL="${MODEL:-qwen2.5:32b}"; PORT="${PORT:-11434}"
fi

echo "== Dispersed bootstrap: SERVER=$SERVER MODEL=$MODEL PORT=$PORT =="
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L || echo "  ! no nvidia-smi (no GPU?)"
command -v git  >/dev/null 2>&1 || { apt-get update -y && apt-get install -y git; }
command -v python3 >/dev/null 2>&1 || { apt-get update -y && apt-get install -y python3 python3-pip python3-venv; }

# --- 1. serve the model -------------------------------------------------------
if [ "$SERVER" = "ollama" ]; then
  command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh
  OLLAMA_HOST="0.0.0.0:${PORT}" nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 5
  echo "  pulling $MODEL (one-time)..."; ollama pull "$MODEL"
  BASE="http://localhost:${PORT}/v1"
else  # vllm
  pip install --upgrade pip >/dev/null
  pip install vllm >/dev/null
  nohup python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --host 0.0.0.0 --port "$PORT" >/tmp/vllm.log 2>&1 &
  echo "  vLLM starting (loads weights; can take minutes -- tail /tmp/vllm.log)"
  BASE="http://localhost:${PORT}/v1"
fi

# --- 2. clone + install the pipeline -----------------------------------------
if [ -z "${REPO_DIR:-}" ]; then
  REPO_DIR="$HOME/PatientPunk"
  [ -d "$REPO_DIR/.git" ] || git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
pip install -e '.[openai,cluster]' >/dev/null || pip install -e . >/dev/null

# --- 3. write .env ------------------------------------------------------------
cat > "$REPO_DIR/.env" <<EOF
LLM_PROVIDER=openai
LLM_BASE_URL=${BASE}
LLM_API_KEY=EMPTY
MODEL_FAST=${MODEL}
MODEL_STRONG=${MODEL}
LLM_TEMPERATURE=0
EOF
echo "  wrote $REPO_DIR/.env (LLM_BASE_URL=${BASE})"

# --- 4. smoke test the endpoint through OUR adapter --------------------------
echo "== smoke test =="
( set -a; . "$REPO_DIR/.env"; set +a
  python3 - <<'PY'
import sys; sys.path.insert(0, "variable_extraction")
from patientpunk._utils import get_llm_client, MODEL_FAST, LLM_TEMPERATURE
try:
    c = get_llm_client()
    r = c.messages.create(model=MODEL_FAST, max_tokens=10, temperature=LLM_TEMPERATURE,
                          messages=[{"role": "user", "content": "Reply with the word OK"}])
    print("  OK ->", r.content[0].text[:40])
except Exception as e:
    print("  ! smoke test failed:", type(e).__name__, str(e)[:200])
    print("    (vLLM may still be loading weights -- retry in a minute; tail /tmp/vllm.log)")
PY
)

cat <<EOF

== ready ==
Next, from $REPO_DIR (env already written):
  set -a; . .env; set +a
  # 1) gate the model per-field vs your Claude reference:
  python variable_extraction/main.py validate --reference gold.csv --candidate <run>.csv
  # 2) if good, run extraction (deductive, promoted schema):
  python variable_extraction/main.py run --schema <promoted>.json --input-dir <corpus>
  # 3) build the clustering matrix + readiness:
  python variable_extraction/main.py cluster-prep --records <corpus>/records.csv
EOF
