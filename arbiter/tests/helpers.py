# tests/helpers.py — shared test doubles (importable because pythonpath includes "tests")
class FakeCritic:
    def __init__(self, issues=None, boom=False):
        self.issues = (issues if issues is not None
                       else [("missing-invariant", "high", "no invariant")])
        self.boom = boom
        self.seen = None

    def find_issues(self, body, linked_adrs, rubric):
        if self.boom:
            raise RuntimeError("api down")
        self.seen = (body, linked_adrs, rubric)
        return self.issues
