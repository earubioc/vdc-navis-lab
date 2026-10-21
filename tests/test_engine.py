import pytest

from vdc_navis_lab.engine import analyze
from vdc_navis_lab.engine.cluster import cluster
from vdc_navis_lab.engine.screen import NoiseScreen
from vdc_navis_lab.engine.pipeline import level_label
from vdc_navis_lab.engine.plan import hotspots, matrix, work_packages
from vdc_navis_lab.engine.scoring import Scorer, mover_and_anchor
from vdc_navis_lab.engine.tagging import Tagger
from vdc_navis_lab.model import CLEARANCE, HARD, Clash, ClashSet, Element, TestInfo
from vdc_navis_lab.profile import Profile, ProfileError


def el(disc_model="", cat="", **kw):
    return Element(id=kw.pop("id", cat + disc_model), model=disc_model, category=cat, **kw)


def clash(a, b, point=(0, 0, 0), depth=0.05, test="T", status="new", kind=HARD, distance=None, cid=None):
    return Clash(id=cid or f"c{id(a)}{id(b)}", test=test, name="n", status=status, kind=kind,
                 distance=-depth if distance is None else distance, point=point, a=a, b=b)


# ---------------------------------------------------------------- profile
def test_default_profile_is_valid(profile):
    assert profile.validate() == []
    assert profile.criticality("HVAC", "STR") == profile.criticality("STR", "HVAC") == 0.9


@pytest.mark.parametrize("bad", [
    'schema = "x"', 'schema="vdc_navis_lab.profile/1"\nlang="fr"',
])
def test_invalid_profiles_are_rejected(bad):
    with pytest.raises(ProfileError):
        Profile.from_text(bad)


def test_profile_rejects_bad_bands_and_unknown_pairs():
    text = Profile.default().raw
    import tomllib
    base = open(str(__import__("importlib").resources.files("vdc_navis_lab").joinpath("profiles/default.toml")), encoding="utf-8").read()
    with pytest.raises(ProfileError, match="bands"):
        Profile.from_text(base.replace("critical = 70\nhigh = 52", "critical = 40\nhigh = 52"))
    with pytest.raises(ProfileError, match="unknown"):
        Profile.from_text(base.replace('"FIRE-HVAC"]', '"FIRE-ZZZ"]', 1))


# ---------------------------------------------------------------- tagging
def test_file_name_beats_category_and_tokens_avoid_false_hits(profile):
    t = Tagger(profile)
    assert t.discipline_of("Walls", "Torre-ELE.nwc") == "ELE"
    assert t.discipline_of("Ducts", "ELEVATIONS.nwc") == "HVAC"       # 'ele' must not match 'elevations'
    assert t.discipline_of("Ducts", "Edificio_Estructura.nwc") == "STR"
    assert t.discipline_of("Tubos", "") == "ELE"                       # Spanish Revit: conduits
    assert t.discipline_of("Tuberías", "") == "PLB"                    # ...and pipes
    assert t.discipline_of("Mystery", "") == "OTHER"


def test_override_wins(profile):
    profile.overrides["general.nwc"] = "FIRE"
    assert Tagger(profile).discipline_of("Walls", "general.nwc") == "FIRE"


# ---------------------------------------------------------------- noise
def _flt(profile):
    return NoiseScreen(profile)


def test_opening_needs_geometry_to_be_dropped(profile):
    wall = Element(id="w", category="Walls", bbox=((0, 0, 0), (0.2, 8, 3)))
    inside = Element(id="d1", category="Doors", bbox=((0, 1, 0), (0.2, 1.9, 2.1)))
    outside = Element(id="d2", category="Doors", bbox=((0, 9, 0), (0.2, 9.9, 2.1)))
    no_box = Element(id="d3", category="Doors")
    f = _flt(profile)
    assert f.reason(clash(wall, inside)) == "designed_opening"
    assert f.reason(clash(wall, outside)) == ""
    assert f.reason(clash(wall, no_box)) == "", "cannot prove it, so keep it"


def test_shallow_closed_and_self_assembly(profile):
    a, b = Element(id="a"), Element(id="b")
    f = _flt(profile)
    assert f.reason(clash(a, b, depth=0.001)) == "shallow"
    assert f.reason(clash(a, b, depth=0.05, status="approved")) == "closed"
    host = Element(id="h", model="m")
    part = Element(id="p", model="m", host_id="h")
    assert f.reason(clash(host, part)) == "self_assembly"
    assert f.reason(clash(a, b, kind=CLEARANCE, distance=0.001)) == "", "tolerance only applies to hard clashes"


def test_eaten_tests_are_reported(profile):
    wall = Element(id="w", category="Walls", bbox=((0, 0, 0), (0.2, 8, 3)))
    clashes = [clash(wall, Element(id=f"d{i}", category="Doors", bbox=((0, 1, 0), (0.2, 1.9, 2.1))), test="DOORS",
                     cid=f"x{i}") for i in range(6)]
    assert _flt(profile).run(clashes).silenced_tests() == ["DOORS"]


# ---------------------------------------------------------------- cluster
def _pts(points, disc="HVAC", prefix=""):
    out = []
    for n, p in enumerate(points):
        a = Element(id=f"{prefix}a{n}", discipline="STR")
        b = Element(id=f"{prefix}b{n}", discipline=disc)
        out.append(clash(a, b, point=p, cid=f"k{n}"))
    return out


def test_cluster_joins_near_and_separates_far():
    groups = cluster(_pts([(0, 0, 0), (1, 0, 0), (1.9, 0, 0), (50, 0, 0)]), eps=1.5, max_span=100)
    assert sorted(len(g) for g in groups) == [1, 3]


def test_cluster_never_joins_different_discipline_pairs():
    a = _pts([(0, 0, 0)], "HVAC", "x")
    b = _pts([(0.1, 0, 0)], "PLB", "y")
    assert len(cluster(a + b, eps=1.5, max_span=100)) == 2


def test_same_pair_of_assemblies_is_one_problem_anywhere():
    a, b = Element(id="a", discipline="STR"), Element(id="b", discipline="HVAC")
    far = [clash(a, b, point=(0, 0, 0), cid="1"), clash(a, b, point=(40, 0, 0), cid="2")]
    assert len(cluster(far, eps=1.5, max_span=100)) == 1


def test_large_groups_are_bisected_deterministically():
    pts = [(float(x), 0, 0) for x in range(0, 40)]  # a chain 39 m long, 1 m apart
    first = cluster(_pts(pts), eps=1.5, max_span=12.0)
    second = cluster(_pts(pts), eps=1.5, max_span=12.0)
    assert all(max(c.point[0] for c in g) - min(c.point[0] for c in g) <= 12.0 for g in first)
    assert len(first) >= 3
    assert [[c.id for c in g] for g in first] == [[c.id for c in g] for g in second]


# ---------------------------------------------------------------- scoring
def test_mover_is_the_more_movable_discipline(profile):
    assert mover_and_anchor(profile, "STR", "HVAC") == ("HVAC", "STR")
    assert mover_and_anchor(profile, "HVAC", "STR") == ("HVAC", "STR")
    m, a = mover_and_anchor(profile, "HVAC", "HVAC")
    assert m == a == "HVAC"


def _hard(depth, dims=(0.3, 0.3), a="STR", b="HVAC"):
    ea = Element(id="a", discipline=a, bbox=((0, 0, 0), (dims[0],) * 3))
    eb = Element(id="b", discipline=b, bbox=((0, 0, 0), (dims[1],) * 3))
    return clash(ea, eb, depth=depth)


def test_hard_clash_is_not_capped_by_the_clearance_weight(profile):
    s = Scorer(profile, [])
    top = s.score([_hard(0.3)], crowding=1.0, crowd=5)
    assert top.score > 75, "renormalisation must let a worst-case hard clash exceed 100*0.9"
    assert top.priority == "critical"


def test_penetration_is_relative_to_the_element_bitten(profile):
    s = Scorer(profile, [])
    small = s.score([_hard(0.03, dims=(0.05, 0.05))])  # 30 mm into a 50 mm element
    big = s.score([_hard(0.03, dims=(1.2, 1.2))])      # 30 mm into a 1.2 m element
    assert small.components["penetration"] > big.components["penetration"] * 5


def test_clearance_only_issue_scores_on_closeness(profile):
    tests = [TestInfo("CL", CLEARANCE, "active", tolerance=0.05)]
    a, b = Element(id="a", discipline="ELE"), Element(id="b", discipline="HVAC")
    near = Scorer(profile, tests).score([clash(a, b, test="CL", kind=CLEARANCE, distance=0.005)])
    far = Scorer(profile, tests).score([clash(a, b, test="CL", kind=CLEARANCE, distance=0.045)])
    assert "penetration" not in near.components
    assert near.components["clearance"] > far.components["clearance"]


def test_gate_raises_priority_and_says_why(profile):
    s = Scorer(profile, [])
    v = s.score([_hard(0.06, dims=(2.0, 2.0), a="STR", b="ELE")])  # shallow relative, but 60 mm into structure
    assert v.priority in ("high", "critical")
    assert v.score < 52 or v.priority != "low"


