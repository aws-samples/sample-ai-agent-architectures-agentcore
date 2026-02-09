import boto3
import json
import base64
import logging
import os
from typing import List, Dict

logger = logging.getLogger()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")
CONVERSATION_TABLE = os.environ.get("CONVERSATION_TABLE", "")

_agentcore = None
_dynamodb = None

# Try to import msgpack for decoding LangGraph checkpoint data
try:
    import msgpack
    from msgpack import ExtType as MsgpackExtType
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False
    MsgpackExtType = None


def _get_agentcore_client():
    global _agentcore
    if _agentcore is None:
        _agentcore = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    return _agentcore


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def list_conversations(actor_id: str) -> List[Dict]:
    """List conversations from DynamoDB metadata table."""
    if not CONVERSATION_TABLE:
        logger.warning("CONVERSATION_TABLE not configured")
        return []
    
    try:
        table = _get_dynamodb().Table(CONVERSATION_TABLE)
        response = table.query(
            KeyConditionExpression="actor_id = :aid",
            ExpressionAttributeValues={":aid": actor_id},
            ScanIndexForward=False  # Most recent first
        )
        
        conversations = []
        for item in response.get("Items", []):
            conversations.append({
                "session_id": item.get("session_id"),
                "conversation_name": item.get("conversation_name", "Untitled"),
                "created_at": item.get("created_at", "")
            })
        
        return conversations
        
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        return []


def get_messages(session_id: str, actor_id: str) -> List[Dict]:
    """Get messages from AgentCore Memory."""
    if not AGENTCORE_MEMORY_ID:
        logger.warning("AGENTCORE_MEMORY_ID not configured")
        return []
    
    if not HAS_MSGPACK:
        logger.error("msgpack required for message history")
        return []
    
    try:
        client = _get_agentcore_client()
        response = client.list_events(
            memoryId=AGENTCORE_MEMORY_ID,
            sessionId=session_id,
            actorId=actor_id,
            includePayloads=True
        )
        
        messages = []
        seen_content = set()
        
        for event in response.get("events", []):
            timestamp = event.get("eventTimestamp", "")
            if hasattr(timestamp, 'isoformat'):
                timestamp = timestamp.isoformat()
            
            for payload_item in event.get("payload", []):
                blob = payload_item.get("blob", "")
                if not blob:
                    continue
                
                try:
                    blob_data = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                
                event_type = blob_data.get("event_type", "")
                
                if event_type == "writes":
                    writes = blob_data.get("writes", [])
                    for msg in _extract_messages_from_writes(writes, str(timestamp)):
                        content = msg["content"]
                        if isinstance(content, list):
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict) and "text" in part:
                                    text_parts.append(part["text"])
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            content = "".join(text_parts)
                            msg["content"] = content
                        
                        content_key = (msg["role"], str(content))
                        if content_key not in seen_content:
                            seen_content.add(content_key)
                            messages.append(msg)
        
        messages.sort(key=lambda x: x["timestamp"])
        return messages
        
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        return []


def _decode_msgpack_value(value_obj: dict):
    """Decode a msgpack value object."""
    if not HAS_MSGPACK or not isinstance(value_obj, dict):
        return None
    
    data_type = value_obj.get("type")
    data = value_obj.get("data", "")
    
    if data_type == "msgpack" and data:
        try:
            decoded = base64.b64decode(data)
            return msgpack.unpackb(decoded, raw=False)
        except Exception:
            pass
    return None


def _extract_langchain_message(item) -> Dict:
    """Extract role and content from a LangChain message."""
    if HAS_MSGPACK and MsgpackExtType and isinstance(item, MsgpackExtType):
        try:
            inner = msgpack.unpackb(item.data, raw=False)
            if isinstance(inner, list) and len(inner) >= 3:
                data_dict = inner[2] if len(inner) > 2 else {}
                if isinstance(data_dict, dict):
                    content = data_dict.get("content", "")
                    msg_type = data_dict.get("type", "").lower()
                    if msg_type in ("human", "ai", "user", "assistant") and content:
                        role = "user" if msg_type == "human" else ("assistant" if msg_type == "ai" else msg_type)
                        return {"role": role, "content": content}
        except Exception:
            pass
    return None


def _extract_messages_from_writes(writes: list, timestamp: str) -> List[Dict]:
    """Extract messages from LangGraph writes events."""
    messages = []
    
    for write in writes:
        if write.get("channel") != "messages":
            continue
        
        decoded = _decode_msgpack_value(write.get("value", {}))
        if not decoded or not isinstance(decoded, list):
            continue
        
        for item in decoded:
            lc_msg = _extract_langchain_message(item)
            if lc_msg:
                lc_msg["timestamp"] = timestamp
                messages.append(lc_msg)
                continue
            
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                role = str(item[0]).lower()
                content = str(item[1])
                if role in ("human", "ai", "user", "assistant") and content:
                    messages.append({
                        "role": "user" if role == "human" else ("assistant" if role == "ai" else role),
                        "content": content,
                        "timestamp": timestamp
                    })
            elif isinstance(item, dict):
                role = item.get("type", item.get("role", "")).lower()
                content = item.get("content", "")
                if role in ("human", "ai", "user", "assistant") and content:
                    messages.append({
                        "role": "user" if role == "human" else ("assistant" if role == "ai" else role),
                        "content": content,
                        "timestamp": timestamp
                    })
    
    return messages
