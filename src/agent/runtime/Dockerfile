# AgentCore Runtime container image for the Order Reprocessing Agent.
#
# Real implementation (replaces the earlier placeholder that only satisfied
# CDK's AgentRuntimeArtifact.from_asset() requirement — see this project's
# audit.md for the history of that gap across Units 2-6). Runs a real
# Strands Agents SDK agent loop (agent.py), connected to Unit 2's AgentCore
# Gateway MCP endpoint via SigV4-signed HTTP (sigv4_auth.py), following the
# system prompt and model configuration in agent_config.py.
#
# Build context is THIS directory (src/agent/runtime) per
# agent_orchestration.py's `AgentRuntimeArtifact.from_asset(directory="src/agent/runtime")`
# — all imports in agent.py/gateway_client.py are flat, relative to this
# directory's own files (agent_config, gateway_client, sigv4_auth), not the
# project's full src/ package tree.

FROM public.ecr.aws/docker/library/python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_config.py sigv4_auth.py gateway_client.py agent.py ./

# Run as a non-root user (Checkov CKV_DOCKER_3) rather than the image default root.
RUN useradd --create-home --shell /usr/sbin/nologin appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Checkov CKV_DOCKER_2: basic liveness check against the Flask app's own port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=3)" || exit 1

CMD ["python3", "agent.py"]
