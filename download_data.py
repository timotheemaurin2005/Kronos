import yfinance as yf
import pandas as pd
import sys

if len(sys.argv) < 2:
    print("Usage: python download_data.py <TICKER>")
    sys.exit(1)

ticker = sys.argv[1].upper()

# Download 5-minute data for the last 60 days
print(f"Downloading {ticker} data...")
stock = yf.Ticker(ticker)
hist = stock.history(period="60d", interval="5m")

if hist.empty:
    print(f"No data found for {ticker}")
    sys.exit(1)

# Format columns to match Kronos expectations
hist = hist.reset_index()
hist = hist.rename(columns={
    "Datetime": "timestamps",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume"
})
# amount is optional, we'll just set it to 0
hist['amount'] = 0

output_file = f"{ticker.lower()}_data.csv"
# Save to CSV
hist[['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']].to_csv(output_file, index=False)
print(f"Saved {len(hist)} rows to {output_file}")
