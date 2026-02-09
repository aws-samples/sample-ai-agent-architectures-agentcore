# Iteration 3: Amazon API Gateway + AWS Lambda + LangGraph Agent hosted on Amazon Bedrock AgentCore Runtime + Memory using Amazon Bedrock AgentCore Memory

Full-featured chat application with conversation persistence and auto-generated conversation names.

## Architecture

![IAM integration with AgentCore Runtime with additional functionality for memory](../images/iteration_3.png)


## Features

- **Amazon Cognito Auth**: JWT validation at Amazon API Gateway level
- **IAM Auth**: AWS Lambda → Amazon Bedrock AgentCore uses IAM credentials
- **Conversation Memory**: Messages stored in Amazon Bedrock AgentCore Memory
- **Auto-naming**: Agent generates conversation names on first message
- **Amazon DynamoDB**: Stores conversation metadata (names, timestamps)

## Prerequisites

- AWS CLI configured with credentials
- SAM CLI installed ([installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
- Python 3.11+ (`python3 --version` to check; use `uv python install 3.11` if needed)

**Amazon Cognito must be deployed first** (from iteration-0):

```bash
cd ../iteration-0
aws cloudformation deploy \
  --template-file cognito.yaml \
  --stack-name agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

> **Note**: If you already deployed Amazon Cognito for a previous iteration, skip this step.

Also need a test user created (see iteration-0 README).

## Deployment

### 1. Get Execution Role ARN

```bash
EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`AgentCoreExecutionRoleArn`].OutputValue' \
  --output text)
echo "Execution Role ARN: $EXECUTION_ROLE_ARN"
```

> **Save this ARN** - you'll paste it during agent configuration.

### 2. Deploy Agent with Memory

```bash
cd agent
agentcore configure
```

When prompted during configuration:
- **Entrypoint**: `agent.py`
- **Agent name**: `agent_3` (or press Enter for default)
- **Requirements file**: Press Enter to use detected `requirements.txt`
- **Deployment type**: `1` (Direct Code Deploy)
- **Python runtime**: `2` (PYTHON_3_11)
- **Execution role**: Paste the `$EXECUTION_ROLE_ARN` from step 1
- **S3 bucket**: Press Enter to auto-create
- **Configure OAuth authorizer?**: `no` (we use IAM auth - Lambda calls agent)
- **Request header allowlist**: `no`
- **Memory**: `c` (create new memory)
  - **Memory name**: `iteration3-memory` (or any name you prefer)

> **Important**: Iteration-3 uses IAM authentication (not OAuth). The AWS Lambda calls the agent using its IAM role. Memory is required for conversation persistence.

Then deploy:
```bash
agentcore deploy
```

Note the Agent ARN and Memory ID from the output:
- Agent ARN: `arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/AGENT_ID`
- Memory ID: `iteration3-memory-XXXXX` (the full ID including suffix)

> **⚠️ Important**: Save both the Agent ARN and Memory ID - you'll need them for the SAM deployment.


### 3. Store AWS Systems Manager Parameters

The agent reads these at runtime to find the memory and Amazon DynamoDB table:

```bash
# Replace <YOUR_MEMORY_ID> with the Memory ID from agentcore deploy output
aws ssm put-parameter --name /agentcore/memory-id --value "<YOUR_MEMORY_ID>" --type String --overwrite
aws ssm put-parameter --name /dynamo/conversation-table --value "iteration3-conversations" --type String --overwrite
```

> **Verify the parameters were created**:
> ```bash
> aws ssm get-parameter --name /agentcore/memory-id --query 'Parameter.Value' --output text
> aws ssm get-parameter --name /dynamo/conversation-table --query 'Parameter.Value' --output text
> ```

### 4. Build AWS Lambda Functions

```bash
cd ..  # Back to iteration-3 root (if still in agent/)

# Build
sam build
```

### 5. Deploy AWS Lambda + Amazon API Gateway

Get the Amazon Cognito ARN:
```bash
COGNITO_ARN=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolArn`].OutputValue' \
  --output text)
echo "Cognito ARN: $COGNITO_ARN"
```

Deploy (replace placeholders with values from step 2):
```bash
sam deploy --parameter-overrides \
  "AgentCoreRuntimeArn=arn:aws:bedrock-agentcore:<YOUR_REGION>:<YOUR_ACCOUNT_ID>:runtime/<YOUR_AGENT_RUNTIME_ID>" \
  "AgentCoreMemoryId=<YOUR_MEMORY_ID>" \
  "CognitoUserPoolArn=arn:aws:cognito-idp:<YOUR_REGION>:<YOUR_ACCOUNT_ID>:userpool/<YOUR_USER_POOL_ID>" \
  --no-confirm-changeset
```

> **Tip**: Copy the Agent ARN and Memory ID directly from the `agentcore deploy` output to avoid formatting issues.

> **If deployment fails with ROLLBACK_COMPLETE**: The stack is in a failed state. Delete it first:
> ```bash
> aws cloudformation delete-stack --stack-name iteration3
> # Wait for deletion to complete, then retry sam deploy
> ```

Note the Amazon API Gateway endpoint from the outputs.

### 6. Update Frontend Config

Get the Amazon Cognito values from the stack:
```bash
# Get Cognito domain
COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoDomain`].OutputValue' \
  --output text)
