from typing import Any, Optional, cast
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from app.shared.llm.providers.base import BaseProvider
from app.shared.core.config import get_settings


class OpenAIProvider(BaseProvider):
    def create_model(
        self, model: Optional[str] = None, api_key: Optional[str] = None
    ) -> BaseChatModel:
        settings = get_settings()
        key = api_key or settings.OPENAI_API_KEY
        self.validate_api_key(key, "openai")

        openai_cls = cast(Any, ChatOpenAI)
        return cast(
            BaseChatModel,
            openai_cls(
                api_key=key,
                model=model or settings.OPENAI_MODEL,
                temperature=0,
            ),
        )
