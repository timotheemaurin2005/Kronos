import os
import sys
import time
import argparse
import datetime
import dotenv
import torch
import yfinance as yf
import pandas as pd
import numpy as np

# Import Kronos architecture
sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
except ImportError:
    print("❌ Error: alpaca-py is not installed. Run: ./venv/bin/pip install alpaca-py")
    sys.exit(1)

# Load environment variables from .env file if present
dotenv.load_dotenv()

def init_alpaca_client():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key or "your_api_key" in api_key:
        print("\n" + "="*70)
        print("⚠️  ALPACA API CREDENTIALS NOT CONFIGURED (RUNNING IN DRY-RUN MODE)")
        print("To connect your bot for automated paper trading & TradingView charting:")
        print("1. Sign up for a free developer account at https://alpaca.markets")
        print("2. Once inside your dashboard, switch to 'Paper Trading'.")
        print("3. Look at the right sidebar for 'API Keys' and click 'Generate New Key'.")
        print("4. Copy `.env.example` to a new file named `.env` in this directory:")
        print("   cp .env.example .env")
        print("5. Paste your Alpaca API Key ID and Secret Key into `.env`.")
        print("="*70 + "\n")
        return None
    
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        account = client.get_account()
        print(f"✅ Connected to Alpaca Paper Brokerage | Status: {account.status} | Buying Power: ${float(account.buying_power):,.2f}")
        return client
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca Trading API: {e}")
        return None

def load_kronos_predictor():
    device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"🧠 Loading Kronos AI Model (hardware acceleration: {device.upper()})...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
    print("🚀 Kronos AI Engine online & ready!")
    return predictor

def get_signal_from_prediction(pred_df, y_timestamp, current_price):
    prediction_data = [row for _, row in pred_df.iterrows()]
    if len(prediction_data) <= 1:
        return None
    
    # Search for profit potential in forecasted candles
    min_price_idx = 0
    max_profit_long = -float('inf')
    sell_price_long = current_price
    buy_price_long = current_price
    
    for i in range(1, len(prediction_data)):
        if prediction_data[i]['close'] < prediction_data[min_price_idx]['close']:
            min_price_idx = i
        profit = prediction_data[i]['close'] - prediction_data[min_price_idx]['close']
        if profit > max_profit_long and i > min_price_idx:
            max_profit_long = profit
            buy_price_long = prediction_data[min_price_idx]['close']
            sell_price_long = prediction_data[i]['close']

    # Establish robust defensive Stop-Loss and aggressive Take-Profit brackets
    min_low = pred_df['low'].min() * 0.99
    stop_loss = min(min_low, current_price * 0.985)  # At least 1.5% stop loss boundary
    take_profit = max(sell_price_long, current_price * 1.02)  # At least 2% target upside
    
    # Trigger buy signal if predicted upside > 0.5% over current price
    if (sell_price_long - current_price) / current_price > 0.005:
        return {
            "action": "LONG",
            "take_profit": round(float(take_profit), 2),
            "stop_loss": round(float(stop_loss), 2),
            "predicted_target": round(float(sell_price_long), 2)
        }
    return None

