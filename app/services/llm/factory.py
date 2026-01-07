from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()

class LLMFactory:
  @staticmethod
  def create(provider: str = "openai") -> BaseChatModel:
    settings = get_settings()
    logger.info("Initializing LLM", provider=provider)

    if provider == "openai":
      return ChatOpenAI(
          api_key=settings.OPENAI_API_KEY, 
          model=settings.OPENAI_MODEL,
          temperature=0
      )

    elif provider == "claude":
      return ChatAnthropic(
          api_key=settings.CLAUDE_API_KEY, 
          model=settings.CLAUDE_MODEL,
          temperature=0
      )
      
    elif provider == "google":
      return ChatGoogleGenerativeAI(
          google_api_key=settings.GOOGLE_API_KEY, 
          model=settings.GOOGLE_MODEL,
          temperature=0
      )
      
    elif provider == "groq":
      return ChatGroq(
          api_key=settings.GROQ_API_KEY, 
          model=settings.GROQ_MODEL,
          temperature=0
      )
    raise ValueError(f"Unsupported provider: {provider}")