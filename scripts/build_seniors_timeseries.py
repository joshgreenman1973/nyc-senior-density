"""
Build per-tract time series of senior (65+) population, on 2010 tract boundaries.

Inputs (all from fetch_seniors.py):
  data/sr_2000.json, sr_2010.json, sr_2020.json
  data/acs5_sr_2011.json ... acs5_sr_2023.json

Plus, optionally, pre-2000 senior counts on 2010 boundaries from a future
NHGIS extract (not yet available — placeholder pipeline below).

Outputs:
  docs/seniors_counts.json        {years: [...], tracts: {gj: [count, ...]}}
  docs/seniors_density.json       {years: [...], tracts: {gj: [density, ...]}}
  docs/seniors_bands.json         {years: [...], bands: [...], tracts: {gj: {band: {y: c}}}}
  docs/seniors_summary.json       {total: {y: regional_count}}
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "docs"

YEARS_DEC = [2000, 2010, 2020]
YEARS_ACS = list(range(2011, 2024))
DATA_YEARS = sorted(set(YEARS_DEC + YEARS_ACS))   # years that have measured data
ALL_YEARS = list(range(2000, 2024))                # contiguous output: 24 years

BANDS = ["65_74", "75_84", "85plus"]


def load_year(year):
    if year in YEARS_DEC:
        path = DATA / f"sr_{year}.json"
    else:
        path = DATA / f"acs5_sr_{year}.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text())
    # GEOID -> {"total": n, "by_band": {...}}
    out = {}
    for r in rows:
        # 2020 GEOIDs use 2020 tract boundaries; the kid pipeline joins them
        # to 2010 tracts by string match (most are unchanged). Replicate that.
        out[r["geoid"]] = r
    return out


def gj_to_geoid(gj):
    # G3600610002602 -> 36061002602
    return gj[1:3] + gj[4:7] + gj[8:14]


def main():
    base = json.loads((WEB / "tracts_base.geojson").read_text())
    wanted_gjs = [f["properties"]["gisjoin"] for f in base["features"]]
    area_by_gj = {f["properties"]["gisjoin"]: f["properties"]["land_sqmi"]
                  for f in base["features"]}

    per_year = {y: load_year(y) for y in DATA_YEARS}
    per_year = {y: v for y, v in per_year.items() if v is not None}
    years = ALL_YEARS  # contiguous 2000..2023
    print(f"data years: {sorted(per_year.keys())}")
    print(f"output years (contiguous): {years[0]}..{years[-1]} ({len(years)} years)")

    # Build tract series
    counts = {}
    bands = {}
    for gj in wanted_gjs:
        geoid = gj_to_geoid(gj)
        # Counts: build contiguous 2000..2023 array, None for missing years
        cseries = []
        bs = {b: {} for b in BANDS}
        any_data = False
        for y in years:
            rec = per_year.get(y, {}).get(geoid) if y in per_year else None
            if rec is None:
                cseries.append(None)
                continue
            cseries.append(rec["total"])
            any_data = True
            for b in BANDS:
                bs[b][y] = rec["by_band"][b]
        # Linear-interp gaps. For seniors we have 2000, 2010, 2011-2023, so the
        # only gap is 2001-2009.
        cseries = interp_gaps(years, cseries)
        if any_data:
            counts[gj] = cseries
            # only persist bands if at least one band-year is non-None
            if any(bs[b] for b in BANDS):
                bands[gj] = bs

    # Density
    density = {}
    for gj, c in counts.items():
        a = area_by_gj.get(gj)
        if not a or a < 0.005:
            continue
        density[gj] = [round(v / a, 1) if v is not None else None for v in c]

    # Summary totals + which years are measured (vs interpolated)
    summary = {"total": {}, "real_anchor_years": []}
    for i, y in enumerate(years):
        s = sum((c[i] or 0) for c in counts.values())
        summary["total"][y] = s
        # 2000, 2010, 2020 are decennials; 2011-2023 are ACS - all measured.
        # 2001-2009 are interpolated.
        if y in (2000, 2010, 2020) or 2011 <= y <= 2023:
            summary["real_anchor_years"].append(y)

    out_counts = {"years": years, "tracts": counts}
    out_density = {"years": years, "tracts": density}
    out_bands = {"years": years, "bands": BANDS, "tracts": bands}

    (WEB / "seniors_counts.json").write_text(json.dumps(out_counts, separators=(",", ":")))
    (WEB / "seniors_density.json").write_text(json.dumps(out_density, separators=(",", ":")))
    (WEB / "seniors_bands.json").write_text(json.dumps(out_bands, separators=(",", ":")))
    (WEB / "seniors_summary.json").write_text(json.dumps(summary))

    print(f"wrote seniors_counts.json    ({len(counts)} tracts, {len(years)} years)")
    print(f"wrote seniors_density.json   ({len(density)} tracts)")
    print(f"wrote seniors_bands.json     ({len(bands)} tracts)")
    print(f"regional 65+ totals:")
    for y in [2000, 2010, 2020, 2023]:
        if y in summary["total"]:
            print(f"  {y}: {summary['total'][y]:,}")


def interp_gaps(years, vals):
    """Fill internal Nones with linear interpolation between bracketing points."""
    out = list(vals)
    n = len(out)
    i = 0
    while i < n:
        if out[i] is not None:
            i += 1; continue
        # find prev
        j = i - 1
        while j >= 0 and out[j] is None:
            j -= 1
        # find next
        k = i
        while k < n and out[k] is None:
            k += 1
        if j < 0 or k >= n:
            i = k; continue
        v0, v1 = out[j], out[k]
        for m in range(i, k):
            t = (m - j) / (k - j)
            out[m] = round(v0 + (v1 - v0) * t, 1)
        i = k
    return out


if __name__ == "__main__":
    main()
