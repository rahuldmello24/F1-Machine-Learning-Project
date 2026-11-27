"""Command line entry point.

    f1predict pull jolpica [--force]   # dump + API top-up -> parquet
    f1predict pull openf1 [--years 2025 2026]
    f1predict pull fastf1               # needs F1 TV credentials, see README
    f1predict audit                     # writes reports/data_audit.md
"""

from __future__ import annotations

import argparse
import logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="f1predict")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pull = sub.add_parser("pull", help="download and tidy a data source")
    pull.add_argument("source", choices=["jolpica", "openf1", "fastf1"])
    pull.add_argument("--force", action="store_true", help="re-download the Jolpica dump")
    pull.add_argument("--years", type=int, nargs="*")
    pull.add_argument("--no-fetch", action="store_true", help="only rebuild parquet from the local cache")

    sub.add_parser("audit", help="write reports/data_audit.md")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "pull":
        from f1predict.data import jolpica

        if args.source == "jolpica":
            jolpica.build(force_download=args.force)
        elif args.source == "openf1":
            from f1predict.data import openf1

            if not args.no_fetch:
                openf1.fetch(args.years)
            openf1.tidy(jolpica.load("rounds"), jolpica.load("results"))
        elif args.source == "fastf1":
            from f1predict.data import fastf1_sessions

            if not args.no_fetch:
                fastf1_sessions.fetch(tuple(args.years) if args.years else fastf1_sessions.YEARS)
            fastf1_sessions.tidy(jolpica.load("results"))
    elif args.cmd == "audit":
        from f1predict.audit import write_report

        write_report()
        print("wrote reports/data_audit.md")


if __name__ == "__main__":
    main()
