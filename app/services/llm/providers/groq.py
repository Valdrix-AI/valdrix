from typing import Optional
from langchain_groq import ChatGroq
from app.services.llm.providers.base import BaseProvider
from app.core.config import get_settings

class GroqProvider(BaseProvider):
    def create_model(self, model: Optional[str] = None, api_key: Optional[str] = None) -> ChatGroq:
        settings = get_settings()
        key = api_key or settings.GROQ_API_KEY
        self.validate_api_key(key, "groq")
        
        return ChatGroq(
            api_key=key,
            model=model or settings.GROQ_MODEL,
            temperature=0
        )
