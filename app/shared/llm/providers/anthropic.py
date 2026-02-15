from typing import Any, Optional, cast
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from app.shared.llm.providers.base import BaseProvider
from app.shared.core.config import get_settings


class AnthropicProvider(BaseProvider):
    def create_model(
        self, model: Optional[str] = None, api_key: Optional[str] = None
    ) -> BaseChatModel:
        settings = get_settings()
        key = api_key or settings.ANTHROPIC_API_KEY or settings.CLAUDE_API_KEY
        self.validate_api_key(key, "anthropic")

        anthropic_cls = cast(Any, ChatAnthropic)
        return cast(
            BaseChatModel,
            anthropic_cls(
                api_key=key,
                model=model or settings.CLAUDE_MODEL,
                temperature=0,
            ),
        )
