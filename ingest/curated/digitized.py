"""Plot-digitized observations: every digitized/<name>.spec.json that has a WPD export next to it.

Specs without an export are pending (listed on stderr, emit nothing). See ingest/wpd.py for the guards.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..wpd import load_project, load_spec, observations_from, project_for

DIR = Path("digitized")


def observations(sources: dict) -> list[dict]:
    out: list[dict] = []
    for spec_path in sorted(DIR.glob("*.spec.json")):
        proj = project_for(spec_path)
        if proj is None:
            print(f"    pending (no WPD export yet): {spec_path.name}", file=sys.stderr)
            continue
        data, images = load_project(proj)
        got = observations_from(load_spec(spec_path), data, images, sources)
        print(f"    {proj.name}: {len(got)} points", file=sys.stderr)
        out.extend(got)
    return out
