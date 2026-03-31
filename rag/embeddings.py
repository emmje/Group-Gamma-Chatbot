from typing import List

from fastembed import TextEmbedding


class EmbeddingModel:
    def __init__(self, model_name: str) -> None:
        # fastembed uses ONNX Runtime instead of PyTorch — much lower memory footprint.
        # Map the sentence-transformers model name to the fastembed equivalent.
        _MODEL_MAP = {
            "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
        }
        fastembed_name = _MODEL_MAP.get(model_name, model_name)
        self.model = TextEmbedding(model_name=fastembed_name)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            sample = list(self.model.embed(["hello"]))[0]
            self._dimension = len(sample)
        return self._dimension

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [list(map(float, emb)) for emb in self.model.embed(texts)]

    def embed_query(self, text: str) -> List[float]:
        return list(map(float, list(self.model.embed([text]))[0]))
