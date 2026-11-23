from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collect import collect, discover
from .core import analyze
from .synthetic import make_fixture


def main() -> None:
    parser = argparse.ArgumentParser(description="Options order-book imbalance study")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover", help="list liquid active Deribit options")
    d.add_argument("--currency", default="BTC")
    d.add_argument("--limit", type=int, default=10)
    c = sub.add_parser("collect", help="record one public option book")
    c.add_argument("--instrument", required=True)
    c.add_argument("--seconds", type=int, default=600)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--append", action="store_true", help="resume an interrupted capture")
    f = sub.add_parser("fixture", help="generate clearly synthetic demo data")
    f.add_argument("--output", type=Path, required=True)
    f.add_argument("--seed", type=int, default=7)
    a = sub.add_parser("analyze", help="evaluate chronological signal on saved capture")
    a.add_argument("--input", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--horizon-ms", type=int, default=1000)
    a.add_argument("--tolerance-ms", type=int, default=500)
    a.add_argument("--levels", type=int, default=5)
    args = parser.parse_args()
    if args.command == "discover":
        result = discover(args.currency, args.limit)
    elif args.command == "collect":
        result = collect(args.instrument, args.seconds, args.output, args.append)
    elif args.command == "fixture":
        result = make_fixture(args.output, args.seed)
    else:
        if args.horizon_ms <= 0 or args.tolerance_ms < 0 or args.levels <= 0:
            parser.error("horizon/levels must be positive and tolerance nonnegative")
        result = analyze(args.input, args.horizon_ms, args.tolerance_ms, args.levels)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    visible = ({k: v for k, v in result.items() if k != "sample_rows"}
               if isinstance(result, dict) else result)
    print(json.dumps(visible, indent=2))


if __name__ == "__main__":
    main()
