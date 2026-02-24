from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel


class BaseProvider(ABC):
    """
    Standard interface for all LLM providers in Valdrix.
    Ensures consistent API key validation and model creation.
    """

    @abstractmethod
    def create_model(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> BaseChatModel:
        """Create a LangChain compatible ChatModel."""
        raise NotImplementedError()

    def validate_api_key(self, api_key: Optional[str], provider_name: str) -> None:
        """Standardized API key validation logic."""
        if not api_key:
            raise ValueError(f"{provider_name.upper()}_API_KEY not configured")

        placeholders = ["sk-xxx", "change-me", "your-key-here", "default_key"]
        if any(p in api_key.lower() for p in placeholders):
            raise ValueError(
                f"Invalid API key for {provider_name}: Key contains a placeholder value."
            )

        if len(api_key) < 20:
            raise ValueError(f"Invalid API key for {provider_name}: Key is too short.")
