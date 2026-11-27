# 02 · Evaluation framework and baselines

**Goal:** decide *exactly* how forecasts are made and scored **before**
building any features, so every later idea has to prove it helps, and
so the model can't accidentally cheat.

Results: [`reports/backtest.md`](../../reports/backtest.md).

---

## 1. Why evaluation comes first

The original project had three evaluation problems:

1. **Shuffled K-fold cross-validation.** Races were mixed randomly, so
   the model was trained on 2019 to "predict" 2016. In time-ordered data
   that inflates scores: the model is partly remembering the future.
2. **A weak benchmark** ("finish where you started").
3. **One metric (MSE) that doesn't fit the question.** Nobody asks "what's
   Hamilton's predicted position, ±4.7?". They ask "who'll win?", "what
   are the podium chances?", "will he score points?".

Fixing these first means every number from step 3 onwards is honest.

---

## 2. Decisions

### 2.1 The forecast moment: after qualifying, before the race
A forecast can only use what's known at that moment. We forecast **after
qualifying**, so the starting grid is known. It's the strongest single
signal and gives the most accurate forecast. (A "before the weekend"
forecast, without the grid, can be added later for season simulations.)

### 2.2 The unit of data: one row per driver per Grand Prix
`dataset.build_entries()` builds this table. Sprints are excluded (they
are separate, shorter races; they can become features later).

### 2.3 What counts as the truth: the full finishing order
`finish_order` ranks **every** starter: classified finishers by position,
then non-finishers by laps completed. `finished` records whether the car
was classified. A retirement is never a fake "P20". It's a separate
outcome the model must predict (`p_dnf`).

### 2.4 One output format for every model: strength + retirement probability
Every model, from the simplest baseline to the future Transformer, outputs
two numbers per driver:
- **strength**: how likely the driver is to beat the others (on a log scale),
- **p_dnf**: probability of not finishing.

A **race simulator** turns those into probabilities for every position:
1. each car retires with probability `p_dnf`;
2. the finishers are ordered by a **Plackett-Luce** model: the winner is
   drawn with probability ∝ e^strength, then 2nd from the rest, and so on;
3. retired cars go to the back.

Simulating 20,000 races per Grand Prix gives P(win), P(podium),
P(points) and expected position for each driver. Because every model
speaks this one "language", they are directly comparable, and the
simulator can later be reused for whole-season championship simulations.

> **Gumbel-max trick:** adding random Gumbel noise to each strength and
> sorting produces an exact Plackett-Luce sample. That's why 20,000
> simulated races take milliseconds.

### 2.5 Walk-forward backtesting
For each test season (2022–2026):
1. **fit** the model on all seasons before it;
2. for each race, in calendar order, **predict** using only races dated
   *before* it, so in-season form updates race by race, exactly as it
   would live.

Test seasons include **two regulation resets (2022, 2026)**, so we see
how models cope when history is least reliable.

### 2.6 A hard guard against look-ahead (data leakage)
`backtest._check_no_lookahead` runs on **every** prediction and fails if:
- the history contains any race on/after the race being predicted, or
- the race frame contains any outcome column (finishing order, points...).

A test (`test_backtest_never_shows_the_future`) uses a deliberately
"cheating" model to confirm it can't see the future, and
`test_team_form_is_point_in_time` checks that changing a race's result
doesn't change the features used to predict that same race.

### 2.7 Metrics

| Metric | Question it answers | Better |
|---|---|---|
| **winner log-loss** | how much probability did we give the actual winner? (−log p) | lower |
| winner hit | did the favourite win? | higher |
| **podium Brier** | how accurate are podium probabilities? (mean squared error vs 0/1) | lower |
| points Brier | same for top 10 | lower |
| DNF Brier | same for retirements | lower |
| Spearman | does the predicted order match the actual order? | higher |
| top-3 overlap | how many of the podium did we name? | higher |
| **calibration table** | when we say 30%, does it happen ~30% of the time? | predicted ≈ observed |

**Log-loss** is the headline metric because it rewards being *confident
and right* and harshly punishes *confident and wrong*, which is exactly
what a probability forecast should be judged on. Guessing uniformly among
20 drivers scores log(20) ≈ 3.0.

