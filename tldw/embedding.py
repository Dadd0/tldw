"""Sends texts to the OpenRouter embeddings endpoint and returns one vector per text."""

import requests

from tldw.errors import EMBEDDING, StageError

URL = "https://openrouter.ai/api/v1/embeddings"
MODEL_ID = "openai/text-embedding-3-small"
TIMEOUT_SECONDS = 120


def embed(texts: list[str], api_key: str) -> list[list[float]]:
    """Return one 1536-float vector per text, in input order."""
    try:
        response = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL_ID, "input": texts},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise StageError(
                EMBEDDING,
                "embedding",
                f"HTTP {response.status_code}: {response.text[:300]}",
            )
        data = response.json().get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise StageError(
                EMBEDDING, "embedding", f"expected {len(texts)} vectors in data"
            )
        by_index = {item["index"]: item["embedding"] for item in data}
        return [by_index[i] for i in range(len(texts))]
    except (
        requests.RequestException,
        ValueError,
        AttributeError,
        KeyError,
        TypeError,
    ) as e:
        raise StageError(EMBEDDING, "embedding", f"{type(e).__name__}: {e}") from e
