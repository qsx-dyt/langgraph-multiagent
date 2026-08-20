"""LLM factory.

Supports three providers:
- "mock" (default): deterministic rule-based responses, no API key needed.
  Perfect for running the whole workflow offline and for tests.
- "openai": any OpenAI-compatible chat API (OpenAI, DeepSeek, Qwen, Moonshot...)
  configured via OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL.
- "fake": langchain's FakeMessagesListChatModel (test-only).
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app import config


class MockChatModel(BaseChatModel):
    """Deterministic chat model with a pluggable responder for offline runs."""

    responder: object | None = None

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        responder = self.responder
        if responder is None:
            raise RuntimeError("MockChatModel requires a responder.")
        text = responder(messages, **kwargs)
        return self._create_response_with_usage(text)

    def _create_response_with_usage(self, text):
        from langchain_core.outputs import ChatGeneration, ChatResult

        message = AIMessage(content=text)
        return ChatResult(generations=[ChatGeneration(message=message)])


def get_chat_model() -> BaseChatModel:
    """Return the configured chat model."""
    if config.LLM_PROVIDER == "mock":
        from app.agents.mock_responses import MockResponder

        return MockChatModel(responder=MockResponder())
    if config.LLM_PROVIDER == "fake":
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

        return FakeMessagesListChatModel(responses=[AIMessage(content="ok")])
    # default: OpenAI-compatible chat model
    from langchain_openai import ChatOpenAI

    kwargs: dict = {"model": config.LLM_MODEL, "temperature": 0}
    if config.OPENAI_API_KEY:
        kwargs["api_key"] = config.OPENAI_API_KEY
    if config.OPENAI_BASE_URL:
        kwargs["base_url"] = config.OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def make_prompt(system: str) -> RunnableSequence:
    """Small helper: system prompt -> model -> plain string."""
    return ChatPromptTemplate.from_messages([("system", system), ("human", "{input}")]) | get_chat_model() | StrOutputParser()
