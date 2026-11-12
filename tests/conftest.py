from pathlib import Path

import pytest

from obscuretone_semantic_diff.context import build_context
from obscuretone_semantic_diff.models import load_pair
from obscuretone_semantic_diff.runners import IsolatedRunner

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = sorted((ROOT / "fixtures").rglob("manifest.json"))


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", help="Execute Node and Cargo sources"
    )
    parser.addoption("--integration-backend", choices=["docker", "local"], default="docker")
    parser.addoption(
        "--integration-timeout",
        type=float,
        default=120,
        help="Allow slow container startup/compilation on developer hosts",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-integration to execute sources"))


@pytest.fixture
def pair():
    return load_pair(ROOT / "fixtures/regressions/01-zero-count/manifest.json")


@pytest.fixture
def context():
    return build_context(IsolatedRunner())


@pytest.fixture(scope="session")
def integration_context(request):
    return build_context(
        IsolatedRunner(
            request.config.getoption("--integration-backend"),
            request.config.getoption("--integration-timeout"),
        )
    )
