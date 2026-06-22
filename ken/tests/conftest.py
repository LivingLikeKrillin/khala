"""Shared test fixtures for ken."""

import pytest

from ken.llm import FakeLLM


@pytest.fixture
def make_fake_llm():
    """Factory fixture: call with a responses list to get a scripted FakeLLM."""

    def _make(responses):
        return FakeLLM(responses=responses)

    return _make
