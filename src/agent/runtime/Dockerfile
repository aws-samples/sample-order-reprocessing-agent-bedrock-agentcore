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

FROM public.ecr.aws/docker/library/python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_config.py sigv4_auth.py gateway_client.py agent.py ./

EXPOSE 8080

CMD ["python3", "agent.py"]
