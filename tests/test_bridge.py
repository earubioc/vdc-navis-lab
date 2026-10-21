import json
import socket

import pytest

from vdc_navis_lab.bridge import Bridge, BridgeError
from vdc_navis_lab.bridge.simulator import Simulator
from vdc_navis_lab.bridge.transport import Endpoint, discover


def test_endpoint_parsing_refuses_non_loopback_tcp():
    assert str(Endpoint.parse("pipe://vdc-navis-lab.123")) == "pipe://vdc-navis-lab.123"
    with pytest.raises(BridgeError):
        Endpoint.parse("tcp://192.168.1.5:9000")
    with pytest.raises(BridgeError):
        Endpoint.parse("http://x")


def test_instances_hello_and_unreachable(sim):
    b = Bridge(lambda: [Endpoint.parse(sim.endpoint), Endpoint.parse("tcp://127.0.0.1:1")])
    found, dead = b.instances()
    assert len(found) == 1 and found[0]["instance_id"] == sim.instance_id and dead == ["tcp://127.0.0.1:1"]
    assert "clash.apply" in found[0]["methods"]


def test_no_instance_is_an_actionable_error():
    with pytest.raises(BridgeError) as exc:
        Bridge(lambda: []).resolve()
    assert exc.value.code == "no_instance" and "simulator" in exc.value.hint


def test_reads_pick_newest_but_writes_refuse_to_guess():
    a, b = Simulator(), Simulator()
    ea, eb = Endpoint.parse(a.start()), Endpoint.parse(b.start())
    try:
        br = Bridge(lambda: [ea, eb])
        ep, info, note = br.resolve(for_write=False)
        assert info["instance_id"] in (a.instance_id, b.instance_id) and "most recent" in note
        with pytest.raises(BridgeError) as exc:
            br.resolve(for_write=True)
        assert exc.value.code == "ambiguous_instance" and len(exc.value.data) == 2
        br.select(a.instance_id)
        assert br.resolve(for_write=True)[1]["instance_id"] == a.instance_id
    finally:
        a.stop(), b.stop()


def test_pinned_instance_that_vanishes_is_reported(sim):
    b = Bridge(lambda: [Endpoint.parse(sim.endpoint)])
    b.pinned_id = "sim-gone"
    with pytest.raises(BridgeError, match="gone"):
        b.resolve()


def test_jobs_complete_and_return_results(sim):
    b = Bridge(lambda: [Endpoint.parse(sim.endpoint)])
    ep = Endpoint.parse(sim.endpoint)
    job = b.call_at(ep, "clash.export", {})
    status = b.wait_job(ep, job["job_id"], 5)
    assert status["state"] == "completed"
    assert len(b.call_at(ep, "job.result", {"job_id": job["job_id"]})["clashes"]) == 54


def test_unfinished_job_result_is_refused_and_cancel_works():
    s = Simulator(job_delay=5)
    ep = Endpoint.parse(s.start())
    try:
        b = Bridge(lambda: [ep])
        job = b.call_at(ep, "clash.export", {})
        with pytest.raises(BridgeError) as exc:
            b.call_at(ep, "job.result", {"job_id": job["job_id"]})
        assert exc.value.code == "busy"
        assert b.call_at(ep, "job.cancel", {"job_id": job["job_id"]})["state"] == "cancelled"
    finally:
        s.stop()


def test_apply_requires_matching_fingerprint_and_is_idempotent(sim):
    b = Bridge(lambda: [Endpoint.parse(sim.endpoint)])
    ep = Endpoint.parse(sim.endpoint)
    fp = sim.fingerprint
    with pytest.raises(BridgeError) as exc:
        b.call_at(ep, "clash.apply", {"if_fingerprint": "wrong", "groups": []})
    assert exc.value.code == "stale_document"
    params = {"if_fingerprint": fp, "dedupe_key": "k1", "groups": [{"name": "G", "guids": ["c0001", "c0002"]}]}
    first = b.call_at(ep, "clash.apply", params)
    again = b.call_at(ep, "clash.apply", params)
    assert first["verified"]["groups"] == 1 and again["replayed"] is True and len(sim.groups) == 1


def test_unknown_method_and_garbage_are_handled(sim):
    b = Bridge(lambda: [Endpoint.parse(sim.endpoint)])
    with pytest.raises(BridgeError) as exc:
        b.call_at(Endpoint.parse(sim.endpoint), "nope.nothing")
    assert exc.value.code == "unsupported"
    host, port = sim.endpoint.removeprefix("tcp://").split(":")
    with socket.create_connection((host, int(port))) as s:
        s.sendall(b"not json\n")
        assert json.loads(s.makefile().readline())["error"]["data"]["code"] == "invalid_params"


def test_registry_discovery_drops_stale_entries(tmp_path):
    s = Simulator()
    s.start(register=True)
    try:
        assert any(str(e) == s.endpoint for e in discover())
    finally:
        s.stop()
    assert not any(str(e) == s.endpoint for e in discover())


def test_registry_entry_of_a_killed_simulator_is_dropped_on_any_platform():
    import socket as _s
    from vdc_navis_lab.bridge.transport import registry_dir
    free = _s.socket(); free.bind(("127.0.0.1", 0)); port = free.getsockname()[1]; free.close()  # nobody listens here
    stale = registry_dir() / "sim-dead.json"
    stale.write_text(json.dumps({"endpoint": f"tcp://127.0.0.1:{port}", "pid": 0}), encoding="utf-8")
    assert not any(f"{port}" in str(e) for e in discover())
    assert not stale.exists()
