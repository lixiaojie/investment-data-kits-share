"""A minimal workbench integration; no network unless --demo is absent."""
import argparse
import json
from pathlib import Path
import tempfile


def main():
    import market_data_kit as kit
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Synthetic offline example")
    parser.add_argument("--symbol", default="US.AAPL")
    parser.add_argument("--provider", choices=["yfinance", "akshare", "push2", "futu"], default="yfinance")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="workbench-example-") as runtime:
        kit.init(data_root=Path(runtime) / "market", use_stubs=args.demo, providers=(args.provider,))
        try:
            df = kit.load_klines(args.symbol, days=120)
        except kit.ProviderUnavailableError as exc:
            print(json.dumps({"status": "unavailable", "error": str(exc)}, ensure_ascii=False))
            raise SystemExit(2)
        computed = kit.indicators.compute_all(df)
        print(json.dumps({"data_kind": "SYNTHETIC_DEMO" if args.demo else "PROVIDER_DATA", "meta": df.attrs,
                          "last_rows": json.loads(computed[["date", "close", "rsi_14", "ma_20"]].tail(3).to_json(orient="records", date_format="iso"))}, ensure_ascii=False, indent=2))
        if args.demo:
            import news_data_kit as ndk
            from news_data_kit.store.engine import NewsStore
            ndk.init(data_root=Path(runtime) / "news")
            cfg = ndk.get_config()
            cfg.ensure_dirs()
            store = NewsStore(cfg.db_path, cfg.articles_dir)
            try:
                store.save(ndk.NewsItem(item_id="synthetic-demo", source_type="demo", source_name="Synthetic",
                                       title="SYNTHETIC DEMO: sample company update", url="https://example.com/demo",
                                       markets=["US"], metadata={"simulated": True}))
            finally:
                store.close()
            print(json.dumps({"news_kind": "SYNTHETIC_DEMO", "query_count": len(ndk.search("sample"))}))


if __name__ == "__main__":
    main()
