# Data audit

_Generated 2026-11-27 by `f1predict audit`._

## Sources

| source | years | status | what |
|---|---|---|---|
| Jolpica-F1 (dump + API top-up) | 1950–2026 | ✅ pulled | results, sprints, qualifying, laps (1996+), pit stops (2011+), standings |
| OpenF1 | 2023– | ⏳ not pulled | every lap incl. practice, sectors, speed traps, tyre stints, weather, pit lane, race control |
| FastF1 / F1 live timing | 2018– | 🔒 needs F1 TV sign-in | the same lap data for 2018–2022 + high-rate telemetry |

Latest race in the data: **Las Vegas Grand Prix 2026** (round 21, 2026-11-22).

## Jolpica coverage

Share of races that have each kind of data.

| year | races | entries_per_race | quali_times | race_laps | pit_stops | sprints |
|---|---|---|---|---|---|---|
| 1950 | 7 | 22.9 | 0% | 0% | 0% | 0 |
| 1960 | 10 | 21.5 | 0% | 0% | 0% | 0 |
| 1970 | 13 | 20.5 | 0% | 0% | 0% | 0 |
| 1980 | 14 | 24.0 | 0% | 0% | 0% | 0 |
| 1990 | 16 | 26.2 | 0% | 0% | 0% | 0 |
| 1994 | 16 | 26.1 | 94% | 0% | 0% | 0 |
| 1995 | 17 | 24.6 | 94% | 0% | 0% | 0 |
| 1996 | 16 | 20.5 | 44% | 100% | 0% | 0 |
| 1997 | 17 | 22.0 | 59% | 100% | 0% | 0 |
| 1998 | 16 | 21.7 | 44% | 100% | 0% | 0 |
| 1999 | 16 | 21.9 | 19% | 100% | 0% | 0 |
| 2000 | 17 | 21.9 | 24% | 100% | 0% | 0 |
| 2001 | 17 | 21.9 | 6% | 100% | 0% | 0 |
| 2002 | 17 | 21.1 | 12% | 100% | 0% | 0 |
| 2003 | 16 | 20.0 | 100% | 100% | 0% | 0 |
| 2004 | 18 | 20.0 | 100% | 100% | 0% | 0 |
| 2005 | 19 | 19.8 | 100% | 100% | 0% | 0 |
| 2006 | 18 | 22.0 | 100% | 100% | 0% | 0 |
| 2007 | 17 | 22.0 | 100% | 100% | 0% | 0 |
| 2008 | 18 | 20.4 | 100% | 100% | 0% | 0 |
| 2009 | 17 | 20.0 | 100% | 100% | 0% | 0 |
| 2010 | 19 | 24.0 | 100% | 100% | 0% | 0 |
| 2011 | 19 | 23.9 | 100% | 100% | 100% | 0 |
| 2012 | 20 | 23.9 | 100% | 100% | 100% | 0 |
| 2013 | 19 | 22.0 | 100% | 100% | 100% | 0 |
| 2014 | 19 | 21.4 | 100% | 100% | 100% | 0 |
| 2015 | 19 | 19.9 | 100% | 100% | 100% | 0 |
| 2016 | 21 | 22.0 | 100% | 100% | 100% | 0 |
| 2017 | 20 | 20.0 | 100% | 100% | 100% | 0 |
| 2018 | 21 | 20.0 | 100% | 100% | 100% | 0 |
| 2019 | 21 | 20.0 | 100% | 100% | 100% | 0 |
| 2020 | 17 | 20.0 | 100% | 100% | 100% | 0 |
| 2021 | 22 | 20.0 | 100% | 100% | 95% | 3 |
| 2022 | 22 | 20.0 | 100% | 100% | 100% | 3 |
| 2023 | 22 | 20.0 | 100% | 100% | 100% | 6 |
| 2024 | 24 | 20.0 | 100% | 100% | 100% | 6 |
| 2025 | 24 | 20.0 | 96% | 100% | 100% | 6 |
| 2026 | 21 | 22.0 | 100% | 100% | 100% | 6 |

**Takeaways:** results go back to 1950; qualifying lap times are complete from the mid-90s; lap-by-lap race data from 1996; pit stops from 2011. Pre-1996 data supports ratings (who beat whom) but not pace features.

## Race outcomes: the DNF problem

The original project coded every non-finisher as P20. Jolpica separates *why* a car didn't finish:

| period | finished | lapped | dnf_mechanical | dnf_incident | dsq | dns |
|---|---|---|---|---|---|---|
| 1950-69 | 18% | 32% | 38% | 7% | 0% | 4% |
| 1970-89 | 19% | 30% | 37% | 12% | 1% | 1% |
| 1990-2005 | 25% | 30% | 28% | 15% | 1% | 1% |
| 2006-13 | 49% | 29% | 12% | 10% | 0% | 0% |
| 2014-21 | 47% | 34% | 11% | 7% | 0% | 1% |
| 2022-26 | 63% | 22% | 12% | 2% | 0% | 1% |

