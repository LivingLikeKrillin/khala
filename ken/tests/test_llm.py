from ken.llm import LLMClient, FakeLLM


def test_fake_llm_returns_scripted():
    llm = FakeLLM(responses=["Q1\nQ2"])
    assert llm.generate("sys", "user") == "Q1\nQ2"
    assert isinstance(llm, LLMClient)  # runtime_checkable Protocol
