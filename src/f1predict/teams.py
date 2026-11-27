"""Team lineages: the same factory/organisation under different names.

Car performance carries over between seasons through the *organisation*
(people, facilities, wind tunnel), not through the badge on the car, so
ratings and year-over-year comparisons use the lineage id.
Covers 1995 onwards; earlier teams map to themselves.
"""

from __future__ import annotations

import pandas as pd

LINEAGE: dict[str, str] = {
    # Milton Keynes
    "stewart": "red_bull", "jaguar": "red_bull",
    # Faenza
    "minardi": "rb", "toro_rosso": "rb", "alphatauri": "rb",
    # Silverstone
    "jordan": "aston_martin", "mf1": "aston_martin", "spyker_mf1": "aston_martin", "spyker": "aston_martin",
    "force_india": "aston_martin", "racing_point": "aston_martin",
    # Hinwil
    "sauber": "audi", "bmw_sauber": "audi", "alfa": "audi",
    # Enstone
    "benetton": "alpine", "renault": "alpine", "lotus_f1": "alpine",
    # Brackley
    "tyrrell": "mercedes", "bar": "mercedes", "honda": "mercedes", "brawn": "mercedes",
    # Banbury
    "virgin": "manor", "marussia": "manor",
    # Leafield / Hingham
    "lotus_racing": "caterham",
    "footwork": "arrows",
    "ligier": "prost",
}


def lineage(team: str | pd.Series) -> str | pd.Series:
    if isinstance(team, pd.Series):
        return team.map(lambda t: LINEAGE.get(t, t))
    return LINEAGE.get(team, team)
