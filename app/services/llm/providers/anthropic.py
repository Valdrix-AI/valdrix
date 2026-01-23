from typing import Optional
from langchain_anthropic import ChatAnthropic
from app.services.llm.providers.base import BaseProvider
from app.core.config import get_settings

class AnthropicProvider(BaseProvider):
    def create_model(self, model: Optional[str] = None, api_key: Optional[str] = None) -> ChatAnthropic:
        settings = get_settings()
        key = api_key or settings.ANTHROPIC_API_KEY or settings.CLAUDE_API_KEY
        self.validate_api_key(key, "anthropic")
        
        return ChatAnthropic(
            api_key=key,
            model=model or settings.CLAUDE_MODEL,
            temperature=0
        )
