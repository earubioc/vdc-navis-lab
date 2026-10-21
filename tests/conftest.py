import pytest

from vdc_navis_lab.bridge import Bridge
from vdc_navis_lab.bridge.simulator import Simulator
from vdc_navis_lab.bridge.transport import Endpoint
from vdc_navis_lab.engine import analyze
from vdc_navis_lab.profile import Profile
from vdc_navis_lab.sample.generator import build
from vdc_navis_lab.service import App


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("VDC_NAVIS_LAB_OUTPUT_ROOTS", raising=False)
    monkeypatch.delenv("VDC_NAVIS_LAB_READ_ONLY", raising=False)
    monkeypatch.delenv("VDC_NAVIS_LAB_ENDPOINT", raising=False)


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
