# Throughput path: vLLM serving a QUANTIZED 32B with the model baked into CMD.
#
# Dispersed has NO command override (only image/env/ports/...), and the GPU
# catalog tops out at a single 32GB card (RTX 5090) / 24GB (RTX 4090) -- there
# are NO multi-GPU nodes to requisition. So we serve a 4-bit AWQ 32B (~19GB
# weights) that fits ONE card, and rely on vLLM's continuous batching for real
# throughput (Ollama force-serializes one request at a time -> ~83s/record;
# this is the fix).
#
# Build + push to a registry Dispersed can pull, then launch a PERSISTENT job:
#   docker build -f dispersed/vllm.Dockerfile -t <registry>/pp-vllm-qwen32-awq:latest .
#   docker push <registry>/pp-vllm-qwen32-awq:latest
#   python dispersed/launch_job.py --image <registry>/pp-vllm-qwen32-awq --port 8000 \
#       --model Qwen/Qwen2.5-32B-Instruct-AWQ --gpu-name "NVIDIA RTX 5090" --min-vram-gb 32
#   (NO --pull: the model is baked into the image. Then point extraction at it:
#    MODEL_FAST/STRONG=Qwen/Qwen2.5-32B-Instruct-AWQ, LLM_BASE_URL=http://<node>:8000/v1)
#
# GPU notes:
#  * RTX 5090 (32GB) is the throughput target -- ~19GB weights leaves ~10-12GB
#    for KV-cache => good batch concurrency. BUT the 5090 is Blackwell (sm_120);
#    if vLLM's kernels misbehave there, fall back to the 4090.
#  * RTX 4090 (24GB, $0.35/hr, well-supported): AWQ-32B fits, but KV-cache is
#    tight -> keep --max-model-len modest and expect lower concurrency.
FROM vllm/vllm-openai:latest

# Faster weight download at image-build time.
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Actually BAKE the weights into the image so the first container start is
# instant -- no ~19GB download on billed GPU time (the point of the "no --pull"
# Path B workflow). vLLM finds them in the HF cache at runtime by repo id.
RUN pip install --no-cache-dir hf_transfer \
 && python3 -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-32B-Instruct-AWQ')"

# --max-model-len bounds the KV-cache so the weights+cache fit a 24GB card too;
# raise it (e.g. 16384) when you know you're landing on the 32GB 5090.
# awq_marlin is the fast AWQ kernel on Ampere/Ada; vLLM falls back to plain awq
# if unsupported on the assigned GPU.
CMD ["--model", "Qwen/Qwen2.5-32B-Instruct-AWQ", \
     "--quantization", "awq_marlin", \
     "--max-model-len", "8192", \
     "--gpu-memory-utilization", "0.92", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--served-model-name", "Qwen/Qwen2.5-32B-Instruct-AWQ"]
