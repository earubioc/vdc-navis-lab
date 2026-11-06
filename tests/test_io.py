import io
import json

import pytest

from vdc_navis_lab import exports, ingest
from vdc_navis_lab.engine import analyze
from vdc_navis_lab.model import ClashSet
from vdc_navis_lab.paths import PathError, resolve_output

NAVIS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<exchange xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" units="mm" filename="demo.nwf">
 <batchtest name="Batch" units="mm"><clashtests>
  <clashtest name="STR vs HVAC" test_type="hard" status="ok" tolerance="0.0">
   <summary total="1"/>
   <clashresults>
    <clashresult name="Clash1" guid="g-1" status="new" distance="-150.0">
     <clashpoint><pos3f x="10000.0" y="2000.0" z="3000.0"/></clashpoint>
     <clashobjects>
      <clashobject><pathlink><node>TORRE-EST.nwc</node><node>Beam 1</node></pathlink>
       <smarttags><smarttag><name>Item Name</name><value>Beam 1</value></smarttag>
        <smarttag><name>Category</name><value>Structural Framing</value></smarttag>
        <smarttag><name>Level</name><value>Level "L2", #77</value></smarttag>
        <smarttag><name>Element ID</name><value>5551</value></smarttag></smarttags></clashobject>
      <clashobject><pathlink><node>TORRE-HVAC.nwc</node><node>Duct 9</node></pathlink>
       <smarttags><smarttag><name>Item Name</name><value>Duct 9</value></smarttag>
        <smarttag><name>Category</name><value>Ducts</value></smarttag></smarttags></clashobject>
     </clashobjects>
    </clashresult>
   </clashresults>
  </clashtest>
  <clashtest name="Empty" test_type="clearance" status="new" tolerance="50"><clashresults/></clashtest>
 </clashtests></batchtest>
</exchange>"""


def test_navisworks_xml_is_read_and_units_converted():
    cs = ingest.from_navisworks_xml(NAVIS_XML)
    assert len(cs.clashes) == 1 and [t.name for t in cs.tests] == ["STR vs HVAC", "Empty"]
    c = cs.clashes[0]
    assert c.distance == pytest.approx(-0.15) and c.point == pytest.approx((10.0, 2.0, 3.0))
    assert c.a.model == "TORRE-EST.nwc" and c.a.category == "Structural Framing" and c.a.id == "TORRE-EST.nwc:5551"
    assert cs.tests[1].tolerance == pytest.approx(0.05) and cs.tests[1].kind == "clearance"
    assert analyze(cs, __import__("vdc_navis_lab.profile", fromlist=["Profile"]).Profile.default()).issues


def test_xml_with_dtd_is_refused():
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><exchange/>'
    with pytest.raises(ingest.IngestError):
        ingest.from_navisworks_xml(evil)


def test_load_rejects_wrong_types_and_hides_content(tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text('{"password": "hunter2"}', encoding="utf-8")
    with pytest.raises(ingest.IngestError) as exc:
        ingest.load(f)
    assert "hunter2" not in str(exc.value)
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(ingest.IngestError):
        ingest.load(bad)


def test_csv_ingest():
    text = ("id,test,name,status,distance,x,y,z,a_id,a_name,a_category,a_model,b_id,b_name,b_category,b_model,level\n"
            "1,T1,C1,new,-0.12,1,2,3,a1,Beam,Structural Framing,EST.nwc,b1,Duct,Ducts,HVAC.nwc,L1\n")
    cs = ingest.from_csv(text)
    assert cs.clashes[0].distance == -0.12 and cs.clashes[0].b.category == "Ducts" and cs.tests[0].count == 1


def test_json_roundtrip(tower, tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(tower.to_dict()), encoding="utf-8")
    again = ingest.load(p)
    assert len(again.clashes) == len(tower.clashes) and again.clashes[0].a.bbox == tower.clashes[0].a.bbox
    with pytest.raises(ValueError):
        ClashSet.from_dict({"schema": "other/1"})


# ---------------------------------------------------------------- exports (Community: markdown; the file formats are Pro)
def test_markdown_report_has_scope_and_language(result, profile):
    es = exports.to_markdown(result, profile)
    assert "Alcance de la evidencia" in es
    import dataclasses
    en = exports.to_markdown(dataclasses.replace(result, lang="en"), profile)
    assert "Evidence scope" in en and "—" not in en and "—" not in es


# ---------------------------------------------------------------- paths
def test_output_paths_are_confined(tmp_path, monkeypatch):
    root = tmp_path / "out"
    root.mkdir()
    monkeypatch.setenv("VDC_NAVIS_LAB_OUTPUT_ROOTS", str(root))
    ok = resolve_output(str(root / "a" / "x.csv"), "d.csv")
    assert str(ok).startswith(str(root.resolve()))
    for bad in ["../../etc/passwd", str(tmp_path / "elsewhere.csv"), "\\\\host\\share\\x.csv", "C:\\a\\b.txt:hidden",
                "NUL.csv", "a\x00b.csv", "x?.csv"]:
        with pytest.raises(PathError):
            resolve_output(bad, "d.csv")


def test_overwrite_defaults_to_refuse(tmp_path):
    p = resolve_output("same.csv", "same.csv")
    p.write_text("x")
    with pytest.raises(PathError, match="exists"):
        resolve_output("same.csv", "same.csv")
    assert resolve_output("same.csv", "same.csv", overwrite=True) == p
