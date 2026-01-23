from typing import Optional
from langchain_openai import ChatOpenAI
from app.services.llm.providers.base import BaseProvider
from app.core.config import get_settings

class OpenAIProvider(BaseProvider):
    def create_model(self, model: Optional[str] = None, api_key: Optional[str] = None) -> ChatOpenAI:
        settings = get_settings()
        key = api_key or settings.OPENAI_API_KEY
        self.validate_api_key(key, "openai")
        
        return ChatOpenAI(
            api_key=key,
            model=model or settings.OPENAI_MODEL,
            temperature=0
        )
