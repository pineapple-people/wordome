import argparse

import uvicorn

from wordome.support import TraceMode


def main():
    parser = argparse.ArgumentParser(
        description="Wordome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  wordome                 Run the API with live scrape trace output.\n"
            "  wordome --mode demo     Run the demo flow.\n"
            "  python scripts/bootstrap_snowflake.py  Create the configured database, schema, and tables.\n"
            "  wordome --trace         Run the API with live scrape trace output.\n"
            "  wordome --trace buffered  Run the API with buffered scrape trace output.\n"
            "  wordome --help          Show this help message.\n"
        ),
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["demo", "api"],
        default="api",
    )
    parser.add_argument(
        "--trace",
        nargs="?",
        const=TraceMode.LIVE.value,
        choices=[TraceMode.LIVE.value, TraceMode.BUFFERED.value],
        help="Set scrape trace mode. If no value is given, `--trace` defaults to `live`.",
    )
    args = parser.parse_args()
    trace_mode = TraceMode(args.trace) if args.trace else TraceMode.LIVE
    if args.mode == "demo":
        from wordome.demo import run_demo

        run_demo()
    else:
        from wordome.app import create_app

        app = create_app(trace_mode=trace_mode)
        uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
