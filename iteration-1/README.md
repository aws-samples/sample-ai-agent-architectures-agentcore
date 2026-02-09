# Iteration 1: Amazon API Gateway + Amazon Bedrock AgentCore Runtime (OAuth Pass-through)

Amazon API Gateway in front of Amazon Bedrock AgentCore Runtime with Amazon Cognito authentication and AWS WAF protection.

## Architecture

![OAuth integration with AgentCore Runtime](../images/oauth_waf_apigateway_agent.png)


## Key Concepts

- **OAuth token pass-through**: Same Amazon Cognito JWT validates at both Amazon API Gateway AND Amazon Bedrock AgentCore
- **AWS WAF protection**: Rate limiting per IP
- **Security note**: User JWT works for both API and agent directly - see Iteration 2 for the fix

## Prerequisites

**Amazon Cognito must be deployed first** (from iteration-0):

```bash
cd ../iteration-0
aws cloudformation deploy \
  --template-file cognito.yaml \
  --stack-name agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

> **Note**: If you already deployed Amazon Cognito for iteration-0, skip this step.

If you haven't created a test user yet:
```bash
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
  --output text)

aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username <YOUR_USERNAME_HERE> \
  --temporary-password <YOUR_TEMP_PASSWORD_HERE> \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username <YOUR_USERNAME_HERE> \
  --password <YOUR_PASSWORD_HERE> \
  --permanent
```

> **Password Requirements**: Must be 8+ characters with uppercase, lowercase, numbers, and special characters.

## Project Structure

```
iteration-1/
├── README.md
├── api-gateway.yaml         # Amazon API Gateway + AWS WAF CloudFormation template
├── agent/
│   ├── agent.py             # LangGraph agent
│   └── requirements.txt
└── frontend/
    └── index.html           # Single-page chat UI
```

## Deployment

### 1. Get Amazon Cognito Outputs

```bash
CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
  --output text)

DISCOVERY_URL=$(aws cloudformation describe-stacks \
  --stack-name agentcore-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`OAuthDiscoveryUrl`].OutputValue' \
  --output text)

echo "Client ID: $CLIENT_ID"
echo "Discovery URL: $DISCOVERY_URL"
```

### 2. Deploy Agent with OAuth

```bash
cd agent
agentcore configure
```
When prompted during configuration:
- **Entrypoint**: `agent.py`
- **Agent name**: `agent_1` (or press Enter for default)
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

Then run:

```bash
agentcore deploy
```

Note the Runtime ID from the output.

> **Important**: You need the Runtime ID (not the full ARN) for the next step. It looks like `agent_1-AbCdEf123` (the part after `runtime/` in the ARN).

### 3. Deploy Amazon API Gateway

```bash
aws cloudformation deploy \
  --template-file api-gateway.yaml \
  --stack-name agentcore-api \
  --parameter-overrides \
    AgentRuntimeId=<YOUR_AGENT_RUNTIME_ID>  \
    CognitoStackName=agentcore-cognito \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

> **⚠️ Common Error**: Use only the Runtime ID (e.g., `agent_1-AbCdEf123`), NOT the full ARN. Using the full ARN will cause a 404 "UnknownOperationException" error.

Get the Amazon API Gateway endpoint:
```bash
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name agentcore-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)
echo "API Endpoint: $API_ENDPOINT"
```

### 4. Update Frontend Config

Edit `frontend/index.html` and update the CONFIG section:

```javascript
const CONFIG = {
  cognitoDomain: 'apigw-agentcore-<YOUR_ACCOUNT_ID>.auth.<YOUR_REGION>.amazoncognito.com',
  clientId: '<YOUR_CLIENT_ID>',
  redirectUri: 'http://localhost:8000',
  apiEndpoint: 'https://<YOUR_API_ID>.execute-api.<YOUR_REGION>.amazonaws.com/prod'
};
```

> **Tip**: You can get all these values programmatically:
> ```bash
> # Cognito domain (remove https://)
> aws cloudformation describe-stacks --stack-name agentcore-cognito \
>   --query 'Stacks[0].Outputs[?OutputKey==`CognitoDomain`].OutputValue' --output text
> 
> # Client ID
> aws cloudformation describe-stacks --stack-name agentcore-cognito \
>   --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' --output text
> ```

### 5. Test

```bash
cd frontend
python3 -m http.server 8000
```

Open http://localhost:8000 and login with `<YOUR_USERNAME_HERE>` / `<YOUR_PASSWORD_HERE>`

> **Troubleshooting**:
> - **404 "UnknownOperationException"**: You used the full ARN instead of just the Runtime ID when deploying Amazon API Gateway. Delete the stack and redeploy with just the ID.
> - **401 Unauthorized**: Token expired or invalid. Try logging out and back in.
> - **CORS errors**: Ensure you're using `http://localhost:8000` (not 127.0.0.1).

## Cleanup

```bash
aws cloudformation delete-stack --stack-name agentcore-api
cd agent && agentcore destroy
# Don't delete Amazon Cognito if using other iterations
```
