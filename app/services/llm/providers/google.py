from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.services.llm.providers.base import BaseProvider
from app.core.config import get_settings

class GoogleProvider(BaseProvider):
    def create_model(self, model: Optional[str] = None, api_key: Optional[str] = None) -> ChatGoogleGenerativeAI:
        settings = get_settings()
        key = api_key or settings.GOOGLE_API_KEY
        self.validate_api_key(key, "google")
        
        return ChatGoogleGenerativeAI(
            google_api_key=key,
            model=model or settings.GOOGLE_MODEL,
            temperature=0
        )
