from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.shared.llm.providers.base import BaseProvider
from app.shared.core.config import get_settings


class GoogleProvider(BaseProvider):
    def create_model(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> ChatGoogleGenerativeAI:
        settings = get_settings()
        key = api_key or settings.GOOGLE_API_KEY
        self.validate_api_key(key, "google")

        kwargs = {
            "google_api_key": key,
            "model": model or settings.GOOGLE_MODEL,
            "temperature": 0,
        }
        if isinstance(max_output_tokens, int) and max_output_tokens > 0:
            kwargs["max_output_tokens"] = max_output_tokens

        return ChatGoogleGenerativeAI(**kwargs)
