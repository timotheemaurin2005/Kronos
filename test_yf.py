import yfinance as yf
ticker = yf.Ticker("MSFT")
info = ticker.info
print("FCF:", info.get("freeCashflow"))
print("Operating Cashflow:", info.get("operatingCashflow"))
print("Total Debt:", info.get("totalDebt"))
print("Cash:", info.get("totalCash"))
print("Shares:", info.get("sharesOutstanding"))
print("Revenue Growth:", info.get("revenueGrowth"))
print("Current Price:", info.get("currentPrice"))
