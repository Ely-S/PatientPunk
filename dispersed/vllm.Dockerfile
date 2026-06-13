# Throughput path: a vLLM image with the model baked into the default command.
#
# Dispersed's job API has NO command/args override (only image/env/ports/...),
# so the model must be the image's default CMD. vllm/vllm-openai's ENTRYPOINT is
# the OpenAI API server; CMD supplies its arguments.
#
# Build + push to a registry Dispersed can pull, then launch a PERSISTENT job
# with that image and ports:[8000]:
#   docker build -f dispersed/vllm.Dockerfile -t <registry>/pp-vllm-qwen:latest .
#   docker push <registry>/pp-vllm-qwen:latest
#   python dispersed/launch_job.py --image <registry>/pp-vllm-qwen --port 8000 \
#       --model Qwen/Qwen2.5-32B-Instruct --gpu-name "<gpu>" --min-vram-gb 80
#   (then MODEL_FAST/STRONG=Qwen/Qwen2.5-32B-Instruct, LLM_BASE_URL=<node>:8000/v1)
#
# vLLM gives continuous batching -> far higher throughput than Ollama for the
# full 100k-item run. Change the model below to whatever fits your GPU's VRAM
# (32B ~ 1x80GB or 2x48GB; 72B ~ 2x80GB; quantized variants need less).
FROM vllm/vllm-openai:latest

# For gated models set HUGGING_FACE_HUB_TOKEN as a job env var (Qwen/Llama-3.3
# instruct are open). --download-dir can point at a mounted volume to cache weights.
CMD ["--model", "Qwen/Qwen2.5-32B-Instruct", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--served-model-name", "Qwen/Qwen2.5-32B-Instruct"]
