from khala.adept.judge import grade
from khala.adept.llm import FakeLLM


def test_grade_parses_verdict_json():
    llm = FakeLLM(responses=['{"passed": true, "score": 0.8, "rationale": "ok"}'])
    v = grade("artifact text", [("Q", "A")], llm=llm)
    assert v.passed and v.score == 0.8


def test_grade_fails_closed_on_llm_error():
    class Boom:
        def generate(self, s, u):
            raise RuntimeError("llm down")

    v = grade("t", [("Q", "A")], llm=Boom())
    assert v.passed is False and v.score == 0.0  # fail-closed, never auto-pass


def test_grade_fails_closed_on_garbage_output():
    v = grade("t", [("Q", "A")], llm=FakeLLM(responses=["not json at all"]))
    assert v.passed is False and v.score == 0.0  # unparseable -> fail-closed


def test_grade_parses_fenced_json():
    llm = FakeLLM(responses=['```json\n{"passed": true, "score": 0.8, "rationale": "ok"}\n```'])
    v = grade("artifact text", [("Q", "A")], llm=llm)
    assert v.passed is True and v.score == 0.8
