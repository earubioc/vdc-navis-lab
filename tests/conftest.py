import importlib.util

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
    """The usual App: Community plus the Pro package when it is installed (with a test license)."""
    a = App(bridge=Bridge(lambda: [Endpoint.parse(sim.endpoint)]))
    return enable_pro(a) if PRO_AVAILABLE else a


# ------------------------------------------------------------------ Community and Pro modes
# The core suite runs without the Pro package (Community) and with it. Tests marked `pro` exercise capabilities that
# live in vdc-navis-lab-pro (write execution, CSV/BCF/PDF/handoff/JSON, image, document save, snapshot compare, packs);
# they are skipped when that package is not importable. The Pro package is private: it is never needed to run Community.
PRO_AVAILABLE = importlib.util.find_spec("vdc_navis_lab_pro") is not None
TEST_SECRET = bytes(range(32))  # a throwaway key for tests; the real signing key is never in any repository


def pytest_configure(config):
    config.addinivalue_line("markers", "pro: needs the vdc-navis-lab-pro package (skipped without it)")


def pytest_collection_modifyitems(config, items):
    if PRO_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="needs the Pro package (vdc-navis-lab-pro)")
    for item in items:
        if "pro" in item.keywords:
            item.add_marker(skip)


def enable_pro(app):
    """Register the Pro package on `app` with a test license (valid for years). Returns the app."""
    import datetime

    from vdc_navis_lab_pro import ed25519, license as lic, register
    today = datetime.date.today()
    token = lic.encode_token({"v": 1, "kind": "test", "id": "t0", "company": "tests", "issued": today.isoformat(),
                              "expires": (today + datetime.timedelta(days=3650)).isoformat()}, TEST_SECRET)
    register(None, app, public_keys=[ed25519.public_key(TEST_SECRET)], token=token)
    return app


@pytest.fixture
def community_app(sim):
    """An App with no plugin at all: what Community alone does."""
    return App(bridge=Bridge(lambda: [Endpoint.parse(sim.endpoint)]))
