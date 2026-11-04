"""Times the analysis engine on a synthetic clash set (no Navisworks needed).

    python tools/stress_gen.py 200 2000 big.json     # tests, clashes per test, output
    python tools/stress_bench.py big.json            # load + analyse time and peak memory
"""
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from vdc_navis_lab.engine import analyze  # noqa: E402
from vdc_navis_lab.model import ClashSet  # noqa: E402
from vdc_navis_lab.profile import Profile  # noqa: E402

t0 = time.time()
cs = ClashSet.from_dict(json.load(open(sys.argv[1])))
t1 = time.time()
r = analyze(cs, Profile.default(), "en")
t2 = time.time()
print(f"{sys.argv[1]}: raw={len(cs.clashes)} issues={len(r.issues)} load={t1 - t0:.1f}s analyze={t2 - t1:.1f}s "
      f"peak_memory={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f}MB")
