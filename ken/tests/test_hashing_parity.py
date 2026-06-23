import sys
import pathlib

import pytest

from ken.hashing import content_hash

SPEC_SRC = pathlib.Path(__file__).parents[2] / "specledger" / "src"  # tests->ken->khala root


@pytest.mark.parametrize("body", ["", "a\n", "x \r\ny\n\n", "한국어\n  trailing  \n"])
def test_parity_with_specledger(body):
    sys.path.insert(0, str(SPEC_SRC))
    from specledger.hashing import content_hash as spec_hash  # noqa: E402

    assert content_hash(body) == spec_hash(body)
