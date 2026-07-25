import yfinance as yf
import pandas as pd

# Download MSFT 5-minute data for the last 60 days
print("Downloading MSFT data...")
msft = yf.Ticker("MSFT")
hist = msft.history(period="60d", interval="5m")

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

# Save to CSV
hist[['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']].to_csv('msft_data.csv', index=False)
print(f"Saved {len(hist)} rows to msft_data.csv")
