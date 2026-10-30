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
from vdc_navis_lab.views import coverage_view


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


def test_sleeve_candidate_is_dampened_and_capped_but_a_beam_is_not(profile):
    s = Scorer(profile, [])
    floor = Element(id="f", discipline="STR", category="Floors", bbox=((0, 0, 0), (2.0, 2.0, 0.10)))
    pipe = Element(id="p", discipline="PLB", category="Pipes", bbox=((0, 0, 0), (0.05, 0.05, 0.05)))
    through_floor = s.score([clash(floor, pipe, depth=0.09)])  # a riser, not deeper than the slab itself
    assert any(code == "sleeve_candidate" for code, _ in through_floor.reasons)
    assert through_floor.priority in ("medium", "low"), "capped below the STR-* depth gate's 'high' floor"

    beam = Element(id="be", discipline="STR", category="Structural Framing", bbox=((0, 0, 0), (0.3, 0.3, 0.3)))
    through_beam = s.score([clash(beam, pipe, depth=0.09)])  # a beam is never a sleeve candidate
    assert not any(code == "sleeve_candidate" for code, _ in through_beam.reasons)
    assert through_beam.priority in ("high", "critical")

    too_deep = s.score([clash(floor, pipe, depth=0.5)])  # far past the slab's own thickness
    assert not any(code == "sleeve_candidate" for code, _ in too_deep.reasons)


def test_thin_conduit_in_a_slab_is_low_and_a_thick_one_is_not(profile):
    s = Scorer(profile, [])
    floor = Element(id="f", discipline="STR", category="Floors", bbox=((0, 0, 0), (2.0, 2.0, 0.10)))
    conduit = Element(id="c", discipline="ELE", category="Conduits", bbox=((0, 0, 0), (0.033, 0.033, 0.5)))
    thin = s.score([clash(floor, conduit, depth=0.09)])
    assert thin.priority == "low"
    assert any(code == "embedded_small" for code, _ in thin.reasons)

    fat = Element(id="c2", discipline="ELE", category="Conduits", bbox=((0, 0, 0), (0.08, 0.08, 0.5)))
    thick = s.score([clash(floor, fat, depth=0.09)])  # 80 mm in a 100 mm slab: not an ordinary embedding
    assert not any(code == "embedded_small" for code, _ in thick.reasons)
    assert thick.priority in ("medium", "low") and any(code == "sleeve_candidate" for code, _ in thick.reasons)

    beam = Element(id="be", discipline="STR", category="Structural Framing", bbox=((0, 0, 0), (0.3, 0.3, 0.3)))
    in_beam = s.score([clash(beam, conduit, depth=0.033)])  # beams are never covered by this rule
    assert not any(code == "embedded_small" for code, _ in in_beam.reasons)


def test_sleeve_reason_says_none_are_modelled_only_when_the_model_was_checked(profile):
    floor = Element(id="f", discipline="STR", category="Floors", bbox=((0, 0, 0), (2.0, 2.0, 0.10)))
    pipe = Element(id="p", discipline="PLB", category="Pipes", bbox=((0, 0, 0), (0.05, 0.05, 0.05)))
    s = Scorer(profile, [])
    assert any(c == "sleeve_candidate" for c, _ in s.score([clash(floor, pipe, depth=0.09)]).reasons)  # not checked
    s.sleeves_modeled = 3
    assert any(c == "sleeve_candidate" for c, _ in s.score([clash(floor, pipe, depth=0.09)]).reasons)
    s.sleeves_modeled = 0
    assert any(c == "sleeve_missing" for c, _ in s.score([clash(floor, pipe, depth=0.09)]).reasons)


def test_actions_depend_on_who_moves_and_on_the_situation(tower, profile):
    from vdc_navis_lab import views
    r = analyze(tower, profile)
    texts_seen = {views.action_text(i, profile, "es") for i in r.issues}
    assert len(texts_seen) >= 2, "actions should not all read the same"
    assert all("—" not in t for t in texts_seen)


