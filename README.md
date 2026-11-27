# 🏎️ F1 Forecasting Engine

Probabilistic Formula 1 race and season forecasting: win, podium and
points probabilities for every driver before each Grand Prix, season
simulations for championship odds, and car-adjusted driver ratings.

> **Status: rebuilding.** This repository started as a college project
> (a random-forest regression of finishing position on 2014–2022 data,
> kept in [`legacy/`](legacy/)). It is being rebuilt around fresher data,
> a proper evaluation setup and stronger models. Steps 1–2 (data
> pipeline, evaluation framework) are done; see the [data audit](reports/data_audit.md) and the
> [project journal](docs/journal/), which explains each design decision.

## Roadmap

1. **Data pipeline** ✅: Jolpica-F1 (1950 to the latest race) and OpenF1
   (lap-level practice, qualifying and race data from 2023), cleaned into
   tidy parquet tables with shared keys.
2. **Evaluation** ✅: forecasts made after qualifying; walk-forward
   backtests over 2022–2026 with a hard guard against look-ahead;
   probability metrics (log-loss, Brier, calibration); grid and
   grid + team-form baselines. See the [backtest report](reports/backtest.md).
3. **Features**: Elo/TrueSkill-style driver and car ratings that widen
   their uncertainty at regulation resets, a driver-vs-car decomposition,
   qualifying pace (gap to pole, gap to teammate), practice long-run
   pace and tyre degradation, recent form, reliability, circuit character.
4. **Models**, all judged by walk-forward (season-by-season) validation:
   - baselines: grid order, grid + team
   - LightGBM ranking model
   - TabPFN
   - a set-Transformer over the whole grid trained with a Plackett-Luce
     (full finishing order) likelihood
   - separate models for retirements (mechanical vs incident)
5. **Products**: race-weekend probabilities, Monte Carlo championship
   odds, all-time car-adjusted driver ratings, and a public accuracy
   record updated after every race.

## Data sources

| Source | Coverage | Used for |
|---|---|---|
| [Jolpica-F1](https://github.com/jolpica/jolpica-f1) (Ergast successor) | 1950 to now | results, sprints, qualifying, lap charts (1996+), pit stops (2011+), standings |
| [OpenF1](https://openf1.org) | 2023 to now | every lap incl. practice and testing, sector times, speed traps, tyre stints, weather, race control |
| [FastF1](https://docs.fastf1.dev) (optional) | 2018 to now | same lap data for 2018–2022; since Oct 2026 needs your own F1 TV sign-in |

## Quick start

```bash
pip install -e ".[dev]"
f1predict pull jolpica      # ~15 MB download, ~20 s
f1predict pull openf1       # rate-limited: about 1.5 h the first time, cached after that
f1predict audit             # writes reports/data_audit.md
f1predict backtest          # writes reports/backtest.md
pytest
```

Data lands in `data/` (git-ignored): raw downloads in `data/raw`, tidy
tables in `data/processed/{jolpica,openf1}/*.parquet`.

## Layout

```
src/f1predict/
  data/jolpica.py        dump download, tidy tables, API top-up for new races
  data/openf1.py         cached per-session fetch, joined to Jolpica keys
  data/fastf1_sessions.py  optional FastF1 loader (uses your F1 TV sign-in)
  eras.py                technical-regulation eras and resets
  teams.py               team lineages (Toro Rosso → AlphaTauri → RB, ...)
  audit.py               data coverage and quality report
  dataset.py             one row per driver per Grand Prix (the modelling table)
  evaluation/            race simulator, walk-forward backtest, metrics, report
  models/                Plackett-Luce fitting and baselines
legacy/                  the original notebook and CSVs
reports/                 generated reports
```
