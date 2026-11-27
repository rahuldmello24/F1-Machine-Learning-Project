"""Data audit: what each source covers, how clean it is, and a first look
at the questions the model has to answer (how much do regulation resets
reshuffle the order? how much does the grid decide the race?).

Writes ``reports/data_audit.md``.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from f1predict.data import jolpica
from f1predict.eras import ERA_STARTS, MAJOR_RESETS
from f1predict.paths import FASTF1_OUT, OPENF1_OUT, REPORTS_DIR, ensure
from f1predict.teams import lineage

log = logging.getLogger(__name__)


def md_table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    df = df.copy()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else floatfmt.format(v))
            else:
                cells.append("" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


# ------------------------------------------------------------------ Jolpica
def jolpica_coverage(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    res = t["results"].query("session_type == 'R'")
    races = res.groupby("year")["round"].nunique().rename("races")
    entries = (res.groupby("year").size() / races).rename("entries_per_race")
    q = t["qualifying"].query("kind == 'Q'")
    q_rounds = q.dropna(subset=["best_s"]).groupby("year")["round"].nunique()
    lap_rounds = t["laps"].query("session_type == 'R'").groupby("year")["round"].nunique()
    pit_rounds = t["pitstops"].groupby("year")["round"].nunique()
    sprint = t["results"].query("session_type == 'SR'").groupby("year")["round"].nunique()
    df = pd.concat(
        [races, entries, (q_rounds / races).rename("quali_times"), (lap_rounds / races).rename("race_laps"),
         (pit_rounds / races).rename("pit_stops"), sprint.rename("sprints")], axis=1
    ).fillna(0)
    df.index.name = "year"
    return df


def outcome_mix(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    res = t["results"].query("session_type == 'R'").copy()
    bins = [1949, 1969, 1989, 2005, 2013, 2021, 2030]
    labels = ["1950-69", "1970-89", "1990-2005", "2006-13", "2014-21", "2022-26"]
    res["period"] = pd.cut(res["year"], bins=bins, labels=labels)
    mix = res.groupby("period", observed=True)["outcome"].value_counts(normalize=True).unstack(fill_value=0)
    cols = [c for c in ["finished", "lapped", "dnf_mechanical", "dnf_incident", "dsq", "dns"] if c in mix]
    return mix[cols]


def _spearman(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(j) < 4:
        return np.nan
    return j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank())


def order_carryover(t: dict[str, pd.DataFrame], first_year: int = 1996) -> pd.DataFrame:
    """Spearman correlation between consecutive seasons' constructor
    order (points per race, by team lineage). Low = the order reshuffled."""
    res = t["results"].query("session_type in ['R', 'SR']").copy()
    res["lineage"] = lineage(res["team"])
    races = res.query("session_type == 'R'").groupby("year")["round"].nunique()
    ppr = res.groupby(["year", "lineage"])["points"].sum().div(races, level="year").rename("ppr")
    # also driver-level: points per race for drivers who raced both seasons
    rows = []
    years = sorted(y for y in res["year"].unique() if y >= first_year)
    for y in years:
        if y - 1 not in races.index:
            continue
        prev, cur = ppr.xs(y - 1, level="year"), ppr.xs(y, level="year")
        rows.append({"year": y, "constructor_order_rho": _spearman(prev, cur),
                     "reset": "**reset**" if y in ERA_STARTS else ""})
    return pd.DataFrame(rows)


def grid_vs_finish(t: dict[str, pd.DataFrame], first_year: int = 2010) -> pd.DataFrame:
    res = t["results"].query("session_type == 'R' and year >= @first_year").copy()
    res = res[res["grid"] > 0]
    res["finish"] = res["position"].astype(float)
    per_race = res.dropna(subset=["finish"]).groupby(["year", "round"]).apply(
        lambda g: g["grid"].rank().corr(g["finish"].rank()), include_groups=False
    ).rename("rho")
    winners = res.query("position == 1")
    out = pd.DataFrame({
        "grid_finish_rho": per_race.groupby("year").mean(),
        "pole_win_rate": (winners["grid"] == 1).groupby(winners["year"]).mean(),
        "winner_mean_grid": winners.groupby("year")["grid"].mean(),
    })
    out.index.name = "year"
    return out.reset_index()


def circuit_character(t: dict[str, pd.DataFrame], first_year: int = 2014, min_races: int = 4) -> pd.DataFrame:
    res = t["results"].query("session_type == 'R' and year >= @first_year and grid > 0").dropna(subset=["position"])
    rounds = t["rounds"][["year", "round", "circuit"]]
    res = res.merge(rounds, on=["year", "round"])
    per_race = res.groupby(["circuit", "year", "round"]).apply(
        lambda g: g["grid"].rank().corr(g["position"].astype(float).rank()), include_groups=False
    ).rename("rho").reset_index()
    agg = per_race.groupby("circuit").agg(races=("rho", "size"), grid_finish_rho=("rho", "mean"))
    return agg[agg["races"] >= min_races].sort_values("grid_finish_rho").reset_index()


# ------------------------------------------------------------------ OpenF1
def openf1_summary() -> tuple[pd.DataFrame, dict] | None:
    if not (OPENF1_OUT / "sessions.parquet").exists():
        return None
    s = pd.read_parquet(OPENF1_OUT / "sessions.parquet")
    laps = pd.read_parquet(OPENF1_OUT / "laps.parquet") if (OPENF1_OUT / "laps.parquet").exists() else pd.DataFrame()
    stints = pd.read_parquet(OPENF1_OUT / "stints.parquet") if (OPENF1_OUT / "stints.parquet").exists() else pd.DataFrame()
    weather = pd.read_parquet(OPENF1_OUT / "weather.parquet") if (OPENF1_OUT / "weather.parquet").exists() else pd.DataFrame()
    order = ["TEST", "FP1", "FP2", "FP3", "SQ", "SR", "Q", "R"]
    sess = s.pivot_table(index="year", columns="session", values="session_key", aggfunc="nunique").reindex(columns=order).fillna(0).astype(int)
    lap_counts = laps.groupby(["year", "session"]).size().unstack().reindex(columns=order).fillna(0).astype(int) if len(laps) else None
    stats = {
        "sessions": len(s),
        "sessions_mapped_to_round": s["round"].notna().mean(),
        "laps": len(laps),
        "laps_with_time": laps["lap_duration"].notna().mean() if len(laps) else np.nan,
        "laps_mapped_to_driver": laps["driver"].notna().mean() if len(laps) else np.nan,
        "practice_laps": int(laps["session"].isin(["FP1", "FP2", "FP3"]).sum()) if len(laps) else 0,
        "stints": len(stints),
        "stints_with_compound": stints["compound"].notna().mean() if len(stints) else np.nan,
        "sessions_with_weather": weather["session_key"].nunique() / len(s) if len(weather) else 0,
        "lap_counts": lap_counts,
    }
    return sess.reset_index(), stats


# ------------------------------------------------------------------ report
def write_report() -> str:
    t = {name: jolpica.load(name) for name in ("rounds", "results", "qualifying", "laps", "pitstops", "driver_standings")}
    cov = jolpica_coverage(t)
    mix = outcome_mix(t)
    carry = order_carryover(t)
    gvf = grid_vs_finish(t)
    circ = circuit_character(t)
    of1 = openf1_summary()

    last = t["results"].query("session_type == 'R'").sort_values(["year", "round"]).iloc[-1]
    last_round = t["rounds"].query("year == @last.year and round == @last['round']").iloc[0]

    L: list[str] = []
    add = L.append
    add("# Data audit\n")
    add(f"_Generated {date.today().isoformat()} by `f1predict audit`._\n")
    add("## Sources\n")
    add(md_table(pd.DataFrame([
        {"source": "Jolpica-F1 (dump + API top-up)", "years": f"1950–{int(last.year)}", "status": "✅ pulled",
         "what": "results, sprints, qualifying, laps (1996+), pit stops (2011+), standings"},
        {"source": "OpenF1", "years": "2023–", "status": "✅ pulled" if of1 else "⏳ not pulled",
         "what": "every lap incl. practice, sectors, speed traps, tyre stints, weather, pit lane, race control"},
        {"source": "FastF1 / F1 live timing", "years": "2018–", "status": "🔒 needs F1 TV sign-in",
         "what": "the same lap data for 2018–2022 + high-rate telemetry"},
    ])))
    add(f"\nLatest race in the data: **{last_round['name']} {int(last.year)}** (round {int(last['round'])}, {last_round['date'].date()}).\n")

    add("## Jolpica coverage\n")
    add("Share of races that have each kind of data.\n")
    show = cov.reset_index()
    show = pd.concat([show[show.year.isin([1950, 1960, 1970, 1980, 1990])], show[show.year >= 1994]])
    show = show.assign(**{c: show[c].map(_pct) for c in ["quali_times", "race_laps", "pit_stops"]},
                       races=show["races"].astype(int), sprints=show["sprints"].astype(int))
    add(md_table(show, "{:.1f}"))
    add("\n**Takeaways:** results (incl. grid) go back to 1950; qualifying lap times exist for 1994–95 and "
        "are complete from 2003, but Jolpica is missing most 1996–2002 qualifying sessions; lap-by-lap "
        "race data from 1996; pit stops from 2011. Pre-1996 data supports ratings (who beat whom) "
        "but not pace features.\n")

    add("## Race outcomes: the DNF problem\n")
    add("The original project coded every non-finisher as P20. Jolpica separates *why* a car didn't finish:\n")
    add(md_table(mix.reset_index().assign(**{c: mix[c].map(_pct).values for c in mix.columns})))
    add("\nMechanical failures (car reliability) and incidents (driver/racing) are different processes and "
        "should be modelled separately from finishing order, not folded into it.\n")

    add("## Do regulation resets reshuffle the order?\n")
    add("Spearman correlation between consecutive seasons' constructor order (points per race, "
        "teams matched by lineage, e.g. Toro Rosso → AlphaTauri → RB). 1.0 = identical order, 0 = unrelated.\n")
    c = carry.copy()
    reset_mean = c[c.year.isin(MAJOR_RESETS)]["constructor_order_rho"].mean()
    other_mean = c[~c.year.isin(ERA_STARTS)]["constructor_order_rho"].mean()
    add(md_table(c[c.year >= 2005]))
    add(f"\nMean carry-over in major reset years ({', '.join(map(str, MAJOR_RESETS))}): **{reset_mean:.2f}**; "
        f"in non-reset years since 1996: **{other_mean:.2f}**.\n")

    add("## How much does the grid decide the race?\n")
    add("Per-race Spearman correlation of grid vs. finishing position (classified finishers), averaged per season.\n")
    add(md_table(gvf))
    add("\n## Circuit character (2014+)\n")
    add("Grid→finish correlation by circuit. Low values = races where the order shuffles most.\n")
    add("Most chaotic:\n")
    add(md_table(circ.head(8)))
    add("\nMost processional:\n")
    add(md_table(circ.tail(8).iloc[::-1]))

    add("\n## OpenF1 (2023+)\n")
    if of1:
        sess, st = of1
        add("Sessions per season:\n")
        add(md_table(sess))
        if st["lap_counts"] is not None:
            add("\nLaps per season and session:\n")
            add(md_table(st["lap_counts"].reset_index()))
        add("\n" + md_table(pd.DataFrame([
            {"check": "sessions matched to a Jolpica round", "value": _pct(st["sessions_mapped_to_round"])},
            {"check": "laps total / practice laps", "value": f"{st['laps']:,} / {st['practice_laps']:,}"},
            {"check": "laps with a lap time", "value": _pct(st["laps_with_time"])},
            {"check": "laps matched to a Jolpica driver", "value": _pct(st["laps_mapped_to_driver"])},
            {"check": "tyre stints with compound", "value": _pct(st["stints_with_compound"])},
            {"check": "sessions with weather", "value": _pct(st["sessions_with_weather"])},
        ])))
    else:
        add("Not pulled yet. Run `f1predict pull openf1`.\n")

    add("\n## FastF1 / F1 live timing\n")
    if (FASTF1_OUT / "laps.parquet").exists():
        add("Pulled (see `data/processed/fastf1`).\n")
    else:
        add("Since mid-October 2026 F1's timing archive requires an F1 TV sign-in. Not pulled. With a "
            "subscription it would add lap-level practice data for 2018–2022, i.e. pace features "
            "before OpenF1 starts, covering the 2022 ground-effect reset.\n")

    add("\n## Known quirks\n")
    add("- 89 duplicate driver/race result rows, all 1950–1964: shared drives (one driver, two cars). Kept as-is.\n"
        "- The 2026 calendar has a cancelled Saudi Arabian GP and a *Bahrain Grand Prix in Malaysia* (round 16, held at Sepang); "
        "circuit-level features must key on the **circuit**, not the event name.\n"
        "- Jolpica's API (used for rounds newer than the dump) has no sprint-qualifying results; the next dump fills them in.\n"
        "- 2025 round 6 has no qualifying lap times in the dump (grid is present).\n"
        "- Pre-1996 laps are only the fastest lap per driver, not full lap charts.\n")

    ensure(REPORTS_DIR)
    text = "\n".join(L)
    (REPORTS_DIR / "data_audit.md").write_text(text)
    return text
