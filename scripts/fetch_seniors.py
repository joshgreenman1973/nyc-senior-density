"""
Fetch population aged 65+ by tract for 2000-2023.

Sources:
  - 2000 decennial SF1, table P012 (male 020-025, female 044-049)
  - 2010 decennial SF1, table P012 (same layout)
  - 2020 decennial DHC, table P12 (P12_020N..025N + P12_044N..049N)
  - 2011-2023 ACS 5-year, table B01001

Six male and six female cells make up "65 and over" in each table:
  Male: 65-66, 67-69, 70-74, 75-79, 80-84, 85+
  Female: same six bands

Output (cached per year):
  data/sr_2000.json   [{"geoid":..., "total":..., "by_band":{...}}, ...]
  data/sr_2010.json
  data/sr_2020.json
  data/acs5_sr_2011.json
  ...
  data/acs5_sr_2023.json

These feed build_seniors_timeseries.py, which produces
docs/seniors_counts.json + docs/seniors_density.json + docs/seniors_bands.json.
"""

import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

STATE_COUNTIES = {
    "36": ["005", "047", "061", "081", "085", "119", "059"],
    "34": ["003", "017", "039", "023"],
}

# 65+ index numbers (zero-padded). These map onto:
#   65_74  = 65-66 + 67-69 + 70-74
#   75_84  = 75-79 + 80-84
#   85plus = 85+
P012_MALE_65PLUS = ["020", "021", "022", "023", "024", "025"]
P012_FEMALE_65PLUS = ["044", "045", "046", "047", "048", "049"]

BAND_DEF = {
    "65_74":  [0, 1, 2],   # 65-66, 67-69, 70-74
    "75_84":  [3, 4],      # 75-79, 80-84
    "85plus": [5],         # 85+
}


def dec_var_names(year, indices):
    if year == 2020:
        return [f"P12_{i}N" for i in indices]
    return [f"P012{i}" for i in indices]


def acs_var_names(indices):
    return [f"B01001_{i}E" for i in indices]


def normalize_tract(t):
    return t + "00" if len(t) == 4 else t


def fetch_year(year, source):
    """source is 'decennial' or 'acs'."""
    if source == "decennial":
        if year == 2020:
            base = "https://api.census.gov/data/2020/dec/dhc"
        else:
            base = f"https://api.census.gov/data/{year}/dec/sf1"
        male = dec_var_names(year, P012_MALE_65PLUS)
        female = dec_var_names(year, P012_FEMALE_65PLUS)
    else:
        base = f"https://api.census.gov/data/{year}/acs/acs5"
        male = acs_var_names(P012_MALE_65PLUS)
        female = acs_var_names(P012_FEMALE_65PLUS)

    all_vars = male + female
    get = ",".join(["NAME"] + all_vars)
    out = []
    for state, counties in STATE_COUNTIES.items():
        for county in counties:
            params = {
                "get": get,
                "for": "tract:*",
                "in": f"state:{state} county:{county}",
            }
            r = requests.get(base, params=params, timeout=60)
            if r.status_code != 200:
                print(f"   {year} {state}{county}: HTTP {r.status_code}")
                continue
            header, *body = r.json()
            for row in body:
                d = dict(zip(header, row))
                try:
                    male_vals = [int(d[v]) for v in male]
                    female_vals = [int(d[v]) for v in female]
                except (ValueError, TypeError):
                    continue
                # Total 65+
                total = sum(male_vals) + sum(female_vals)
                # Band breakdown
                by_band = {}
                for band, idxs in BAND_DEF.items():
                    by_band[band] = sum(male_vals[i] for i in idxs) + sum(female_vals[i] for i in idxs)
                geoid = d["state"] + d["county"] + normalize_tract(d["tract"])
                out.append({"geoid": geoid, "total": total, "by_band": by_band})
            time.sleep(0.05)
    return out


def main():
    # Decennials
    for year in [2000, 2010, 2020]:
        path = DATA / f"sr_{year}.json"
        if path.exists():
            print(f"skip decennial {year} (cached)")
            continue
        print(f"fetching decennial {year}...")
        rows = fetch_year(year, "decennial")
        path.write_text(json.dumps(rows))
        total = sum(r["total"] for r in rows)
        print(f"  {len(rows)} tracts, total 65+ {total:,}")

    # ACS
    for ey in range(2011, 2024):
        path = DATA / f"acs5_sr_{ey}.json"
        if path.exists():
            print(f"skip ACS {ey} (cached)")
            continue
        print(f"fetching ACS {ey}...")
        rows = fetch_year(ey, "acs")
        path.write_text(json.dumps(rows))
        total = sum(r["total"] for r in rows)
        print(f"  {len(rows)} tracts, total 65+ {total:,}")


if __name__ == "__main__":
    main()
