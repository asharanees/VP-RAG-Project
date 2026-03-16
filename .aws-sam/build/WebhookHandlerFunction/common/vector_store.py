from typing import Dict, List

import boto3

from common.logger import get_logger

logger = get_logger(__name__)


class S3VectorStore:
    def __init__(self, region: str, vector_bucket: str, vector_index: str):
        self.client = boto3.client("s3vectors", region_name=region)
        self.vector_bucket = vector_bucket
        self.vector_index = vector_index

    def upsert_vectors(self, vectors: List[Dict]) -> None:
        if not vectors:
            return
        self.client.put_vectors(
            vectorBucketName=self.vector_bucket,
            indexName=self.vector_index,
            vectors=vectors,
        )

    def query(self, embedding: List[float], top_k: int) -> List[str]:
        response = self.client.query_vectors(
            vectorBucketName=self.vector_bucket,
            indexName=self.vector_index,
            queryVector={"float32": embedding},
            topK=top_k,
        )
        results = response.get("vectors", [])
        chunk_ids: List[str] = []
        for item in results:
            chunk_id = item.get("key")
            if chunk_id:
                chunk_ids.append(chunk_id)
        logger.info("Vector query completed", extra={"extra": {"hits": len(chunk_ids)}})
        return chunk_ids
