from khala.adept.models import Question


def test_question_default_id_is_empty():
    """A freshly-generated Question (before the store assigns an id) has id=''."""
    q = Question(text="why?")
    assert q.id == "" and q.text == "why?"
