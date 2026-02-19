from typing import Dict, Type, Tuple, Optional
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import BaseRemediationAction


class RemediationActionFactory:
    """
    Registry and Factory for remediation strategies.
    Uses a (provider, action) tuple as the lookup key.
    """

    _registry: Dict[Tuple[str, str], Type[BaseRemediationAction]] = {}

    @classmethod
    def register(cls, provider: str, action: RemediationAction):
        """Decorator to register a strategy for a provider and action."""
        def wrapper(strategy_cls: Type[BaseRemediationAction]) -> Type[BaseRemediationAction]:
            cls._registry[(provider.lower(), action.value)] = strategy_cls
            return strategy_cls
        return wrapper

    @classmethod
    def get_strategy(cls, provider: str, action: RemediationAction) -> BaseRemediationAction:
        """
        Returns an instance of the strategy for the given provider and action.
        """
        strategy_cls = cls._registry.get((provider.lower(), action.value))
        if not strategy_cls:
            raise ValueError(f"No remediation strategy registered for {provider}/{action.value}")
        
        return strategy_cls()
