"""
Build the data for the cross-cutting overlap page: per-neighborhood
kid change vs. senior change, 2000 -> 2023.

Inputs:
  - docs/seniors_counts.json (this repo)
  - kids counts: needs the kid project's counts_timeseries.json copied in
    OR fetched from its GitHub Pages URL.

For now we read the kid file from a sibling working tree if available, else
download it.

Output: docs/overlap.json
  {
    "neighborhoods": [
      {
        "name": "Williamsburg",
        "borough": "Brooklyn",   # or "outside NYC"
        "kids_2000": 4210, "kids_2023": 6840, "kid_delta": 2630, "kid_pct": 62,
        "sr_2000":  1180, "sr_2023":  1820, "sr_delta": 640,    "sr_pct": 54,
        "n_tracts": 14
      },
      ...
    ]
  }
"""

import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "docs"

KIDS_LOCAL = Path("/Users/joshgreenman/Experiments/nyc-child-density/docs/counts_timeseries.json")
KIDS_URL = "https://joshgreenman1973.github.io/nyc-child-density/counts_timeseries.json"

NYC_COUNTIES = {
    ("36", "005"): "Bronx", ("36", "047"): "Brooklyn", ("36", "061"): "Manhattan",
    ("36", "081"): "Queens", ("36", "085"): "Staten Island",
}


def borough(gj):
    st, co = gj[1:3], gj[4:7]
    return NYC_COUNTIES.get((st, co), "Inner-ring suburb")


def main():
    seniors = json.loads((WEB / "seniors_counts.json").read_text())
    nbhd = json.loads((WEB / "neighborhoods.json").read_text())

    if KIDS_LOCAL.exists():
        kids = json.loads(KIDS_LOCAL.read_text())
        print(f"loaded kids from {KIDS_LOCAL}")
    else:
        print(f"downloading kids from {KIDS_URL}")
        with urllib.request.urlopen(KIDS_URL) as r:
            kids = json.loads(r.read())

    # Year indices
    sr_y00 = seniors["years"].index(2000)
    sr_y23 = seniors["years"].index(2023)
    kd_y00 = kids["years"].index(2000)
    kd_y23 = kids["years"].index(2023)

    # Aggregate per neighborhood
    agg = {}
    for gj, label in nbhd.items():
        if not isinstance(label, str) or not label or label == "?":
            continue
        sr = seniors["tracts"].get(gj)
        kd = kids["tracts"].get(gj)
        if not sr or not kd:
            continue
        sv00 = sr[sr_y00] or 0
        sv23 = sr[sr_y23] or 0
        kv00 = kd[kd_y00] or 0
        kv23 = kd[kd_y23] or 0
        boro = borough(gj)
        # Use (label, boro) as key so two neighborhoods with the same label in
        # different states/boroughs (e.g. "Madison" - exists in NJ and Westchester) don't merge.
        key = (label, boro)
        if key not in agg:
            agg[key] = {"kids00": 0, "kids23": 0, "sr00": 0, "sr23": 0, "n": 0}
        a = agg[key]
        a["kids00"] += kv00; a["kids23"] += kv23
        a["sr00"] += sv00; a["sr23"] += sv23
        a["n"] += 1

    rows = []
    for (label, boro), a in agg.items():
        # Filter out tiny neighborhoods (low-pop fragments at edges)
        if a["kids00"] + a["kids23"] < 200 or a["sr00"] + a["sr23"] < 200:
            continue
        rows.append({
            "name": label,
            "borough": boro,
            "kids_2000": round(a["kids00"]),
            "kids_2023": round(a["kids23"]),
            "kid_delta": round(a["kids23"] - a["kids00"]),
            "kid_pct": round(100 * (a["kids23"] - a["kids00"]) / a["kids00"]) if a["kids00"] > 0 else None,
            "sr_2000": round(a["sr00"]),
            "sr_2023": round(a["sr23"]),
            "sr_delta": round(a["sr23"] - a["sr00"]),
            "sr_pct": round(100 * (a["sr23"] - a["sr00"]) / a["sr00"]) if a["sr00"] > 0 else None,
            "n_tracts": a["n"],
        })

    # Sort by total magnitude of activity (kids + seniors) for default render order
    rows.sort(key=lambda r: abs(r["kid_delta"]) + abs(r["sr_delta"]), reverse=True)

    out = {"neighborhoods": rows, "comparison_years": [2000, 2023]}
    (WEB / "overlap.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {WEB/'overlap.json'} ({len(rows)} neighborhoods)")

    # Quick stats
    both_lost = [r for r in rows if r["kid_delta"] < 0 and r["sr_delta"] < 0]
    both_gained = [r for r in rows if r["kid_delta"] > 0 and r["sr_delta"] > 0]
    kids_up_sr_down = [r for r in rows if r["kid_delta"] > 0 and r["sr_delta"] < 0]
    kids_down_sr_up = [r for r in rows if r["kid_delta"] < 0 and r["sr_delta"] > 0]
    print(f"\nQuadrants ({len(rows)} total):")
    print(f"  Both UP   (growing all ages):       {len(both_gained):4d}")
    print(f"  Both DOWN (shrinking all ages):     {len(both_lost):4d}")
    print(f"  Kids up, seniors down:              {len(kids_up_sr_down):4d}")
    print(f"  Kids down, seniors up (aging mix):  {len(kids_down_sr_up):4d}")


if __name__ == "__main__":
    main()