def evaluate_and_trade(client, predictor, watchlist, trade_amount_usd=1000):
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Scanning Watchlist: {', '.join(watchlist)}")
    
    # Check open positions to avoid redundant double entries
    open_symbols = set()
    if client:
        try:
            positions = client.get_all_positions()
            for p in positions:
                open_symbols.add(p.symbol)
                print(f"📊 Current Active Position in {p.symbol}: Qty {p.qty} | Unrealized P&L: ${float(p.unrealized_pl):+.2f}")
        except Exception as e:
            print(f"⚠️ Could not retrieve existing brokerage positions: {e}")

    for ticker in watchlist:
        is_crypto = ("/" in ticker or "-" in ticker or ticker.upper().endswith("USD")) and len(ticker) > 4
        yf_ticker = ticker.replace("/", "-") if is_crypto else ticker
        alpaca_symbol = ticker.replace("-", "/") if is_crypto else ticker
        
        # Check against open symbols (Alpaca sometimes lists BTC positions as BTCUSD or BTC/USD)
        check_symbols = {ticker, yf_ticker, alpaca_symbol, ticker.replace("-", "").replace("/", "")}
        if any(s in open_symbols for s in check_symbols):
            print(f"⏭️  Skipping {ticker} — already holding an active simulated trade.")
            continue

        asset_type = "Crypto 🪙" if is_crypto else "Stock 📈"
        print(f"📈 Analyzing {asset_type} {ticker} via Kronos Neural Net...")
        try:
            stock = yf.Ticker(yf_ticker)
            df = stock.history(period="60d", interval="5m")
            if df.empty or len(df) < 400:
                print(f"   ⚠️ Insufficient 5m candle history for {yf_ticker}, skipping.")
                continue

            df.reset_index(inplace=True)
            for col in ['Datetime', 'Date']:
                if col in df.columns:
                    df.rename(columns={col: 'timestamps'}, inplace=True)
                    break
            df.columns = [c.lower() for c in df.columns]
            df['timestamps'] = pd.to_datetime(df['timestamps'])
            
            # Feed last 400 candles into predictor
            x_df = df.iloc[-400:].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
            x_timestamp = df.iloc[-400:]['timestamps'].reset_index(drop=True)
            x_df['amount'] = x_df['volume'] * x_df[['open', 'high', 'low', 'close']].mean(axis=1)
            
            # Forecast future 120 timestamps
            last_time = x_timestamp.iloc[-1]
            y_timestamp = pd.Series(pd.date_range(start=last_time + datetime.timedelta(minutes=5), periods=120, freq="5min"))
            
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=120,
                T=1.0,
                top_p=0.9,
                sample_count=1,
                verbose=False
            )
            
            current_price = float(x_df['close'].iloc[-1])
            signal = get_signal_from_prediction(pred_df, y_timestamp, current_price)
            
            if not signal:
                print(f"   📉 {ticker}: No confident long breakout predicted. Holding pattern.")
                continue
                
            print(f"   🚨 BUY SIGNAL GENERATED [{ticker}]: Entry ~${current_price:.2f} | Target TP: ${signal['take_profit']} | Defensive SL: ${signal['stop_loss']}")
            
            if not client:
                print(f"   ℹ️ [DRY-RUN LOG] Would have submitted Buy Order for ~${trade_amount_usd} worth of {ticker}.")
                continue

            # Handle decimal quantities for crypto vs integer shares for stocks
            if is_crypto:
                qty = round(trade_amount_usd / current_price, 6)
                tif = TimeInForce.GTC  # Crypto markets trade 24/7; DAY is invalid in Alpaca
                unit_label = "coins/units"
            else:
                qty = max(1, int(trade_amount_usd / current_price))
                tif = TimeInForce.DAY
                unit_label = "share(s)"
            
            print(f"   🛒 Submitting Paper Order to Alpaca: Buy {qty} {unit_label} of {alpaca_symbol}...")
            try:
                # Note: Alpaca Crypto may not support bracket orders on all pairs, so we try bracket first
                order_data = MarketOrderRequest(
                    symbol=alpaca_symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=tif,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=signal['take_profit']),
                    stop_loss=StopLossRequest(stop_price=signal['stop_loss'])
                )
                order = client.submit_order(order_data)
                print(f"   ✅ Bracket Trade Executed! Order ID: {order.id} (Check your TradingView charts!)")
            except Exception as e:
                print(f"   ⚠️ Could not submit bracket structure ({e}). Fallback to standard market buy...")
                try:
                    simple_order = MarketOrderRequest(
                        symbol=alpaca_symbol,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=tif
                    )
                    order = client.submit_order(simple_order)
                    print(f"   ✅ Standard Market Trade Executed! Order ID: {order.id} (Live immediately!)")
                except Exception as e2:
                    print(f"   ❌ Trade submission failed completely: {e2}")

        except Exception as e:
            print(f"   ❌ Exception analyzing {ticker}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Kronos Autonomous Paper Trading Engine")
    parser.add_argument("--watchlist", nargs="+", default=["NOW", "TSLA", "NVDA", "AAPL", "AMZN", "MSFT"], help="List of ticker symbols to evaluate")
    parser.add_argument("--crypto", action="store_true", help="Use default 24/7 weekend cryptocurrency watchlist (BTC, ETH, SOL, DOGE)")
    parser.add_argument("--amount", type=float, default=1000.0, help="Target dollar amount per position")
    parser.add_argument("--interval", type=int, default=5, help="Minutes to wait between evaluation sweeps")
    parser.add_argument("--once", action="store_true", help="Perform one scan across the watchlist and exit immediately")
    args = parser.parse_args()

    watchlist = args.watchlist
    if args.crypto and watchlist == ["NOW", "TSLA", "NVDA", "AAPL", "AMZN", "MSFT"]:
        watchlist = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD"]

    print("======================================================================")
    print("🤖 KRONOS AUTONOMOUS PAPER TRADING ENGINE STARTING...")
    if args.crypto:
        print("🌐 24/7 WEEKEND CRYPTO MODE ENABLED")
    print("======================================================================")
    
    client = init_alpaca_client()
    predictor = load_kronos_predictor()
    
    while True:
        evaluate_and_trade(client, predictor, watchlist, args.amount)
        if args.once:
            print("\n🏁 Single scan mode (--once) concluded. Exiting cleanly.")
            break
            
        print(f"\n⏳ Cycle finished. Sleeping for {args.interval} minutes before next evaluation...")
        time.sleep(args.interval * 60)

if __name__ == "__main__":
    main()
