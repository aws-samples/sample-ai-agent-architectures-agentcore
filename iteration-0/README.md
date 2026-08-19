# Iteration 0: Direct Browser → LangGraph Agent hosted on Amazon Bedrock AgentCore Runtime + OAuth using Amazon Cognito Auth

This first pattern shows the simplest setup that most tutorials show - a static HTML page that authenticates via OAuth and calls and agent directly. This example uses Amazon Cognito as the authorizor and Amazon Bedrock AgentCore Runtime as the hosted runtime for the agent. 

This pattern breaks down in production, and does not account for production level concerns for a web based AI agent. The following iterations fix the gaps introduced by this direct client to agent pattern.

## Architecture
![Direct client to agent architecture](../images/client_to_agent_arch.png)

## Components

- `cognito.yaml` - AWS CloudFormation template for Amazon Cognito User Pool and IAM role (shared across all iterations)
- `agent/` - LangGraph hello world agent with simple example tools
- `frontend/index.html` - Single HTML file with Amazon Cognito auth and chat UI

## Prerequisites

- AWS CLI configured with credentials (`aws configure`)
- AgentCore CLI installed (`pip install bedrock-agentcore-starter-toolkit`)
- `uv` and the `zip` CLI installed (required for Direct Code Deploy - see note in step 3)

> **Tip**: Verify your setup with `aws sts get-caller-identity` and `agentcore --version`

## Setup

### 1. Deploy Amazon Cognito (Shared Across All Iterations)

This Amazon Cognito stack is used by all iterations. It also creates an IAM execution role for Amazon Bedrock AgentCore. Deploy it once:

```bash
aws cloudformation deploy \
  --template-file cognito.yaml \
  --stack-name agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Get the outputs:
```bash
# User Pool ID
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
  --output text)

# Client ID
CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
  --output text)

# Cognito Domain
COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoDomain`].OutputValue' \
  --output text)

# Discovery URL (for agent OAuth config)
DISCOVERY_URL=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`OAuthDiscoveryUrl`].OutputValue' \
  --output text)

echo "User Pool ID: $USER_POOL_ID"
echo "Client ID: $CLIENT_ID"
echo "Cognito Domain: $COGNITO_DOMAIN"
echo "Discovery URL: $DISCOVERY_URL"
```

### 2. Create a Test User

```bash
# Create user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username <YOUR_USERNAME_HERE> \
  --temporary-password <YOUR_TEMP_PASSWORD_HERE> \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username <YOUR_USERNAME_HERE> \
  --password <YOUR_PASSWORD_HERE> \
  --permanent
```

> **Password Requirements**: Must be 8+ characters with uppercase, lowercase, numbers, and special characters 

### 3. Deploy the Agent

```bash
cd agent
agentcore configure
```

When prompted during configuration:
- **Entrypoint**: `agent.py`
- **Agent name**: `agent_0` (or press Enter for default)
- **Requirements file**: Press Enter to use detected `requirements.txt`
- **Deployment type**: `1` (Direct Code Deploy)
- **Python runtime**: `2` (PYTHON_3_11)
- **Execution role**: Press Enter to auto-create
- **S3 bucket**: Press Enter to auto-create
- **Configure OAuth authorizer?**: `yes`
- **OAuth discovery URL**: Use the `$DISCOVERY_URL` from step 1
- **Allowed OAuth client IDs**: Leave empty (press Enter)
- **Allowed OAuth audience**: Enter your `$CLIENT_ID` from step 1
- **Allowed OAuth scopes**: Leave empty (press Enter)
- **Custom claims**: Leave empty (press Enter)
- **Request header allowlist**: `no`
- **Memory**: `s` (skip)

> **Important**: Direct Code Deploy requires both `uv` and the `zip` CLI on your machine (`zip` doesn't ship with Windows - install it with `choco install zip` or use WSL). If either is missing, the CLI prints a brief warning and silently falls back to **container deployment**, which needs ECR permissions the execution role doesn't have, and the deploy fails with an ECR validation error.

> **Warning**: Don't enter your client ID at the "Allowed OAuth client IDs" prompt. The frontend sends a Cognito ID token, which carries the client ID in its `aud` claim (not `client_id`), so an agent configured with allowed client IDs rejects it with "Claim 'client_id' value mismatch". The client ID belongs in the **audience** field only.

Then deploy:
```bash
agentcore deploy
```

Note the Agent ARN from the output - you'll need it for the frontend config.

> **Tip**: Save the Agent Runtime ARN somewhere - it looks like `arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/agent_0-AbCdEf123`

### 4. Update Frontend Config

Edit `frontend/index.html` and update the CONFIG section:

```javascript
const CONFIG = {
  // Remove https:// from the Cognito domain
  cognitoDomain: 'apigw-agentcore-<YOUR_ACCOUNT_ID>.auth.<YOUR_REGION>.amazoncognito.com',
  clientId: '<YOUR_CLIENT_ID>',
  redirectUri: 'http://localhost:8000',
  agentRuntimeArn: 'arn:aws:bedrock-agentcore:<YOUR_REGION>:<YOUR_ACCOUNT_ID>:runtime/<YOUR_AGENT_RUNTIME_ID>'
};
```

> **Important**: 
> - `cognitoDomain` should NOT include `https://` - just the domain
> - `clientId` comes from the Cognito stack outputs (step 1)
> - `agentRuntimeArn` is the full ARN from `agentcore deploy` output

### 5. Run Frontend

```bash
cd frontend
python3 -m http.server 8000
```

Open http://localhost:8000 and login with `<YOUR_USERNAME_HERE>` / `<YOUR_PASSWORD_HERE>`

> **Troubleshooting**:
> - **"Claim 'aud' value mismatch"**: The `clientId` in your frontend CONFIG doesn't match what the agent expects. Double-check the CLIENT_ID from step 1.
> - **"Claim 'client_id' value mismatch"**: You entered the client ID at the "Allowed OAuth client IDs" prompt during `agentcore configure`. Re-run `agentcore configure` with that prompt left empty and the CLIENT_ID in the audience field instead, then `agentcore deploy`.
> - **Login redirects but nothing happens**: Check browser console for errors. Ensure `redirectUri` matches exactly (including trailing slash or lack thereof).
> - **CORS errors**: Make sure you're accessing via `http://localhost:8000`, not `127.0.0.1:8000`.

## How It Works

1. User clicks "Login" → redirected to Amazon Cognito Hosted UI
2. After login, Amazon Cognito redirects back with authorization code
3. Frontend exchanges code for tokens
4. Frontend calls Amazon Bedrock AgentCore Runtime with the OAuth token
5. Agent responds

## Files

```
iteration-0/
├── README.md
├── cognito.yaml          # Amazon Cognito User Pool (shared across iterations)
├── agent/
│   ├── agent.py          # LangGraph agent
│   └── requirements.txt
└── frontend/
    └── index.html        # Single-page app with Amazon Cognito auth
```

## Cleanup

```bash
# Delete agent
cd agent
agentcore destroy

# Delete Amazon Cognito (only if not using other iterations)
aws cloudformation delete-stack --stack-name agentcore-cognito
```