Mechanical failures (car reliability) and incidents (driver/racing) are different processes and should be modelled separately from finishing order, not folded into it.

## Do regulation resets reshuffle the order?

Spearman correlation between consecutive seasons' constructor order (points per race, teams matched by lineage, e.g. Toro Rosso → AlphaTauri → RB). 1.0 = identical order, 0 = unrelated.

| year | constructor_order_rho | reset |
|---|---|---|
| 2005 | 0.67 |  |
| 2006 | 0.82 | **reset** |
| 2007 | 0.75 |  |
| 2008 | 0.91 |  |
| 2009 | 0.14 | **reset** |
| 2010 | 0.78 |  |
| 2011 | 0.96 |  |
| 2012 | 0.97 |  |
| 2013 | 0.92 |  |
| 2014 | 0.68 | **reset** |
| 2015 | 0.79 |  |
| 2016 | 0.85 |  |
| 2017 | 0.88 | **reset** |
| 2018 | 0.72 |  |
| 2019 | 0.81 |  |
| 2020 | 0.79 |  |
| 2021 | 0.81 |  |
| 2022 | 0.81 | **reset** |
| 2023 | 0.82 |  |
| 2024 | 0.81 |  |
| 2025 | 0.70 |  |
| 2026 | 0.65 | **reset** |

Mean carry-over in major reset years (2009, 2014, 2022, 2026): **0.57**; in non-reset years since 1996: **0.83**.

## How much does the grid decide the race?

Per-race Spearman correlation of grid vs. finishing position (classified finishers), averaged per season.

| year | grid_finish_rho | pole_win_rate | winner_mean_grid |
|---|---|---|---|
| 2010 | 0.63 | 0.42 | 2.00 |
| 2011 | 0.65 | 0.47 | 1.95 |
| 2012 | 0.51 | 0.50 | 2.40 |
| 2013 | 0.67 | 0.53 | 1.95 |
| 2014 | 0.61 | 0.47 | 2.32 |
| 2015 | 0.64 | 0.63 | 1.42 |
| 2016 | 0.64 | 0.62 | 1.62 |
| 2017 | 0.58 | 0.55 | 2.15 |
| 2018 | 0.58 | 0.48 | 2.48 |
| 2019 | 0.64 | 0.38 | 1.86 |
| 2020 | 0.60 | 0.59 | 2.47 |
| 2021 | 0.65 | 0.50 | 2.50 |
| 2022 | 0.53 | 0.45 | 2.91 |
| 2023 | 0.58 | 0.64 | 2.14 |
| 2024 | 0.73 | 0.46 | 2.54 |
| 2025 | 0.65 | 0.67 | 1.54 |
| 2026 | 0.64 | 0.71 | 2.24 |

## Circuit character (2014+)

Grid→finish correlation by circuit. Low values = races where the order shuffles most.

Most chaotic:

| circuit | races | grid_finish_rho |
|---|---|---|
| vegas | 4 | 0.40 |
| hockenheimring | 4 | 0.40 |
| americas | 12 | 0.51 |
| albert_park | 11 | 0.52 |
| interlagos | 12 | 0.53 |
| baku | 10 | 0.53 |
| sochi | 8 | 0.58 |
| sepang | 5 | 0.59 |

Most processional:

| circuit | races | grid_finish_rho |
|---|---|---|
| miami | 5 | 0.75 |
| suzuka | 11 | 0.75 |
| jeddah | 5 | 0.72 |
| ricard | 4 | 0.72 |
| shanghai | 9 | 0.70 |
| monaco | 12 | 0.69 |
| yas_marina | 12 | 0.69 |
| rodriguez | 11 | 0.69 |

## OpenF1 (2023+)

Not pulled yet. Run `f1predict pull openf1`.


## FastF1 / F1 live timing

Since mid-October 2026 F1's timing archive requires an F1 TV sign-in. Not pulled. With a subscription it would add lap-level practice data for 2018–2022, i.e. pace features before OpenF1 starts, covering the 2022 ground-effect reset.


## Known quirks

- 89 duplicate driver/race result rows, all 1950–1964: shared drives (one driver, two cars). Kept as-is.
- The 2026 calendar has a cancelled Saudi Arabian GP and a *Bahrain Grand Prix in Malaysia* (round 16); circuit-level features must key on the **circuit**, not the event name.
- Jolpica's API (used for rounds newer than the dump) has no sprint-qualifying results; the next dump fills them in.
- Pre-1996 laps are only the fastest lap per driver, not full lap charts.
