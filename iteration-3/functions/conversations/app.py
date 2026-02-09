import json
import logging
import os

from services.conversation_service import list_conversations, get_messages

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS"
}


def lambda_handler(event, context):
    """Handle conversation list and message history requests."""
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
        
        # Get path parameters
        path_params = event.get("pathParameters") or {}
        session_id = path_params.get("session_id")
        
        if session_id:
            # GET /api/conversations/{session_id} - get messages from AgentCore Memory
            messages = get_messages(session_id, actor_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "session_id": session_id,
                    "actor_id": actor_id,
                    "messages": messages
                })
            }
        else:
            # GET /api/conversations - list conversations from DynamoDB
            conversations = list_conversations(actor_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"conversations": conversations})
            }
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
