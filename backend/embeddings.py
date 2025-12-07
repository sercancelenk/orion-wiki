from typing import List

from openai import OpenAI
from .models import LLMConfig
from .config import EMBEDDING_BATCH_SIZE


class EmbeddingClient:
    """
    LLMConfig'e göre OpenAI-compatible embedding client.
    Büyük repository'lerde token limitini aşmamak için
    embedding isteklerini batch'lere bölüyoruz.
    """

    def __init__(self, config: LLMConfig):
        if config.provider == "openai":
            base_url = config.base_url or "https://api.openai.com/v1"
            self.client = OpenAI(
                base_url=base_url,
                api_key=config.api_key,
            )
            self.model = config.embed_model
        else:
            raise NotImplementedError(f"Provider not supported yet: {config.provider}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        texts listesini EMBEDDING_BATCH_SIZE büyüklüğünde parçalara bölerek
        /embeddings endpoint'ine gönderir. Böylece toplam token limiti aşılmaz.
        """
        all_embeddings: List[List[float]] = []
        n = len(texts)
        if n == 0:
            return all_embeddings

        for start in range(0, n, EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + EMBEDDING_BATCH_SIZE]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            # OpenAI sıralamayı korur, biz de direkt extend ediyoruz
            batch_embeddings = [d.embedding for d in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings