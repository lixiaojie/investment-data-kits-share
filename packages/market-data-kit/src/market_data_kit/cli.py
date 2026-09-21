"""Small public CLI. No personal scheduler or historical data imports."""
import argparse
import json
import sys


def main():
    import market_data_kit as kit
    parser = argparse.ArgumentParser(prog="mdk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local dependencies; no network request")
    bars = sub.add_parser("klines", help="Fetch daily bars and provenance as JSON")
    bars.add_argument("symbol")
    bars.add_argument("--days", type=int, default=120)
    bars.add_argument("--adjust", choices=["none", "qfq", "hfq"], default="none")
    bars.add_argument("--refresh", action="store_true")
    bars.add_argument("--allow-stale", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(kit.run_doctor_report())
        else:
            df = kit.load_klines(args.symbol, args.days, adjust=args.adjust,
                                 refresh=args.refresh, allow_stale=args.allow_stale)
            print(json.dumps({"meta": df.attrs, "rows": json.loads(df.to_json(orient="records", date_format="iso"))}, ensure_ascii=False))
    except (ValueError, kit.ProviderUnavailableError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
