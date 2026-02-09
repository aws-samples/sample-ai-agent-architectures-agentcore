import json
import logging
import os

from services.agent_service import invoke_agent

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS"
}


def lambda_handler(event, context):
    """Handle chat requests."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Get actor_id from Cognito authorizer claims
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        actor_id = claims.get("sub")
        
        if not actor_id:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Unauthorized - no user identity"})
            }
        
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        message = body.get("message", "")
        session_id = body.get("session_id", "")
        
        if not message:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Message is required"})
            }
        
        if not session_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "session_id is required"})
            }
        
        # Invoke agent and collect response
        response_text = invoke_agent(message, session_id, actor_id)
        
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "response": response_text,
                "session_id": session_id
            })
        }
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
