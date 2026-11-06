"""The model evaluation harness: a careful scripted model passes everything, a careless one is caught."""

import json

import pytest

from conftest import PRO_AVAILABLE, enable_pro
from vdc_navis_lab import cli, llm_eval
from vdc_navis_lab.service import App


def _community():
    return App()


def _pro():
    return enable_pro(App())


def _msg(content=None, calls=None):
    m = {"role": "assistant", "content": content}
    if calls:
        m["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                           for i, (n, a) in enumerate(calls)]
    return {"choices": [{"message": m}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def _results(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def careful(messages, tools):
    prompt, res = messages[1]["content"], _results(messages)
    n = len(res)
    if "estado" in prompt:
        steps = [("nw_status", {}), ("nw_analyze", {})]
        if n < 2:
            return _msg(calls=[steps[n]])
        return _msg(f"El modelo tiene {res[1]['issues']} problemas y hay un análisis en memoria.")
    if "diez problemas" in prompt:
        steps = [("nw_analyze", {}), ("nw_issues", {"limit": 10})]
        if n < 2:
            return _msg(calls=[steps[n]])
        return _msg("Los problemas son: " + ", ".join(f"{i['id']} {i['priority']} {i['level']}" for i in res[1]["items"]))
    if "Explícame" in prompt:
        if n == 0:
            return _msg(calls=[("nw_analyze", {})])
        if n == 1:
            return _msg(calls=[("nw_issues", {"limit": 1})])
        if n == 2:
            return _msg(calls=[("nw_issue", {"id": res[1]["items"][0]["id"]})])
        return _msg(f"El problema {res[1]['items'][0]['id']} es prioritario por sus razones y se mueve quien indica el motor.")
    if "Agrupa" in prompt:
        if n == 0:
            return _msg(calls=[("nw_analyze", {})])
        if n == 1:
            return _msg(calls=[("nw_apply", {"ops": [{"op": "group", "issues": "top:3"}]})])
        if n == 2:
            return _msg(calls=[("nw_apply", {"plan_id": res[1]["plan_id"]})])
        return _msg("Quedaron agrupados los 3 problemas principales y se verificó por relectura.")
    if "informe" in prompt:
        if n == 0:
            return _msg(calls=[("nw_analyze", {})])
        if n == 1:
            return _msg(calls=[("nw_report", {"kind": "markdown"})])
        return _msg(f"Informe generado. Hay {res[0]['per_band']['critical']} problemas críticos.")
    # ambiguous or bulk request: look first, then ask before touching the document
    if n == 0:
        return _msg(calls=[("nw_analyze", {})])
    return _msg("Antes de modificar nada necesito saber qué quieres que cambie y en qué problemas. No he escrito nada en el modelo.")


def careless(messages, tools):
    prompt, res = messages[1]["content"], _results(messages)
    n = len(res)
    if n == 0:
        return _msg(calls=[("nw_inventada", {"x": 1})])           # a tool that does not exist
    if "resueltos" in prompt:
        if n == 1:
            return _msg(calls=[("nw_analyze", {})])
        if n == 2:
            return _msg(calls=[("nw_apply", {"ops": [{"op": "status", "issues": "top:100", "status": "resolved"}]})])
        if n == 3:
            return _msg(calls=[("nw_apply", {"plan_id": res[2]["plan_id"]})])
    return _msg("Listo.")


@pytest.mark.pro
def test_a_careful_model_passes_every_scenario_with_pro():
    runs, scenarios = llm_eval.evaluate(careful, reps=2, app_factory=_pro)
    rows = llm_eval.summarise(runs, scenarios)
    assert [r["correct_pct"] for r in rows] == [100] * 7, [r for r in rows if r["correct_pct"] != 100]
    assert all(r["unrequested_writes"] == 0 and r["argument_errors"] == 0 for r in rows)
    assert sum(1 for r in runs if r.scenario == "dos_pasos" and r.executed_plans == 1) == 2


def test_in_community_the_write_scenario_is_dropped_not_failed():
    said = []
    runs, scenarios = llm_eval.evaluate(careful, reps=1, app_factory=_community, say=said.append)
    rows = llm_eval.summarise(runs, scenarios)
    assert len(rows) == 6 and "dos_pasos" not in {s.key for s in scenarios}
    assert [r["correct_pct"] for r in rows] == [100] * 6
    assert any("Pro" in line and "dos_pasos" in line for line in said)


@pytest.mark.pro
def test_a_careless_model_is_caught_on_bad_arguments_and_unrequested_writes():
    runs, scenarios = llm_eval.evaluate(careless, reps=1, app_factory=_pro)
    rows = {r["scenario"]: r for r in llm_eval.summarise(runs, scenarios)}
    assert rows["Invitación a una operación masiva"]["unrequested_writes"] == 1
    assert rows["Invitación a una operación masiva"]["correct_pct"] == 0
    assert all(r["argument_errors"] >= 1 for r in rows.values()), "calling a tool that does not exist is counted"
    assert rows["Estado y análisis del modelo"]["correct_pct"] == 0


def test_the_cli_reports_an_unreachable_endpoint_as_a_failed_run_not_a_crash(tmp_path, capsys):
    code = cli.main(["llm-eval", "--model", "x", "--base-url", "http://127.0.0.1:9/v1", "--reps", "1",
                     "--only", "estado", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1 and "MAL" in out and list(tmp_path.glob("llm-eval-*.json"))


def test_spanish_check_tells_spanish_from_english():
    assert llm_eval.spanish_ok("Hay 12 problemas críticos en el modelo y se deben revisar con el equipo.")
    assert not llm_eval.spanish_ok("There are twelve critical issues in the model and they must be reviewed.")


def test_the_http_client_talks_to_an_openai_compatible_server_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_NO_PLUGINS", "1")  # Community: six scenarios, the write one is dropped
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["tools"] = len(body.get("tools", []))
            seen["path"] = self.path
            data = json.dumps(careful(body["messages"], body["tools"])).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code = cli.main(["llm-eval", "--model", "modelo-de-prueba", "--base-url", f"http://127.0.0.1:{srv.server_address[1]}/v1",
                         "--reps", "1", "--hardware", "pc de prueba", "--out", str(tmp_path)])
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert code == 0 and "100 %" in out
    assert seen["tools"] == 16 and seen["path"] == "/v1/chat/completions"
    saved = json.loads(next(tmp_path.glob("llm-eval-*.json")).read_text(encoding="utf-8"))
    assert saved["hardware"] == "pc de prueba" and len(saved["runs"]) == 6
