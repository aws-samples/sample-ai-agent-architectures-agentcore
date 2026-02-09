import json
import os
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AGENTCORE_RUNTIME_ARN = os.environ.get("AGENTCORE_RUNTIME_ARN", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS"
}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    return _client


def lambda_handler(event, context):
    """Handle chat requests from API Gateway."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        message = body.get("message", "")
        
        # Invoke AgentCore Runtime
        client = _get_client()
        response = client.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": message})
        )
        
        # Parse JSON response
        response_body = response["response"].read().decode("utf-8")
        result = json.loads(response_body)
        agent_response = result.get("response", response_body)
        
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"response": agent_response})
        }
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
