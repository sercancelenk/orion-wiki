from typing import List, Dict, Any

from openai import OpenAI
from .models import LLMConfig


class ChatClient:
    """
    LLMConfig'e göre OpenAI-compatible bir chat client.
    Şimdilik sadece provider='openai' destekleniyor.
    """

    def __init__(self, config: LLMConfig):
        if config.provider == "openai":
            base_url = config.base_url or "https://api.openai.com/v1"
            self.client = OpenAI(
                base_url=base_url,
                api_key=config.api_key,
            )
            self.model = config.chat_model
        else:
            raise NotImplementedError(f"Provider not supported yet: {config.provider}")

    def chat(self, messages: List[Dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content