echo "Cognito Domain: $COGNITO_DOMAIN"

# Get Client ID
CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
  --output text)
echo "Client ID: $CLIENT_ID"

# Get API endpoint (from iteration3 stack)
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name iteration3 \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)
echo "API Endpoint: $API_ENDPOINT"
```

Edit `frontend/index.html` and update the CONFIG section with these values:

```javascript
const CONFIG = {
  cognitoDomain: 'apigw-agentcore-<YOUR_ACCOUNT_ID>.auth.<YOUR_REGION>.amazoncognito.com',  // from COGNITO_DOMAIN (without https://)
  clientId: '<YOUR_CLIENT_ID>',  // from CLIENT_ID
  redirectUri: 'http://localhost:8000',
  apiEndpoint: 'https://<YOUR_API_ID>.execute-api.<YOUR_REGION>.amazonaws.com/prod'  // from API_ENDPOINT
};
```

### 7. Test

```bash
cd frontend
python3 -m http.server 8000
# Open http://localhost:8000
```

Login with your Amazon Cognito test user and send a message. The agent will:
1. Generate a conversation name from your first message
2. Save it to Amazon DynamoDB
3. Display it in the sidebar

> **Troubleshooting**:
> - **Conversations not appearing in sidebar**: Check that AWS Systems Manager parameters are set correctly (step 3).
> - **500 errors**: Check Amazon CloudWatch Logs for the AWS Lambda functions. Common causes: missing AWS Systems Manager parameters, IAM permission issues.
> - **First message slow**: Cold start for AWS Lambda + Amazon Bedrock AgentCore. Subsequent messages will be faster.
> - **"Unable to get weather"**: The weather.gov API only works for US locations. Try asking about a US city.

## Cleanup

```bash
# Delete AWS Lambda stack
sam delete --stack-name iteration3

# Delete agent
cd agent
agentcore destroy

# Delete AWS Systems Manager parameters
aws ssm delete-parameter --name /agentcore/memory-id
aws ssm delete-parameter --name /dynamo/conversation-table
```

> **Note**: The Amazon DynamoDB table is deleted automatically with the AWS SAM stack. Amazon Bedrock AgentCore Memory is deleted with `agentcore destroy`.

## File Structure

```
iteration-3/
├── agent/                      # Amazon Bedrock AgentCore Runtime agent
│   ├── agent.py               # Agent with conversation naming
│   └── requirements.txt
├── functions/
│   ├── chat/                  # Chat AWS Lambda
│   │   ├── app.py
│   │   ├── requirements.txt
│   │   └── services/
│   │       └── agent_service.py
│   └── conversations/         # Conversations AWS Lambda
│       ├── app.py
│       ├── requirements.txt
│       └── services/
│           └── conversation_service.py
├── frontend/
│   └── index.html
├── template.yaml              # AWS SAM template
└── samconfig.toml
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/chat | Send message to agent |
| GET | /api/conversations | List conversations (from Amazon DynamoDB) |
| GET | /api/conversations/{session_id} | Get messages (from Amazon Bedrock AgentCore Memory) |

## Data Flow

1. **Chat**: Frontend → Amazon API Gateway → Chat AWS Lambda → Amazon Bedrock AgentCore Runtime
   - Agent checks if new conversation, generates name, saves to Amazon DynamoDB
   - Agent processes message with memory context
   
2. **List Conversations**: Frontend → Amazon API Gateway → Conversations AWS Lambda → Amazon DynamoDB
   - Returns conversation names scoped to actor_id

3. **Get Messages**: Frontend → Amazon API Gateway → Conversations AWS Lambda → Amazon Bedrock AgentCore Memory
   - Returns message history for session_id + actor_id