def _obb(centre, axis, half, up=(0, 0, 1)):
    """Oriented box: first axis is the longest; the other two are completed from the world's vertical."""
    import math
    ax = tuple(axis)
    n = math.sqrt(sum(a * a for a in ax))
    ax = tuple(a / n for a in ax)
    cross = (ax[1] * up[2] - ax[2] * up[1], ax[2] * up[0] - ax[0] * up[2], ax[0] * up[1] - ax[1] * up[0])
    cn = math.sqrt(sum(a * a for a in cross))
    if cn < 1e-9:
        cross, cn = (1.0, 0.0, 0.0), 1.0
    u1 = tuple(a / cn for a in cross)
    u2 = (ax[1] * u1[2] - ax[2] * u1[1], ax[2] * u1[0] - ax[0] * u1[2], ax[0] * u1[1] - ax[1] * u1[0])
    return {"c": list(centre), "u": [list(ax), list(u1), list(u2)], "h": list(half)}


def _beam_and_run(run_axis, run_centre=(0, 0, 0), run_len=2.0, dia=0.033, beam_depth=1.1):
    # beam along X, 6 m span, 0.30 wide, centred at the origin; section axes: u1 = Y (width), u2 = Z (depth)
    beam = Element(id="b", discipline="STR", category="Structural Framing", bbox=((-3, -0.15, -beam_depth / 2), (3, 0.15, beam_depth / 2)))
    beam.obb = {"c": [0, 0, 0], "u": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "h": [3.0, 0.15, beam_depth / 2]}
    run = Element(id="r", discipline="ELE", category="Conduits", bbox=((-0.05, -0.05, -0.05), (0.05, 0.05, 0.05)))
    run.obb = _obb(run_centre, run_axis, (run_len / 2, dia / 2, dia / 2))
    return beam, run


def test_beam_passage_geometry(profile):
    from vdc_navis_lab.engine.passage import assess
    # transversal, mid span, mid depth, thin: meets the geometry
    beam, run = _beam_and_run((0, 1, 0))
    r = assess(profile, beam, run, (0, 0, 0))
    assert r.ok and r.kind == "transversal"
    # same crossing but near a support
    r = assess(profile, beam, run, (2.5, 0, 0))
    assert "span" in r.failures
    # off the middle third of the depth
    r = assess(profile, beam, run, (0, 0, 0.45))
    assert "zone" in r.failures
    # too big for the depth (a 50 cm duct through a 1.1 m beam)
    beam, big = _beam_and_run((0, 1, 0), dia=0.5)
    assert "size" in assess(profile, beam, big, (0, 0, 0)).failures
    # running along the beam
    beam, along = _beam_and_run((1, 0.05, 0))
    r = assess(profile, beam, along, (0, 0, 0))
    assert r.kind == "longitudinal" and r.failures == ["longitudinal"]
    # at 45 degrees
    beam, diag = _beam_and_run((1, 1, 0))
    r = assess(profile, beam, diag, (0, 0, 0))
    assert r.kind == "diagonal" and not r.ok
    # vertical run through the beam is judged on the width (0.30 m): 33 mm is fine, centred
    beam, vert = _beam_and_run((0, 0, 1))
    r = assess(profile, beam, vert, (0, 0, 0))
    assert r.kind == "vertical" and r.ok
    # a stub is not judged
    beam, stub = _beam_and_run((0, 1, 0), run_len=0.05)
    assert assess(profile, beam, stub, (0, 0, 0)) is None


def test_beam_passage_drives_priority(profile):
    s = Scorer(profile, [])
    beam, ok = _beam_and_run((0, 1, 0))
    v = s.score([clash(beam, ok, depth=0.033)])
    assert v.priority == "medium" and any(c == "beam_pass_ok" for c, _ in v.reasons)
    beam, along = _beam_and_run((1, 0.05, 0))
    v = s.score([clash(beam, along, depth=0.033)])
    assert v.priority == "critical" and any(c == "beam_pass_longitudinal" for c, _ in v.reasons)
    beam, near = _beam_and_run((0, 1, 0))
    c = clash(beam, near, depth=0.033)
    c.point = (2.5, 0, 0)
    v = s.score([c])
    assert v.priority == "high" and any(code == "beam_pass_span" for code, _ in v.reasons)
    beam, diag = _beam_and_run((1, 1, 0))
    assert s.score([clash(beam, diag, depth=0.033)]).priority == "high", "a diagonal crossing is not critical by itself"
    # without oriented boxes nothing changes
    beam.obb = None
    base = s.score([clash(beam, near, depth=0.033)])
    assert not any(code.startswith("beam_pass") for code, _ in base.reasons)


