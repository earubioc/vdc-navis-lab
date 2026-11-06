"""Entry point of the offline bundle: every dependency is in server/lib, nothing is downloaded or installed."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from vdc_navis_lab.server import main  # noqa: E402

raise SystemExit(main(["--serve"]))
