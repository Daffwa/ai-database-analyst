"""Provider-neutral language-model adapter boundary."""

from backend.llm.adapters import BaseLLMAdapter, FakeLLMAdapter
from backend.llm.factory import create_llm_adapter

__all__ = ["BaseLLMAdapter", "FakeLLMAdapter", "create_llm_adapter"]
