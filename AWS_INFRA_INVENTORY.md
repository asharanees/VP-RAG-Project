# AWS Infrastructure Inventory (Cost-Min + High Quality)

## Naming standard

You asked for prefix "VP RAG Project". AWS resource names generally cannot contain spaces, so use this AWS-safe prefix in actual names:

- Display/business prefix: VP RAG Project
- AWS-safe prefix to implement: vp-rag-project

## Recommended resources (MVP)

### Core API and compute

- API Gateway HTTP API: `vp-rag-project-http-api`
- Lambda: `vp-rag-project-webhook-handler`
- Lambda: `vp-rag-project-rag-worker`
- Lambda: `vp-rag-project-pdf-ingest`

### Storage and retrieval

- S3 source document bucket: `vp-rag-project-source-<account-id>-<region>`
- S3 Vectors bucket: `vp-rag-project-vectors`
- S3 Vectors index: `vp-rag-project-pdf-index`
- DynamoDB table (chunks): `vp-rag-project-rag-chunks`

### Secrets

- Secrets Manager: `vp-rag-project/gemini/api`
- Secrets Manager: `vp-rag-project/meta/whatsapp`
- Secrets Manager: `vp-rag-project/meta/webhook_verify`

### Logs and monitoring

- CloudWatch log group: `/aws/lambda/vp-rag-project-webhook-handler`
- CloudWatch log group: `/aws/lambda/vp-rag-project-rag-worker`
- CloudWatch log group: `/aws/lambda/vp-rag-project-pdf-ingest`
- CloudWatch dashboard: `vp-rag-project-observability`
- CloudWatch alarm (errors): `vp-rag-project-lambda-errors`
- CloudWatch alarm (throttles): `vp-rag-project-lambda-throttles`

## Environment variables to configure

Set these on all Lambdas unless noted.

- `AWS_REGION=us-east-1` (or your target region)
- `CHUNKS_TABLE_NAME=vp-rag-project-rag-chunks`
- `S3_VECTORS_BUCKET=vp-rag-project-vectors`
- `S3_VECTORS_INDEX=vp-rag-project-pdf-index`
- `SOURCE_BUCKET_NAME=vp-rag-project-source-<account-id>-<region>`
- `SOURCE_PDF_KEY=source.pdf` (legacy; current ingest accepts any `.pdf` key)
- `GEMINI_SECRET_NAME=vp-rag-project/gemini/api`
- `META_SECRET_NAME=vp-rag-project/meta/whatsapp`
- `VERIFY_TOKEN_SECRET_NAME=vp-rag-project/meta/webhook_verify`
- `GENERATION_MODEL=gemini-2.5-flash`
- `EMBEDDING_MODEL=gemini-embedding-001`
- `TOP_K=5`
- `MIN_CONTEXT_CHUNKS=3`
- `MAX_CONTEXT_CHUNKS=5`
- `CHUNK_SIZE_TOKENS=700`
- `CHUNK_OVERLAP_TOKENS=100`
- `RAG_WORKER_FUNCTION=vp-rag-project-rag-worker` (needed by webhook Lambda)
- `WHATSAPP_GRAPH_VERSION=v22.0`
- `LOG_LEVEL=INFO`

### Optional quality tuning env vars

- `SYSTEM_INSTRUCTIONS=<your policy/instructions text>`
- `CUSTOM_PERSONA=<your persona style>`

### Lambda-specific minimum settings

- `vp-rag-project-webhook-handler`
  - Memory: 256 MB
  - Timeout: 10 sec
- `vp-rag-project-rag-worker`
  - Memory: 1024 MB
  - Timeout: 60 sec
- `vp-rag-project-pdf-ingest`
  - Memory: 1024 MB
  - Timeout: 300 sec

## Secrets Manager expected payloads

### Secret: `vp-rag-project/gemini/api`

```json
{
  "api_key": "YOUR_GEMINI_API_KEY"
}
```

### Secret: `vp-rag-project/meta/whatsapp`

```json
{
  "access_token": "YOUR_META_PERMANENT_TOKEN",
  "phone_number_id": "YOUR_PHONE_NUMBER_ID"
}
```

### Secret: `vp-rag-project/meta/webhook_verify`

```json
{
  "verify_token": "YOUR_META_WEBHOOK_VERIFY_TOKEN"
}
```

## Cost-minimum configuration (recommended defaults)

- API Gateway: HTTP API (already lowest-cost API Gateway tier for this use case).
- DynamoDB: on-demand billing (PAY_PER_REQUEST).
- S3: single source PDF + lifecycle rule for old artifacts (if added later).
- Lambdas:
  - Keep reserved concurrency low (`webhook=2`, `worker=2`, `ingest=1`) to cap spend.
  - Use ARM/Graviton runtime where possible for better price/performance.
- CloudWatch logs:
  - Set log retention to 14 days (avoid indefinite storage growth).
- Model strategy for quality/cost balance:
  - Default generation: `gemini-2.5-flash`.
  - Upgrade path: switch only `GENERATION_MODEL` to `gemini-3-flash-preview` when needed for better quality.
  - Keep retrieval quality high with `TOP_K=5` and passing best 3-5 chunks.

## High-output-quality practices (without big cost jump)

- Keep chunking at 700/100 and avoid very tiny chunks.
- Preserve `page_number` metadata and include it in prompt context.
- Enforce concise WhatsApp output in system instructions.
- If context is weak, respond transparently instead of hallucinating.
- Re-embed only on PDF change (already idempotent by file hash).

## Quick setup checklist

1. Create secrets with the exact names above.
2. Deploy stack with resource names using `vp-rag-project` prefix.
3. Set Lambda env vars exactly as listed.
4. Configure Meta webhook callback URL to API Gateway `/webhook`.
5. Upload one PDF to source bucket using any `.pdf` filename.
6. Send a WhatsApp message and verify `rag_worker` logs/context retrieval.
