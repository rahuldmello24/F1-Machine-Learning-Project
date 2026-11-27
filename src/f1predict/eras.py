"""Technical-regulation eras.

A new era starts in a season where the technical rules changed enough to
reshuffle the competitive order. Models use this to widen uncertainty on
car performance at a reset instead of trusting last year's order.
"""

from __future__ import annotations

# first season of each era -> short description
ERA_STARTS: dict[int, str] = {
    1950: "Post-war formula",
    1961: "1.5 L engines",
    1966: "3.0 L engines",
    1983: "Flat-bottom / ground effect ban",
    1989: "Turbo ban, 3.5 L normally aspirated",
    1995: "3.0 L engines",
    1998: "Narrow track, grooved tyres",
    2006: "2.4 L V8",
    2009: "Aero overhaul, slicks, KERS",
    2014: "1.6 L turbo-hybrid power units",
    2017: "Wider cars and tyres",
    2022: "Ground-effect aerodynamics",
    2026: "50/50 hybrid power units, active aero",
}

MAJOR_RESETS = (2009, 2014, 2022, 2026)


def era_of(year: int) -> int:
    """Return the first season of the era ``year`` belongs to."""
    return max(start for start in ERA_STARTS if start <= year)


def is_reset(year: int) -> bool:
    return year in ERA_STARTS
