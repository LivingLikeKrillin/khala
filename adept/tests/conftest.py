"""Shared test fixtures for adept."""

import pytest

from khala.adept.llm import FakeLLM


@pytest.fixture
def make_fake_llm():
    """Factory fixture: call with a responses list to get a scripted FakeLLM."""

    def _make(responses):
        return FakeLLM(responses=responses)

    return _make