def test_failing_beam_passage_is_not_hidden_by_a_thin_conduit_in_a_slab_in_the_same_issue(profile):
    s = Scorer(profile, [])
    floor = Element(id="f", discipline="STR", category="Floors", bbox=((0, 0, 0), (2.0, 2.0, 0.10)))
    conduit = Element(id="c", discipline="ELE", category="Conduits", bbox=((0, 0, 0), (0.033, 0.033, 0.5)))
    beam, along = _beam_and_run((1, 0.05, 0))
    deeper_in_slab = clash(floor, conduit, depth=0.09)
    in_beam = clash(beam, along, depth=0.033)
    v = s.score([deeper_in_slab, in_beam])
    assert v.priority == "critical", "the longitudinal run inside the beam must win over the slab embedding"
    only_slab = s.score([deeper_in_slab])
    assert only_slab.priority == "low"


def test_oriented_box_round_trips_through_the_clashset():
    from vdc_navis_lab.model import Element as E
    e = E(id="x", category="Conduits")
    e.obb = {"c": [1.0, 2.0, 3.0], "u": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "h": [1.0, 0.02, 0.02]}
    back = E.from_dict(e.to_dict())
    assert back.obb == e.obb
    assert E.from_dict({"id": "y", "obb": {"c": [1, 2]}}).obb is None, "a malformed box is dropped, not trusted"


def test_skipped_results_that_were_already_closed_do_not_break_completeness(tower, profile):
    tower.skipped, tower.skipped_open = 4, 0
    r = analyze(tower, profile)
    assert r.coverage.skipped == 4 and r.coverage.skipped_open == 0
    cov = coverage_view(r, "es")
    assert any("ya cerrados" in w for w in cov["warnings"])
    tower.skipped_open = 2
    r2 = analyze(tower, profile)
    assert any("seguían abiertos" in w for w in coverage_view(r2, "es")["warnings"])


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


def test_coverage_reports_skipped_results(tower, profile):
    tower.skipped = 4  # the add-in dropped 4 results whose elements no longer exist in the model
    r = analyze(tower, profile)
    assert r.coverage.skipped == 4
    assert not r.coverage.complete, "a skipped result is not honestly 'complete' coverage"
    cov = coverage_view(r, "es")
    assert cov["skipped"] == 4
    assert any("omitido" in w for w in cov["warnings"])


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


def test_vertical_run_that_ends_inside_the_beam_is_not_a_passage(profile):
    from vdc_navis_lab.engine.passage import assess
    # a drop that starts 0.2 m below the top of a 1.1 m beam and goes up: it ends inside the beam
    beam, drop = _beam_and_run((0, 0, 1), run_centre=(0, 0, 0.75), run_len=1.0)
    r = assess(profile, beam, drop, (0, 0, 0.5))
    assert r is not None and r.kind == "end" and r.ok
    # one that covers the whole depth is still judged, and says how much of it it covers
    beam, thru = _beam_and_run((0, 0, 1), run_len=2.0)
    r = assess(profile, beam, thru, (0, 0, 0))
    assert r is not None and r.kind == "vertical" and r.through == 1.0


def test_vertical_drop_into_a_beam_under_a_thin_slab_stays_an_embedding(profile):
    s = Scorer(profile, [])
    floor = Element(id="f", discipline="STR", category="Floors", bbox=((0, 0, 0.5), (2.0, 2.0, 0.6)))
    conduit = Element(id="c", discipline="ELE", category="Conduits", bbox=((0, 0, 0.3), (0.033, 0.033, 1.0)))
    beam, drop = _beam_and_run((0, 0, 1), run_centre=(0, 0, 0.75), run_len=1.0)
    v = s.score([clash(floor, conduit, depth=0.09), clash(beam, drop, depth=0.06)])
    assert v.priority == "low", v.reasons
    assert not any(code.startswith("beam_pass") for code, _ in v.reasons)


