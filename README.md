# WhatsApp AI Reporting Assistant

A serverless WhatsApp chatbot that answers questions about weekly PDF reports using structured JSON parsing and LLM generation — no embeddings, no vector search.

## Architecture

```
WhatsApp User
     │
     ▼
Meta Cloud API
     │  POST /webhook
     ▼
API Gateway (HTTP API)
     │
     ▼
webhook_handler (Lambda)
     │  async invoke
     ▼
rag_worker (Lambda)
     │                        │
     ▼                        ▼
Bedrock (Claude)         S3 structured JSON
(generation)             (structured_reports.json)

PDF Upload
     │  s3:ObjectCreated
     ▼
pdf_ingest (Lambda)
     │  parse PDF → structured JSON
     ▼
S3 (structured_reports.json)
```

## How it works

1. A PDF report is uploaded to S3. `pdf_ingest` parses it into structured JSON (weekly sections: executive summary, hot topics, RFx metrics, delayed projects, GCTO updates) and saves to `structured/structured_reports.json`.
2. When a WhatsApp message arrives, `webhook_handler` receives it and async-invokes `rag_worker`.
3. `rag_worker` classifies the query intent, loads the relevant weeks from the structured JSON, builds a focused prompt, and calls Bedrock (Claude) to generate a response.
4. The answer is sent back via the Meta WhatsApp Cloud API.

No embeddings, no vector store, no DynamoDB — just structured JSON on S3.

## Project structure

```
src/
  webhook_handler/app.py   # Receives Meta webhook, async-invokes rag_worker
  rag_worker/app.py        # Intent classification, context retrieval, LLM generation
  pdf_ingest/app.py        # PDF → structured JSON → S3
  common/
    structured_analyst.py  # Core parsing, intent classification, context building
    ai_router.py           # Routes between Bedrock and Gemini fallback
    bedrock_client.py      # AWS Bedrock (Claude) client
    gemini_client.py       # Google Gemini fallback client
    whatsapp_client.py     # Meta WhatsApp Cloud API client
    secrets.py             # Reads secrets from Lambda env vars
    settings.py            # Loads config from env vars
    pdf_utils.py           # PDF page extraction
    logger.py              # Structured JSON logging
template.yaml              # AWS SAM template
```

## Supported query intents

| Intent | Example queries |
|---|---|
| `weekly_summary` | "Summary of overall updates from last 4 weeks" |
| `hot_topics` | "What are the major hot topics?" |
| `rfx_metrics` | "Progress comparisons across different weeks" |
| `delayed_projects` | "Identification of delayed or pending initiatives from last 3 months" |
| `gcto_updates` | "What is the GCTO update?" |
| `topic_search` | "What is the update on NTN?" (cross-section keyword search) |
| greeting | "Hi", "Hello", "Salam" → welcome message, no LLM call |

## Secrets

Secrets are passed as Lambda environment variables (JSON strings). No Secrets Manager required.

| Env var | Content |
|---|---|
| `VP_RAG_PROJECT_META_WHATSAPP` | `{"access_token": "...", "phone_number_id": "..."}` |
| `VP_RAG_PROJECT_META_WEBHOOK_VERIFY` | `{"verify_token": "..."}` |
| `VP_RAG_PROJECT_GEMINI_API` | `{"api_key": "..."}` (optional, used as fallback) |

## Deploy

Prerequisites: AWS CLI, SAM CLI, Python 3.12.

```bash
sam build

sam deploy \
  --stack-name vp-rag-project \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "MetaWhatsappSecret={\"access_token\":\"TOKEN\",\"phone_number_id\":\"ID\"}" \
    "WebhookVerifySecret={\"verify_token\":\"TOKEN\"}" \
    "GeminiApiSecret={\"api_key\":\"KEY\"}"
```

After deploy, copy the `WebhookUrl` output into your Meta app webhook callback URL and set the verify token to match `WebhookVerifySecret`.

## Ingest a new PDF report

```bash
aws s3 cp "your-report.pdf" s3://vp-rag-project-source-<account>-<region>/source.pdf
```

`pdf_ingest` triggers automatically on upload. Monitor with:

```bash
aws logs tail /aws/lambda/vp-rag-project-pdf-ingest --follow
```

## Runtime configuration

Key environment variables (set in `template.yaml` or override at deploy time):

| Variable | Default | Description |
|---|---|---|
| `PRIMARY_PROVIDER` | `bedrock` | `bedrock` or `gemini` |
| `GENERATION_MODEL` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Bedrock model ID |
| `FALLBACK_GENERATION_MODEL` | `gemini-2.5-flash` | Gemini fallback model |
| `STRUCTURED_REPORTS_KEY` | `structured/structured_reports.json` | S3 key for parsed report data |
