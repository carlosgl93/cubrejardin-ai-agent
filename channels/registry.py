from channels.base import ChannelAdapter

_registry: dict[str, ChannelAdapter] = {}


def register_adapter(adapter: ChannelAdapter) -> None:
    _registry[adapter.name] = adapter


def get_adapter(name: str) -> ChannelAdapter:
    if name not in _registry:
        raise KeyError(f"No adapter registered for channel '{name}'")
    return _registry[name]


def known_channels() -> list[str]:
    return list(_registry.keys())