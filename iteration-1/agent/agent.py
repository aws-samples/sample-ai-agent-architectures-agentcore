import os
import json
import urllib.request
from datetime import datetime

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrockConverse
from langgraph.prebuilt import create_react_agent

app = BedrockAgentCoreApp()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


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
        points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
        req = urllib.request.Request(points_url, headers={"User-Agent": "AgentCoreSample"})
        with urllib.request.urlopen(req, timeout=10) as response:
            points_data = json.loads(response.read().decode())
        
        forecast_url = points_data["properties"]["forecast"]
        if not forecast_url.startswith("https://"):
            return "Unable to get weather: invalid URL scheme"
        req = urllib.request.Request(forecast_url, headers={"User-Agent": "AgentCoreSample"})
        with urllib.request.urlopen(req, timeout=10) as response:
            forecast_data = json.loads(response.read().decode())
        
        period = forecast_data["properties"]["periods"][0]
        return f"{period['name']}: {period['temperature']}°{period['temperatureUnit']}, {period['shortForecast']}"
    except Exception as e:
        return f"Unable to get weather: {e}"


TOOLS = [get_current_time, get_weather]

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        llm = ChatBedrockConverse(model=MODEL_ID, region_name=AWS_REGION)
        _agent = create_react_agent(llm, TOOLS)
    return _agent


@app.entrypoint
def invoke(payload, context):
    prompt = payload.get("prompt", "Hello!") if payload else "Hello!"
    result = get_agent().invoke({"messages": [("human", prompt)]})
    
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, 'content') and msg.type == "ai":
            content = msg.content
            if isinstance(content, str):
                return {"response": content}
            elif isinstance(content, list):
                text = "".join(b.get("text", b) if isinstance(b, dict) else b for b in content)
                return {"response": text}
    return {"response": ""}


if __name__ == "__main__":
    app.run()
