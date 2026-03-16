import json
import os
from typing import Any, Dict

# Secret values are stored directly in Lambda environment variables.
# Each secret is a JSON string in an env var named after the secret path
# with slashes replaced by underscores and uppercased.
# e.g. "vp-rag-project/meta/whatsapp" -> "VP_RAG_PROJECT_META_WHATSAPP"

def _env_key(secret_name: str) -> str:
    return secret_name.upper().replace("/", "_").replace("-", "_")


def get_secret(secret_name: str) -> Dict[str, Any]:
    env_key = _env_key(secret_name)
    raw = os.environ.get(env_key, "")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Plain string value — wrap it
            return {"value": raw}
    return {}
