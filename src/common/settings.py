import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
    aws_region: str
    chunks_table_name: str
    s3_vectors_bucket: str
    s3_vectors_index: str
    source_bucket_name: str
    source_pdf_key: str
    structured_reports_key: str
    primary_provider: str
    gemini_secret_name: str
    meta_secret_name: str
    verify_token_secret_name: str
    generation_model: str
    embedding_model: str
    fallback_generation_model: str
    fallback_embedding_model: str
    top_k: int
    min_context_chunks: int
    max_context_chunks: int
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    worker_function_name: str
    persona: str
    system_instructions: str
    whatsapp_graph_version: str
    tavily_api_key: str


DEFAULT_SYSTEM_INSTRUCTIONS = (
    "You are a helpful assistant answering questions using only provided document context. "
    "If context is insufficient, say so transparently and suggest what is missing. "
    "Keep the answer concise and WhatsApp-friendly."
)

DEFAULT_PERSONA = "Professional, concise, trustworthy assistant."


def load_settings() -> AppSettings:
    return AppSettings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        chunks_table_name=os.getenv("CHUNKS_TABLE_NAME", "vp-rag-project-rag-chunks"),
        s3_vectors_bucket=os.getenv("S3_VECTORS_BUCKET", "vp-rag-project-vectors"),
        s3_vectors_index=os.getenv("S3_VECTORS_INDEX", "vp-rag-project-pdf-index"),
        source_bucket_name=os.getenv("SOURCE_BUCKET_NAME", "vp-rag-project-source-dev"),
        source_pdf_key=os.getenv("SOURCE_PDF_KEY", "source.pdf"),
        structured_reports_key=os.getenv("STRUCTURED_REPORTS_KEY", "structured/structured_reports.json"),
        primary_provider=os.getenv("PRIMARY_PROVIDER", "bedrock").lower(),
        gemini_secret_name=os.getenv("GEMINI_SECRET_NAME", "vp-rag-project/gemini/api"),
        meta_secret_name=os.getenv("META_SECRET_NAME", "vp-rag-project/meta/whatsapp"),
        verify_token_secret_name=os.getenv("VERIFY_TOKEN_SECRET_NAME", "vp-rag-project/meta/webhook_verify"),
        # Convenience direct-env overrides (used when Secrets Manager is not in use)
        generation_model=os.getenv("GENERATION_MODEL", "us.anthropic.claude-3-5-haiku-20241022-v1:0"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"),
        fallback_generation_model=os.getenv("FALLBACK_GENERATION_MODEL", "gemini-2.5-flash"),
        fallback_embedding_model=os.getenv("FALLBACK_EMBEDDING_MODEL", "gemini-embedding-001"),
        top_k=int(os.getenv("TOP_K", "5")),
        min_context_chunks=int(os.getenv("MIN_CONTEXT_CHUNKS", "3")),
        max_context_chunks=int(os.getenv("MAX_CONTEXT_CHUNKS", "5")),
        chunk_size_tokens=int(os.getenv("CHUNK_SIZE_TOKENS", "700")),
        chunk_overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "100")),
        worker_function_name=os.getenv("RAG_WORKER_FUNCTION", "vp-rag-project-rag-worker"),
        persona=os.getenv("CUSTOM_PERSONA", DEFAULT_PERSONA),
        system_instructions=os.getenv("SYSTEM_INSTRUCTIONS", DEFAULT_SYSTEM_INSTRUCTIONS),
        whatsapp_graph_version=os.getenv("WHATSAPP_GRAPH_VERSION", "v22.0"),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
    )
