# 01 · Data pipeline

**Goal:** replace the five static CSVs (frozen in 2022) with a pipeline
that can be re-run after every race and that contains the richer data
(practice laps, tyres, weather, retirement causes) later features need.

---

## 1. Why the old data had to go

| Old project | Problem | Now |
|---|---|---|
| Ergast CSVs downloaded once, ending 2022 | Ergast shut down in early 2025; no 2023–2026 data | Jolpica-F1, the maintained successor, up to the latest race |
| Only results + standings | Nothing about *pace*: no qualifying times, practice, tyres, weather | Qualifying times, every lap since 1996, pit stops, and (2023+) practice/testing laps, tyre stints, weather |
| Non-finishers coded as P20 (17% of rows) | Mixes "car broke" with "driver was slow" | Retirements labelled `dnf_mechanical` vs `dnf_incident` |
| `replace('\N', 20)` on every column | Silently corrupted unrelated columns | Missing values stay missing (`NA`) |

---

## 2. The three data sources and why each one

**Jolpica-F1** (`api.jolpi.ca`): community-run replacement for Ergast,
same data model. It is the only free source covering **1950 to today**.
It gives results, grid, qualifying, lap charts, pit stops, standings.
*Used for:* everything historical; the "spine" every other table joins to.

**OpenF1** (`api.openf1.org`): free historical data from **2023**,
built from F1's live-timing feed. It has what Jolpica lacks: **every
practice and testing lap**, sector times, speed-trap speeds, tyre
compound and age per stint, weather, race-control messages (safety cars,
red flags). *Used for:* pace features (practice long-run pace, tyre
degradation), which are the strongest signals available before a race.

**FastF1** (Python library): the same kind of lap data back to 2018.
Since October 2026 F1 requires an **F1 TV sign-in** for its timing
archive, so this is optional and runs on my own machine with my own
subscription. It would extend practice-pace features to 2018–2022.

