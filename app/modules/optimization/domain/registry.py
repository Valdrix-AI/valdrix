from typing import Callable, DefaultDict, List, Type
from collections import defaultdict
from app.modules.optimization.domain.plugin import ZombiePlugin


class ZombiePluginRegistry:
    """
    Central registry for zombie detection plugins.
    Decouples plugins from the detector logic, allowing for easy expansion
    per provider without modifying core code.
    """

    _plugins: DefaultDict[str, List[Type[ZombiePlugin]]] = defaultdict(list)

    @classmethod
    def register(
        cls, provider: str
    ) -> Callable[[Type[ZombiePlugin]], Type[ZombiePlugin]]:
        """Decorator to register a plugin for a specific provider."""

        def wrapper(plugin_cls: Type[ZombiePlugin]) -> Type[ZombiePlugin]:
            cls._plugins[provider].append(plugin_cls)
            return plugin_cls

        return wrapper

    @classmethod
    def get_plugins_for_provider(cls, provider: str) -> List[ZombiePlugin]:
        """Instantiates and returns all plugins for a given provider."""
        return [plugin_cls() for plugin_cls in cls._plugins.get(provider, [])]


# Singleton instance for global access
registry = ZombiePluginRegistry()
