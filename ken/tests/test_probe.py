from ken.probe import make_questions
from ken.llm import FakeLLM


def test_make_questions_parses_lines():
    llm = FakeLLM(responses=["What is X?\nWhy Y?\nHow Z?"])
    qs = make_questions("artifact text", n=3, llm=llm)
    assert [q.text for q in qs] == ["What is X?", "Why Y?", "How Z?"]


def test_make_questions_strips_enumeration_and_bounds_to_n():
    llm = FakeLLM(
        responses=["1. What is X?\n2) Why Y?\n- How Z?\n* Extra A?\n4. Extra B?"]
    )
    qs = make_questions("artifact text", n=3, llm=llm)
    assert [q.text for q in qs] == ["What is X?", "Why Y?", "How Z?"]