*Rejected:* paid sports-data APIs (cost, and no advantage over the above
for F1); scraping F1.com (fragile, against terms); a community mirror
of the paywalled F1 archive (it bypasses F1's access control).

---

## 3. Design decisions, and why

### 3.1 Download the database dump, don't call the API thousands of times
Jolpica allows ~500 requests/hour. Rebuilding 77 seasons via the API
would take many hours. Jolpica publishes a full **database dump** (~15 MB
zip of CSVs), so one download gets everything. The dump is refreshed
with a delay, so races newer than it are **topped up from the API**
(`missing_rounds()` finds completed races with no results yet).

> Talking point: *"I treat the bulk dump as the base layer and the API as
> an incremental update. That's the same pattern as a full load plus
> incremental loads in a data warehouse."*

### 3.2 Tidy tables with readable keys
The raw dump is a normalised database (sessions → entries → team-drivers
→ drivers ...). I flatten it into seven **tidy** tables (one row per
observation, one column per variable): `rounds`, `results`, `qualifying`,
`laps`, `pitstops`, `driver_standings`, `team_standings`.

Every table is keyed on **`(year, round, driver)`**, using readable
references like `max_verstappen` and `red_bull`, not database ids. Those
references are identical in the dump and the API, so new rows from the
API line up with old ones automatically.

### 3.3 Parquet instead of CSV
Parquet is a columnar, compressed, typed format. 748k laps load in well
under a second, and types survive the round trip (a nullable integer
stays an integer instead of turning into a float or a string).

### 3.4 Retirement causes as their own label
Jolpica's status codes separate **finished / lapped / mechanical DNF /
incident DNF / DSQ / DNS**. These are different processes:
- *mechanical* = car reliability (a team property),
- *incident* = crashes/collisions (partly driver, partly luck),
- *finishing order* = pace.

The model will predict "does the car finish?" separately from "where
does it finish if it does?". That is a **hurdle model**, and it is the
proper fix for the old P20 hack.

### 3.5 Qualifying rank from the furthest segment reached
Qualifying has three knock-out segments (Q1 → Q2 → Q3). A driver who is
fastest in Q1 but knocked out in Q2 qualifies *behind* everyone in Q3.
So the final rank sorts by **furthest segment reached, then position
within it** (tested in `tests/test_data.py`). Best lap per segment is
kept, because *gap to pole* and *gap to teammate* will be features.

### 3.6 Polite, cached HTTP
Both APIs are free community services. `http.PoliteSession` spaces out
requests, retries network errors, and on HTTP **429 (Too Many Requests)**
waits and retries. OpenF1 responses are cached per session and endpoint
as gzipped JSON, so a re-run only fetches what's new.

### 3.7 Team lineages
Teams rename constantly: Minardi → Toro Rosso → AlphaTauri → RB;
Jordan → … → Racing Point → Aston Martin; Sauber → Alfa Romeo → Audi.
Car performance carries over through the **organisation** (factory,
staff, wind tunnel), not the name. `teams.py` maps every name to a
lineage, so year-to-year comparisons and future car ratings don't reset
just because of a rebrand.

### 3.8 Regulation eras
`eras.py` lists the seasons where technical rules changed enough to
reshuffle the order (2009, 2014, 2017, 2022, 2026, ...). Later, car
ratings will **widen their uncertainty** at these points, so the model
trusts last year's order less exactly when it is least reliable.

### 3.9 Pre-season testing kept, as round 0
OpenF1 includes winter testing. In a reset year like 2026, testing is
almost the *only* evidence of the new pecking order before round 1, so
it is kept and labelled `session = TEST`, `round = 0`.

### 3.10 Joining OpenF1 to Jolpica
- *Weekend:* OpenF1 "meetings" are matched to Jolpica rounds by season
  and race date (±3 days).
- *Driver:* OpenF1 identifies cars by **car number**. Car numbers are
  matched to drivers using that round's entry list. Result: 100% of
  race-weekend laps matched; testing is 97% (reserve drivers who never
  raced have no Jolpica entry).

---

## 4. What the audit found (`reports/data_audit.md`)

**Coverage.** Results and grid since 1950; qualifying times 1994–95 and
2003+ (Jolpica is missing most 1996–2002 qualifying); lap charts 1996+;
pit stops 2011+; OpenF1 practice/testing 2023+.

**Retirements have collapsed.** Mechanical DNFs fell from ~38% of
starts (1950s–80s) to ~12% today; incidents fell to ~2% in 2022–26.
Lumping them all as "P20" was wrong then and is worse now.

**Regulation resets do reshuffle the order, but less than expected.**
I measured the **Spearman rank correlation** between consecutive
seasons' constructor order (points per race, matched by lineage):
- normal years: **≈ 0.83** (the order mostly carries over),
- major resets (2009, 2014, 2022, 2026): **≈ 0.57**,
- 2009 was the real outlier at 0.14 (Brawn GP won from nowhere); 2026 is 0.65.

So history isn't useless after a reset. It's *less* reliable, which is
why the model should down-weight it at resets rather than throw it away.

**The grid matters a lot, and 2026 is no less predictable.** Average
per-race grid-vs-finish correlation is ~0.6; pole has won **71%** of
2026 races so far, the highest in the table.

**Circuits have character.** Las Vegas, Austin and Melbourne shuffle the
order most; Suzuka, Miami and Jeddah are the most processional. That
becomes a feature.

**Quirks found and handled:** 1950s shared drives (one driver in two
cars, kept); a 2026 "Bahrain GP" held at Sepang (so circuit features key
on the *circuit*, not the event name); one 2025 race with no qualifying
times.

---

## 5. Questions you should be able to answer

**Why not just keep the Kaggle/Ergast CSVs?**
They stop in 2022–2023 and Ergast no longer exists. The project's value
is forecasting upcoming races, which needs a source that updates.

**Why three sources instead of one?**
No single free source has both 70+ years of history and modern
practice/tyre data. Jolpica gives depth, OpenF1 gives detail.

**How do you keep the sources consistent?**
Everything joins on `(year, round, driver)` with Jolpica as the
reference. OpenF1 weekends match by date, drivers by car number, and
the match rates are checked in the audit.

**Why separate mechanical and incident DNFs?**
They're driven by different things (team reliability vs. racing
incidents) and both are distinct from pace. Modelling them separately
avoids teaching the model that a blown engine means "slow driver".

**What is Spearman correlation and why use it here?**
It's the correlation between *ranks*, not raw values. Finishing order
is a ranking, so it's the natural measure of "how similar are two
orders?". It's also robust to big point gaps at the top.

**What's the biggest data limitation?**
Detailed pace data (practice laps, tyres) only starts in 2023 for free,
so pace features have ~4 seasons of history; earlier seasons rely on
results-based ratings. FastF1 with F1 TV could extend that to 2018.

**How does it stay up to date?**
`f1predict pull jolpica` re-downloads the dump and tops up any newer
race from the API; `f1predict pull openf1` fetches only uncached
sessions. Later this will run automatically after each race.

---

## 6. Glossary

- **Tidy data**: one row per observation, one column per variable.
- **Parquet**: compressed, columnar, typed file format for tables.
- **Rate limit / HTTP 429**: an API's cap on requests; 429 means "slow down".
- **Spearman's ρ (rho)**: rank correlation, from −1 to 1.
- **Hurdle model**: first model whether something happens (finish the race), then model its size or outcome given that it did (finishing position).
- **Lineage**: the continuous organisation behind a series of team names.
- **Regulation reset**: a season with major technical rule changes.
