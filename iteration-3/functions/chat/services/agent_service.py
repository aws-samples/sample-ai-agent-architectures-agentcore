"""Agent service - invokes AgentCore Runtime."""
import boto3
import json
import logging
import os

logger = logging.getLogger()

AGENTCORE_RUNTIME_ARN = os.environ.get("AGENTCORE_RUNTIME_ARN", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_client = None


def _get_client():
    """Lazy initialization of AgentCore client."""
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    return _client


def invoke_agent(message: str, session_id: str, actor_id: str) -> str:
    """Invoke AgentCore Runtime and return response."""
    if not AGENTCORE_RUNTIME_ARN:
        raise ValueError("AGENTCORE_RUNTIME_ARN not configured")
    
    logger.info(f"Invoking agent for session {session_id}, actor {actor_id}")
    
    client = _get_client()
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
        qualifier="DEFAULT",
        payload=json.dumps({
            "prompt": message,
            "session_id": session_id,
            "actor_id": actor_id
        })
    )
    
    # Parse JSON response
    response_body = response["response"].read().decode("utf-8")
    result = json.loads(response_body)
    return result.get("response", response_body)
