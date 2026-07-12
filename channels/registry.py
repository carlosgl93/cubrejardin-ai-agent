"""Channel adapter registry.

Adapters are registered exactly once at application startup (in main.py
import path). The registry is treated as immutable after startup — do NOT
call register_adapter at request time. There is no locking because the
write path runs before any worker begins serving requests.
"""

from channels.base import ChannelAdapter

_registry: dict[str, ChannelAdapter] = {}


def register_adapter(adapter: ChannelAdapter) -> None:
    if adapter.name in _registry:
        raise ValueError(f"Adapter '{adapter.name}' already registered")
    _registry[adapter.name] = adapter


def get_adapter(name: str) -> ChannelAdapter:
    if name not in _registry:
        raise KeyError(f"No adapter registered for channel '{name}'")
    return _registry[name]


def known_channels() -> list[str]:
    return list(_registry.keys())