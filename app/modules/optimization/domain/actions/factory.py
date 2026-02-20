from __future__ import annotations

from typing import Callable, Dict, Tuple, Type

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import BaseRemediationAction
from app.shared.core.provider import normalize_provider


class RemediationActionFactory:
    """
    Registry and Factory for remediation strategies.
    Uses a (provider, action) tuple as the lookup key.
    """

    _registry: Dict[Tuple[str, str], Type[BaseRemediationAction]] = {}

    @staticmethod
    def _provider_key(provider: str) -> str:
        normalized = normalize_provider(provider)
        if normalized:
            return normalized
        fallback = str(provider or "").strip().lower()
        if not fallback:
            raise ValueError("Provider is required to resolve remediation strategy")
        return fallback

    @classmethod
    def register(
        cls, provider: str, action: RemediationAction
    ) -> Callable[[Type[BaseRemediationAction]], Type[BaseRemediationAction]]:
        """Decorator to register a strategy for a provider and action."""

        def wrapper(strategy_cls: Type[BaseRemediationAction]) -> Type[BaseRemediationAction]:
            provider_key = cls._provider_key(provider)
            registry_key = (provider_key, action.value)
            existing = cls._registry.get(registry_key)
            # Allow idempotent module reload registration, but reject conflicting overrides.
            if existing is not None and existing is not strategy_cls:
                raise ValueError(
                    f"Duplicate remediation strategy registration for {provider_key}/{action.value}: "
                    f"{existing.__name__} vs {strategy_cls.__name__}"
                )
            cls._registry[registry_key] = strategy_cls
            return strategy_cls
        return wrapper

    @classmethod
    def get_strategy(
        cls, provider: str, action: RemediationAction
    ) -> BaseRemediationAction:
        """
        Returns an instance of the strategy for the given provider and action.
        """
        provider_key = cls._provider_key(provider)
        strategy_cls = cls._registry.get((provider_key, action.value))
        if not strategy_cls:
            available = sorted(
                f"{p}/{a}" for (p, a) in cls._registry.keys() if p == provider_key
            )
            suffix = (
                f" Available for provider '{provider_key}': {', '.join(available)}"
                if available
                else " No actions registered for this provider."
            )
            raise ValueError(
                f"No remediation strategy registered for {provider_key}/{action.value}.{suffix}"
            )

        return strategy_cls()
