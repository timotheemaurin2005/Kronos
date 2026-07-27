"""
Standalone logger that periodically records the live macro/news sentiment score
computed by paper_trader.py's analyze_macro_and_news() to a timestamped CSV.

Why this exists: analyze_macro_and_news() only ever reflects "right now" (live
Yahoo Finance headlines + this week's ForexFactory calendar, no historical
lookup). That makes the news veto in paper_trader.py structurally impossible to
backtest point-in-time -- there is no historical archive to replay. This script
starts building that archive today so a future backtest can actually evaluate
the veto against real, dated headline scores instead of excluding it.

Usage:
    python macro_score_logger.py                 # loop forever, 5-min cadence
    python macro_score_logger.py --once           # single sweep, then exit
    python macro_score_logger.py --interval 10    # custom cadence (minutes)

No Alpaca credentials are required -- this only calls analyze_macro_and_news(),
never the trading client.
"""

import argparse
import csv
import datetime
import os
import sys
import time

sys.path.append("./")
from paper_trader import analyze_macro_and_news

LOG_FILE = "macro_score_history.csv"

# (ticker, yf_ticker, is_crypto) -- mirrors paper_trader.py's default watchlists
WATCHLIST = [
    ("NVDA", "NVDA", False), ("TSLA", "TSLA", False), ("NOW", "NOW", False),
    ("PLTR", "PLTR", False), ("AAPL", "AAPL", False), ("MSFT", "MSFT", False),
    ("META", "META", False), ("AMZN", "AMZN", False), ("AMD", "AMD", False),
    ("AVGO", "AVGO", False), ("GLD", "GLD", False), ("SLV", "SLV", False),
    ("BTC/USD", "BTC-USD", True), ("ETH/USD", "ETH-USD", True),
    ("SOL/USD", "SOL-USD", True), ("DOGE/USD", "DOGE-USD", True),
]


def ensure_header(path):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp_utc", "ticker", "score", "verdict", "top_headline"])


def run_sweep(log_path):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows = []
    for ticker, yf_ticker, is_crypto in WATCHLIST:
        try:
            result = analyze_macro_and_news(ticker, yf_ticker, is_crypto)
            rows.append([now, ticker, result["score"], result["verdict"], result["top_headline"]])
        except Exception as e:
            rows.append([now, ticker, "", f"ERROR: {e}", ""])
    with open(log_path, "a", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"[{now}] Logged macro scores for {len(rows)} tickers -> {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Log live macro/news sentiment scores to a timestamped CSV archive")
    parser.add_argument("--once", action="store_true", help="Run a single sweep then exit")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between sweeps (default: 5, matching paper_trader.py)")
    parser.add_argument("--log-file", type=str, default=LOG_FILE, help="Path to the CSV archive")
    args = parser.parse_args()

    ensure_header(args.log_file)

    while True:
        run_sweep(args.log_file)
        if args.once:
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