def test_element_through_the_slab_on_both_sides_is_a_modelling_error(profile):
    s = Scorer(profile, [])
    slab = Element(id="s", discipline="STR", category="Floors", bbox=((0, 0, 3.9), (10, 10, 4.0)))
    wall = Element(id="w", name="Muro 10cm enchape", discipline="ARC", category="Walls", bbox=((1, 1, 0.0), (3, 1.1, 7.65)))
    v = s.score([clash(slab, wall, depth=0.10)])
    assert v.priority == "medium" and any(c == "model_error" for c, _ in v.reasons)
    # a storey-high wall that rests on the slab is nothing special
    ok_wall = Element(id="w2", discipline="ARC", category="Walls", bbox=((1, 1, 3.8), (3, 1.1, 7.6)))
    v2 = s.score([clash(slab, ok_wall, depth=0.10)])
    assert not any(c == "model_error" for c, _ in v2.reasons)
    # structure's own element is never called a modelling error by this rule
    col = Element(id="c", discipline="STR", category="Walls", bbox=((1, 1, 0.0), (3, 1.1, 7.65)))
    assert not any(c == "model_error" for c, _ in s.score([clash(slab, col, depth=0.10)]).reasons)


def test_a_slab_embedding_and_a_beam_crossing_next_to_it_are_two_issues(profile):
    slab = Element(id="s", discipline="STR", category="Floors", bbox=((0, 0, 0), (2, 2, 0.1)))
    beam = Element(id="bm", discipline="STR", category="Structural Framing", bbox=((0, 0, -0.5), (2, 0.3, 0.1)))
    c1 = Element(id="c1", discipline="ELE", category="Conduits", bbox=((0, 0, 0), (0.03, 0.03, 0.5)))
    c2 = Element(id="c2", discipline="ELE", category="Conduits", bbox=((0, 0.1, 0), (0.03, 0.13, 0.5)))
    flat = cluster([clash(slab, c1, point=(0, 0, 0), cid="1"), clash(beam, c2, point=(0.1, 0, 0), cid="2")], eps=1.5, max_span=100)
    assert len(flat) == 1, "close together they would collapse into one issue"
    split = cluster([clash(slab, c1, point=(0, 0, 0), cid="1"), clash(beam, c2, point=(0.1, 0, 0), cid="2")], eps=1.5, max_span=100,
                    partition=lambda c: "floors" if "Floors" in (c.a.category, c.b.category) else "beam")
    assert len(split) == 2


def test_architectural_floor_finish_over_structure_is_a_modelling_error(profile):
    s = Scorer(profile, [])
    column = Element(id="col", discipline="STR", category="Structural Columns", bbox=((0, 0, 0), (0.4, 0.4, 3)))
    finish = Element(id="fin", name="Floor : BALDOSA", discipline="ARC", category="Floors", bbox=((0, 0, 2.9), (5, 5, 3.0)))
    v = s.score([clash(column, finish, depth=0.10)])
    assert v.priority == "medium" and any(c == "model_finish" for c, _ in v.reasons)
    # an architectural wall against a column is an ordinary conflict
    wall = Element(id="w", discipline="ARC", category="Walls", bbox=((0, 0, 0), (0.1, 2, 3)))
    assert not any(c.startswith("model_") for c, _ in s.score([clash(column, wall, depth=0.10)]).reasons)


def test_modelling_errors_of_one_model_become_one_decision(profile):
    from vdc_navis_lab.engine.pipeline import analyze
    from vdc_navis_lab.model import ClashSet
    col = [Element(id=f"col{i}", discipline="STR", category="Structural Columns", model="EST.rvt",
                   bbox=((10 * i, 0, 0), (10 * i + 0.4, 0.4, 3))) for i in range(3)]
    fin = [Element(id=f"fin{i}", name="Floor : BALDOSA", discipline="ARC", category="Floors", model="ARQ.rvt",
                   bbox=((10 * i, 0, 2.9), (10 * i + 5, 5, 3.0))) for i in range(3)]
    cs = ClashSet(clashes=[clash(col[i], fin[i], depth=0.10, point=(10 * i * 5, 0, 3.0), cid=f"c{i}") for i in range(3)],
                  tests=[], source="test")
    r = analyze(cs, profile)
    updates = [c for c in r.causes if c.kind == "model_update"]
    assert len(updates) == 1 and updates[0].params["model"] == "ARQ.rvt"
    decision = next(d for d in r.decisions if d.id == updates[0].id)
    assert len(decision.issue_ids) == len(r.issues) and decision.priority == "high"