### 2.8 Baselines
- **`grid`**: strength from starting slot only (`a·log(slot) + b·slot`,
  fitted), one average retirement rate for everybody.
- **`grid+team_form`**: adds each team's average finishing percentile
  over its last 5 races, and each team's recent retirement rate (shrunk
  toward the average so one bad weekend doesn't dominate).

The real models in later steps must beat these.

*Not available:* bookmaker odds, the strongest public benchmark. There
is no free historical source, so this is noted as a limitation.

---

## 3. Results (2022–2026, 113 races)

| model | winner log-loss | favourite won | podium Brier | Spearman |
|---|---|---|---|---|
| grid | 1.588 | 58% | 0.074 | 0.63 |
| grid + team form | **1.483** | 58% | **0.069** | **0.65** |

- Even grid alone is far better than guessing (1.59 vs 3.0): the grid
  carries most of the information.
- Team form helps most in **2023** (Red Bull dominance: knowing the car is
  dominant matters more than its grid slot) and in **2022** (a reset where
  last year's order was misleading, but in-season form caught up fast).
  It helps least in 2025–26.

### The most useful finding: the baselines are under-confident at the front
Calibration shows that when the grid baseline gives a driver a 50–65%
podium chance, they actually reach the podium ~71% of the time; and the
backmarkers it gives 5–10% almost never make it (~2%).

**Why:** Plackett-Luce assumes the same amount of randomness at every
position. But the front of an F1 race is much more predictable than the
midfield scrap. Fitted on the *whole* order, the model learns the
midfield's noise and applies it to the front.

**Check:** fitting the same baseline on only the top-3/top-5 finishers
improves winner log-loss from 1.60 → ~1.47 and fixes most of the
under-confidence.

**Consequence for the real models:** strength should be fitted with
extra weight on the front of the order (or with position-dependent
noise), and retirement probability should differ by car rather than be
one average. Both are planned for step 4.

---

## 4. Questions you should be able to answer

**Why not use normal (shuffled) cross-validation?**
Races are time-ordered. Shuffling lets the model learn from the future,
which inflates scores. Walk-forward testing mimics real use: train on the
past, predict the next race.

**What is data leakage, and how did you prevent it?**
Using information at training/prediction time that wouldn't be available
in reality, e.g. end-of-season standings to predict mid-season races.
Prevented structurally (the backtester only passes earlier races and
strips outcome columns) and verified by tests, including a model that
tries to cheat.

**Why predict probabilities instead of a position?**
Races are uncertain. "60% win chance" is more useful and more honest than
"predicted position 1.4". Probabilities can also be checked
(calibration) and combined (season simulations).

**What is Plackett-Luce?**
A model for rankings: pick the winner with probability proportional to
each competitor's strength, then pick second from the remaining ones,
and so on. It's the natural model for "who beats whom" in a race.

**What is log-loss, and why is it your main metric?**
−log(probability given to what actually happened). It rewards confident
correct forecasts and heavily penalises confident wrong ones, so a model
can't score well by being vague or by being overconfident.

**What is calibration?**
Whether probabilities mean what they say: things forecast at 30% should
happen about 30% of the time. A model can rank well but be badly
calibrated, which matters if anyone uses the numbers.

**Why separate "does the car finish" from "where does it finish"?**
They're different processes (reliability/incidents vs pace), and mixing
them was the original project's biggest modelling flaw. This is called a
hurdle model.

**What did the baselines teach you?**
The grid explains most of the result; team form adds real information;
and a single Plackett-Luce noise level makes front-runners look less
certain than they are, which is a concrete design target for the real model.

---

## 5. Glossary

- **Walk-forward backtest**: repeatedly train on the past and test on the next period.
- **Data leakage / look-ahead bias**: accidentally using future information.
- **Plackett-Luce**: probability model over rankings.
- **Gumbel-max trick**: sample a Plackett-Luce ranking by adding Gumbel noise and sorting.
- **Maximum likelihood**: choose parameters that make the observed results most probable.
- **Log-loss**: −log of the probability assigned to the actual outcome.
- **Brier score**: mean squared difference between probability and the 0/1 outcome.
- **Calibration**: agreement between forecast probabilities and observed frequencies.
- **Shrinkage**: pulling a noisy estimate (one team's DNF rate) toward an average.
