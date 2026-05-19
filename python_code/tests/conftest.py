"""Root-of-tests pytest configuration.

Registers CLI options that any test under :mod:`tests` may consume. Placed
at the testpath root so pytest discovers it during the initial CLI parse
(``pytest_addoption`` must live in a conftest that pytest sees before
collection).
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--duration",
        action="store",
        default=None,
        help=(
            "Override the duration (seconds) of long-running tests "
            "(e.g., tests/integration/test_long_run.py). Wins over "
            "PYJMRI_LONG_RUN_DURATION env var. Default in-test: 300."
        ),
    )