# ---------------------------------------------------------------- level
@pytest.mark.parametrize("raw,clean", [('Level "2th FLOOR", #9946', "2th FLOOR"), ("Level 1", "Level 1"),
                                        ("Level L2", "L2"), ("", "")])
def test_clean_level(raw, clean):
    assert level_label(raw) == clean


# ---------------------------------------------------------------- pipeline on the tower
def test_filter_counts_on_tower(result):
    assert dict(result.filtering) == {"designed_opening": 5, "shallow": 4, "self_assembly": 3, "closed": 3}


def test_rack_pipes_are_one_issue(result):
    rack = [i for i in result.issues if i.pair == ("HVAC", "PLB")]
    assert len(rack) == 1 and len(rack[0].clashes) == 5


def test_one_critical_and_it_is_the_clean_cut(result):
    crit = [i for i in result.issues if i.priority == "critical"]
    assert len(crit) == 1 and crit[0].level == "L3" and crit[0].responsible == "HVAC"
    assert result.issues[0] is crit[0], "ranking puts critical first"


def test_shared_element_and_repeated_detail_causes(result):
    kinds = {c.kind for c in result.causes}
    assert kinds == {"shared_element", "repeated_detail"}
    shared = next(c for c in result.causes if c.kind == "shared_element")
    assert shared.params["n"] == 5 and "Riser" in shared.params["element"]
    repeated = [c for c in result.causes if c.kind == "repeated_detail"]
    assert all(c.params["n"] == 5 for c in repeated)


def test_shared_element_wins_over_repeated_detail_for_the_riser(result):
    riser_issues = set(next(c for c in result.causes if c.kind == "shared_element").issue_ids)
    owning = [d for d in result.decisions if riser_issues <= set(d.issue_ids)]
    assert owning and owning[0].cause_id.startswith("CS-")


def test_decisions_fold_issues(result):
    assert len(result.decisions) < len(result.issues)
    assert sum(len(d.issue_ids) for d in result.decisions) == len(result.issues)


def test_coverage_is_honest_about_absence(result):
    cov = result.coverage
    assert cov.never_run == ["ELE vs STR"]
    assert "ARC-HVAC" in cov.pairs_without_results and "FIRE-HVAC" in cov.pairs_without_results
    assert "ARC vs STR" in cov.silenced_tests
    assert not cov.complete


def test_analysis_is_deterministic(tower, profile):
    from vdc_navis_lab.sample.generator import build
    r1 = analyze(build()[0], profile)
    r2 = analyze(build()[0], profile)
    assert [i.id for i in r1.issues] == [i.id for i in r2.issues]
    assert [i.score for i in r1.issues] == [i.score for i in r2.issues]


def test_reanalysis_after_profile_change_retags(tower, profile):
    first = analyze(tower, profile)
    profile.overrides["TORRE-HVAC.nwc"] = "PLB"
    second = analyze(tower, profile)
    assert {i.pair for i in first.issues} != {i.pair for i in second.issues}


def test_plan_matrix_hotspots(result, profile):
    m = matrix(result)
    assert sum(r["issues"] for r in m.values()) == len(result.issues)
    pk = work_packages(result, profile, package_size=5)
    assert sum(len(p["issues"]) for p in pk) == len(result.issues)
    assert all(len(p["issues"]) <= 5 for p in pk) and pk[0]["id"] == "WP-01"
    assert len(hotspots(result, limit=3)) == 3


def test_discipline_falls_back_to_the_selection_tree(profile):
    t = Tagger(profile)
    # no property category, model name useless: the tree carries the source file and the Revit category
    assert t.discipline_of("", "", ["fed.nwd", "ELE_Torre.rvt", "Conduits", "x"]) == "ELE"
    assert t.discipline_of("", "", ["fed.nwd", "Modelo.rvt", "Pipes", "Pipe Types", "x"]) == "PLB"
    assert t.discipline_of("", "", ["fed.nwd", "Modelo.rvt", "Cosas"]) == "OTHER"
    # file name keeps priority over the category
    assert t.discipline_of("Pipes", "STR_torre.rvt", []) == "STR"


def test_element_path_round_trips():
    e = Element.from_dict({"id": "a", "path": ["fed.nwd", "x.rvt", "", "Walls"]})
    assert e.path == ["fed.nwd", "x.rvt", "Walls"]
    assert Element.from_dict(e.to_dict()).path == e.path
    assert "path" not in Element(id="b").to_dict()
