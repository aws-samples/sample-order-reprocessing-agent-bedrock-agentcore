"""
SigV4 HTTP auth for AgentCore Gateway's MCP Streamable HTTP endpoint.

Implemented directly on botocore's SigV4Auth (already a transitive
dependency via boto3, which this project already depends on) rather than
pulling in a low-adoption third-party httpx-SigV4 package — botocore's
signer is the same one AWS's own SDKs use internally, so this avoids
introducing a new, less-vetted dependency for security-sensitive request
signing. Verified via direct API inspection (botocore.auth.SigV4Auth,
botocore.awsrequest.AWSRequest) before writing this, not assumed.
"""

from __future__ import annotations

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session


class SigV4HTTPAuth(httpx.Auth):
    """httpx.Auth implementation that signs outbound requests to
    AgentCore Gateway's MCP endpoint using AWS SigV4 (service:
    bedrock-agentcore), per the Gateway's IamAuthorizer configuration
    (see agent_orchestration.py's `authorizer_configuration=agentcore.IamAuthorizer()`)."""

    def __init__(self, region: str, service: str = "bedrock-agentcore") -> None:
        self._region = region
        self._service = service
        self._session = Session()

    def auth_flow(self, request: httpx.Request):
        credentials = self._session.get_credentials()
        if credentials is None:
            raise RuntimeError(
                "No AWS credentials found for SigV4-signing the Gateway MCP request. "
                "The AgentCore Runtime container must have an execution role with "
                "bedrock-agentcore:InvokeGateway-equivalent permissions (or the Gateway "
                "target's underlying tool invocation permissions)."
            )

        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        SigV4Auth(credentials, self._service, self._region).add_auth(aws_request)

        for key, value in dict(aws_request.headers).items():
            request.headers[key] = value

        yield request
