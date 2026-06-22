from ken.probe import make_questions
from ken.llm import FakeLLM


def test_make_questions_parses_lines():
    llm = FakeLLM(responses=["What is X?\nWhy Y?\nHow Z?"])
    qs = make_questions("artifact text", n=3, llm=llm)
    assert [q.text for q in qs] == ["What is X?", "Why Y?", "How Z?"]
