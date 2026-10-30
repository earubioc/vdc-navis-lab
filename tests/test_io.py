import io
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from vdc_navis_lab import exports, ingest
from vdc_navis_lab.engine import analyze
from vdc_navis_lab.engine.diff import compare, snapshot_of
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


# ---------------------------------------------------------------- exports
def test_csv_neutralises_formulas_but_not_numbers(result, profile):
    assert exports.csv_cell("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"
    assert exports.csv_cell("-2+3") == "'-2+3"
    assert exports.csv_cell(-0.5) == -0.5 and exports.csv_cell("Duct") == "Duct"
    data = exports.to_csv(result, profile).decode("utf-8-sig")
    assert data.splitlines()[0].startswith("id,priority") and len(data.splitlines()) == len(result.issues) + 1


def test_pdf_report_is_a_valid_document_in_both_languages(result, profile):
    import dataclasses
    for lang, needle in (("es", b"Decisiones por tomar"), ("en", b"Decisions to make")):
        data = exports.to_pdf(dataclasses.replace(result, lang=lang), profile, 10)
        assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
        assert needle in data and b"\xe2\x80\x94" not in data  # no em dash
        # every xref offset points at its object
        xref = int(data.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
        n = int(data[xref:].split(b"\n")[1].split()[1])
        offsets = [int(l[:10]) for l in data[xref:].split(b"\n")[3:3 + n - 1]]
        for k, off in enumerate(offsets, 1):
            assert data[off:].startswith(b"%d 0 obj" % k)


def test_pdf_wraps_long_words_and_breaks_pages():
    from vdc_navis_lab import pdf
    assert all(pdf.width(l, 9) <= 100.01 for l in pdf.wrap("x" * 300 + " corto", 9, 100))
    d = pdf.Document("t", "f")
    for _ in range(200):
        d.paragraph("línea con acentos ñ é ü", 10)
    assert len(d.pages) > 3 and d.render().count(b"/Type /Page ") == len(d.pages)


def test_markdown_report_has_scope_and_language(result, profile):
    es = exports.to_markdown(result, profile)
    assert "Alcance de la evidencia" in es
    import dataclasses
    en = exports.to_markdown(dataclasses.replace(result, lang="en"), profile)
    assert "Evidence scope" in en and "—" not in en and "—" not in es


def test_bcf_structure(result, profile):
    z = zipfile.ZipFile(io.BytesIO(exports.to_bcf(result, profile)))
    names = z.namelist()
    assert "bcf.version" in names and len(names) == len(result.issues) + 1
    markup = next(n for n in names if n.endswith("markup.bcf"))
    topic = ET.fromstring(z.read(markup)).find("Topic")
    assert topic.get("TopicType") == "Clash" and topic.find("AssignedTo").text in profile.disciplines
    import uuid
    uuid.UUID(topic.get("Guid"))


def test_bcf_validates_against_buildingsmart_schema_when_available(result, profile):
    import os
    d = os.environ.get("BCF_SCHEMA_DIR")
    if not d:
        pytest.skip("set BCF_SCHEMA_DIR to a folder with markup.xsd and visinfo.xsd")
    xmlschema = pytest.importorskip("xmlschema")
    schema = xmlschema.XMLSchema(os.path.join(d, "markup.xsd"))
    z = zipfile.ZipFile(io.BytesIO(exports.to_bcf(result, profile)))
    for n in z.namelist():
        if n.endswith("markup.bcf"):
            schema.validate(z.read(n).decode("utf-8"))


# ---------------------------------------------------------------- diff
def test_compare_identical_is_stable(result):
    snap = snapshot_of(result)
    d = compare(snap, snap)
    assert d["new"] == [] and d["absent"] == [] and d["persisting_count"] == len(result.issues)


def test_compare_reports_absent_never_resolved(tower, profile):
    before = snapshot_of(analyze(tower, profile))
    tower.clashes = [c for c in tower.clashes if c.a.discipline != "FIRE" and c.b.discipline != "FIRE"
                     and "sprk" not in c.b.id]
    after = snapshot_of(analyze(tower, profile))
    d = compare(before, after)
    assert len(d["absent"]) == 1 and d["new"] == []
    assert "resolved" not in json.dumps(d["absent"]) and "absent is not resolved" in d["note_absent"]


def test_compare_flags_changed_coverage(tower, profile):
    before = snapshot_of(analyze(tower, profile))
    after = json.loads(json.dumps(before))
    after["tests"] = after["tests"][:-1]
    after["profile"]["checksum"] = "other"
    d = compare(before, after)
    assert d["coverage_shift"] and len(d["notes"]) == 2


def test_compare_survives_reclustering(tower, profile):
    before = snapshot_of(analyze(tower, profile))
    profile.raw["cluster"]["eps_m"] = 0.3  # the rack splits into several issues
    after = snapshot_of(analyze(tower, profile))
    d = compare(before, after)
    assert d["persisting_count"] >= len(before["issues"]) - 2


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
