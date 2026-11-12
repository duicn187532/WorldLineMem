"""Memory methods. Importing this package registers the built-in baselines.

To add a method (FadeMem, Zep, your own): create a module here with a class decorated by
``@register("name")`` that implements ``MemoryAdapter``, import it below, and select it
with ``[memory] method = "name"`` in a run config.
"""
from .base import REGISTRY, MemoryAdapter, Services, make_memory, register
from . import baselines  # noqa: F401  (registers no_memory, full_context, rag)

__all__ = ["REGISTRY", "MemoryAdapter", "Services", "make_memory", "register"]
