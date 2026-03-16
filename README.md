# WhatsApp RAG Assistant on AWS (Python)

This project implements a 3-Lambda architecture for WhatsApp + RAG:

1. `webhook_handler` receives Meta Cloud API webhook events.
2. `rag_worker` retrieves context from indexed PDF chunks and answers with Gemini.
3. `pdf_ingest` indexes one source PDF into S3 Vectors + DynamoDB metadata.

## Features aligned to your requirements

- Python implementation
- Configurable models via environment variables
  - Default generation model: `gemini-2.5-flash`
  - Default embedding model: `gemini-embedding-001`
  - Easy switch to `gemini-3-flash-preview` by changing `GENERATION_MODEL`
- Secrets in AWS Secrets Manager
- Structured JSON logging
- Idempotent PDF ingestion via SHA-256 document hash marker
- Safely ignores non-message/non-text webhook events
- Concise WhatsApp-friendly response style
- Transparent fallback when context is insufficient (prompt-level enforcement)
- No PDF re-embedding at query time (query embedding only)

## Project structure

- `src/webhook_handler/app.py`
- `src/rag_worker/app.py`
- `src/pdf_ingest/app.py`
- `src/common/*`
- `template.yaml` (AWS SAM)
- `AWS_INFRA_INVENTORY.md` (resource naming + env vars + secrets payloads)

## Secrets Manager expected payloads

### `vp-rag-project/gemini/api`
```json
{
  "api_key": "YOUR_GEMINI_API_KEY"
}
```

### `vp-rag-project/meta/whatsapp`
```json
{
  "access_token": "YOUR_META_PERMANENT_TOKEN",
  "phone_number_id": "YOUR_PHONE_NUMBER_ID"
}
```

### `vp-rag-project/meta/webhook_verify`
```json
{
  "verify_token": "YOUR_META_WEBHOOK_VERIFY_TOKEN"
}
```

## DynamoDB schema

Table name (default): `vp-rag-project-rag-chunks`

- PK: `chunk_id`
- Attributes:
  - `document_id`
  - `chunk_index`
  - `page_number`
  - `chunk_text`
  - `source_s3_key`
  - `token_count`
  - `created_at`

Idempotency marker item:
- `chunk_id = DOC#{document_sha256}`

## Retrieval and chunking defaults

- `CHUNK_SIZE_TOKENS=700`
- `CHUNK_OVERLAP_TOKENS=100`
- `TOP_K=5`
- Context to generation: best 3-5 chunks (`MIN_CONTEXT_CHUNKS=3`, `MAX_CONTEXT_CHUNKS=5`)

## Deploy (AWS SAM)

Prereqs:
- AWS CLI configured
- SAM CLI installed
- Python 3.12

```bash
sam build
sam deploy --guided
```

After deploy:
- Copy `WebhookUrl` output into Meta app webhook callback URL.
- Set verify token in Meta to match `vp-rag-project/meta/webhook_verify` secret.
- Upload your source document as any `.pdf` filename into the created source bucket.

## Runtime configuration

Change generation model without code changes:
- Set Lambda env var `GENERATION_MODEL=gemini-3-flash-preview` (or another supported model).

## Notes

- S3 Vectors API is used via boto3 `s3vectors` client (`PutVectors`, `QueryVectors`).
- Ensure your AWS account/region supports S3 Vectors and permissions are enabled.
- For production, consider adding retries + DLQ and explicit request signing/audit controls.
