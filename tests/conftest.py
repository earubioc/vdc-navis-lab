import pytest

from navis_mcp.bridge import Bridge
from navis_mcp.bridge.simulator import Simulator
from navis_mcp.bridge.transport import Endpoint
from navis_mcp.engine import analyze
from navis_mcp.profile import Profile
from navis_mcp.sample.generator import build
from navis_mcp.service import App


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVIS_MCP_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NAVIS_MCP_OUTPUT_ROOTS", raising=False)
    monkeypatch.delenv("NAVIS_MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("NAVIS_MCP_ENDPOINT", raising=False)


@pytest.fixture
def profile():
    return Profile.default()


@pytest.fixture
def tower():
    return build()[0]


@pytest.fixture
def result(tower, profile):
    return analyze(tower, profile)


@pytest.fixture
def sim():
    s = Simulator(job_delay=0.05)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def app(sim):
    return App(bridge=Bridge(lambda: [Endpoint.parse(sim.endpoint)]))
