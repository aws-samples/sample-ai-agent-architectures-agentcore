import logging
import os
import json
import requests
import boto3
from datetime import datetime

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrockConverse
from langgraph.prebuilt import create_react_agent
from langgraph_checkpoint_aws import AgentCoreMemorySaver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
SSM_MEMORY_ID = "/agentcore/memory-id"
SSM_CONVERSATION_TABLE = "/dynamo/conversation-table"


def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_weather(latitude: float, longitude: float) -> str:
    """Get the current weather forecast for a location using lat/long coordinates.
    
    Examples:
    - New York: latitude=40.7128, longitude=-74.0060
    - Los Angeles: latitude=34.0522, longitude=-118.2437
    - Seattle: latitude=47.6062, longitude=-122.3321
    """
    try:
        headers = {"User-Agent": "AgentCoreSample"}
        points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
        points_response = requests.get(points_url, headers=headers, timeout=10)
        points_response.raise_for_status()
        points_data = points_response.json()
        
        forecast_url = points_data["properties"]["forecast"]
        if not forecast_url.startswith("https://"):
            return "Unable to get weather: invalid URL scheme"
        forecast_response = requests.get(forecast_url, headers=headers, timeout=10)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()
        
        period = forecast_data["properties"]["periods"][0]
        return f"{period['name']}: {period['temperature']}°{period['temperatureUnit']}, {period['shortForecast']}"
    except Exception as e:
        return f"Unable to get weather: {e}"


TOOLS = [get_current_time, get_weather]

_agent = None
_checkpointer = None


def get_ssm_param(name: str) -> str:
    return boto3.client("ssm", region_name=AWS_REGION).get_parameter(Name=name)["Parameter"]["Value"]


def get_agent():
    global _agent, _checkpointer
    if _agent is None:
        memory_id = get_ssm_param(SSM_MEMORY_ID)
        _checkpointer = AgentCoreMemorySaver(memory_id, region_name=AWS_REGION)
        llm = ChatBedrockConverse(model=MODEL_ID, region_name=AWS_REGION)
        _agent = create_react_agent(llm, TOOLS, checkpointer=_checkpointer)
    return _agent, _checkpointer


def is_new_conversation(session_id: str, actor_id: str) -> bool:
    try:
        config = {"configurable": {"thread_id": session_id, "actor_id": actor_id}}
        return _checkpointer.get(config) is None
    except:
        return True


def generate_conversation_name(message: str) -> str:
    try:
        llm = ChatBedrockConverse(model=MODEL_ID, region_name=AWS_REGION)
        response = llm.invoke(f"Generate a 3-5 word title for: {message[:200]}")
        return response.content.strip().strip('"\'#')[:50]
    except:
        return "New Conversation"


def save_conversation_metadata(session_id: str, actor_id: str, name: str):
    try:
        table_name = get_ssm_param(SSM_CONVERSATION_TABLE)
        boto3.resource("dynamodb", region_name=AWS_REGION).Table(table_name).put_item(Item={
            "actor_id": actor_id,
            "session_id": session_id,
            "conversation_name": name,
            "created_at": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to save metadata: {e}")


@app.entrypoint
def invoke(payload, context=None):
    message = payload.get("prompt", "Hello") if payload else "Hello"
    session_id = payload.get("session_id", "default") if payload else "default"
    actor_id = payload.get("actor_id", "default") if payload else "default"
    
    agent, checkpointer = get_agent()
    
    if is_new_conversation(session_id, actor_id):
        name = generate_conversation_name(message)
        save_conversation_metadata(session_id, actor_id, name)
    
    config = {"configurable": {"thread_id": session_id, "actor_id": actor_id}}
    result = agent.invoke({"messages": [("human", message)]}, config=config)
    
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, 'content') and msg.type == "ai":
            content = msg.content
            if isinstance(content, str):
                return {"response": content, "session_id": session_id}
            elif isinstance(content, list):
                text = "".join(b.get("text", b) if isinstance(b, dict) else b for b in content)
                return {"response": text, "session_id": session_id}
    
    return {"response": "", "session_id": session_id}


if __name__ == "__main__":
    app.run()
