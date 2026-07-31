from __future__ import annotations

from typing import Any, Callable, Dict, List

_REGISTRY: Dict[str, Callable[..., Any]] = {}
_DESCRIPTIONS: Dict[str, str] = {}


def register_strategy(name: str, description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Class/factory decorator: registers a strategy under `name` so the dashboard,
    backtester, and live runner can all look it up by name instead of importing a
    specific strategy class directly. Adding a new strategy means adding a new
    registered factory here — no changes to the dashboard/backtest/live-runner code."""

    def decorator(factory: Callable[..., Any]) -> Callable[..., Any]:
        if name in _REGISTRY:
            raise ValueError(f"Strategy already registered: {name!r}")
        _REGISTRY[name] = factory
        _DESCRIPTIONS[name] = description
        return factory

    return decorator


def get_strategy(name: str, **kwargs: Any) -> Any:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy {name!r}. Available: {list_strategies()}")
    return _REGISTRY[name](**kwargs)


def list_strategies() -> List[str]:
    return sorted(_REGISTRY.keys())


def describe_strategy(name: str) -> str:
    return _DESCRIPTIONS.get(name, "")
