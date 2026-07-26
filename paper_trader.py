import os
import sys
import time
import json
import argparse
import datetime
import dotenv
import torch
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import re

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
        print(f"✅ Connected to Alpaca Paper Brokerage | Status: {account.status}")
        print(f"💰 Portfolio Equity: ${float(account.equity):,.2f} | Available Buying Power: ${float(account.buying_power):,.2f}")
        return client
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca Trading API: {e}")
        return None

def analyze_macro_and_news(ticker, yf_ticker, is_crypto=False):
    """Fetches real-time breaking news and macroeconomic headlines to evaluate fundamental sentiment."""
    headlines = []
    score = 0

    # 1. Fetch breaking asset news via Yahoo Finance
    try:
        stock = yf.Ticker(yf_ticker)
        news_items = stock.news or []
        for item in news_items[:4]:
            content = item.get('content', {})
            title = content.get('title', item.get('title', ''))
            if title and title not in headlines:
                headlines.append(title)
    except Exception:
        pass

    # 2. Fetch High-Impact Macro Economic Events (ForexFactory)
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=5)
        if r.status_code == 200:
            events = r.json()
            for e in events:
                if e.get('impact') == 'High' and any(kw in e.get('title', '').lower() for kw in ['cpi', 'fed', 'fomc', 'rate', 'gdp', 'payroll', 'inflation', 'treasury', 'yield', 'gold', 'silver', 'bullion']):
                    title = f"Macro Event [{e.get('country')}]: {e.get('title')}"
                    if len(headlines) < 6:
                        headlines.append(title)
    except Exception:
        pass

    if not headlines:
        headlines = ["No major volatile breaking headlines detected today."]

    # Keyword Sentiment Scoring Engine
    bullish_keywords = ["surge", "record", "inflow", "approval", "etf", "bullish", "recovery", "gain", "adopt", "jump", "rally", "growth", "boost", "outperform", "buy", "upward", "soar", "milestone"]
    bearish_keywords = ["hack", "ban", "lawsuit", "sec", "investigat", "outflow", "crash", "plunge", "bearish", "fall", "drop", "inflation", "rate hike", "risk", "sell", "downward", "slump", "concern"]

    text = " ".join(headlines).lower()
    for kw in bullish_keywords:
        if re.search(r'\b' + kw, text):
            score += 15
    for kw in bearish_keywords:
        if re.search(r'\b' + kw, text):
            score -= 20  # Weight downside risks heavily

    score = max(-100, min(100, score))
    verdict = "BULLISH 🟢" if score >= 15 else ("BEARISH 🔴" if score <= -15 else "NEUTRAL 🟡")
    
    return {
        "score": score,
        "verdict": verdict,
        "top_headline": headlines[0] if headlines else "N/A",
        "all_headlines": headlines
    }

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

def monitor_active_positions(client, stop_strategy="tiered", predictor=None):
    """Automated Software Stop-Loss & Trailing Position Monitor (with Approach B Rolling Continuation)."""
    open_symbols = set()
    if not client:
        return open_symbols
        
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🛡️ Running Software Stop-Loss Monitor (Strategy: {stop_strategy.upper()})...")
    state_file = "position_trailing_state.json"
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
        except Exception:
            state = {}
            
    try:
        positions = client.get_all_positions()
        if not positions:
            print("   ℹ️ No active live positions found.")
            return open_symbols
            
        for p in positions:
            symbol = p.symbol
            open_symbols.add(symbol)
            qty = abs(float(p.qty))
            current_price = float(p.current_price)
            avg_entry = float(p.avg_entry_price)
            unrealized_pl_usd = float(p.unrealized_pl)
            gain_pct = ((current_price - avg_entry) / avg_entry) * 100.0 if avg_entry > 0 else 0.0
            
            # Track high-water mark (peak price since entry)
            pos_state = state.get(symbol, {"peak_price": avg_entry, "tier": 0, "tp_price": avg_entry * 1.06})
            peak_price = max(pos_state.get("peak_price", avg_entry), current_price)
            pos_state["peak_price"] = peak_price
            
            # Calculate dynamic software Stop-Loss and Take-Profit boundaries
            sl_price = 0.0
            tp_price = pos_state.get("tp_price", avg_entry * 1.06)
            reason = ""
            
            if stop_strategy.lower() == "static":
                sl_price = avg_entry * 0.985  # Fixed -1.5% stop loss
                tp_price = avg_entry * 1.03   # Fixed +3.0% take profit
                reason = "Static Brackets (-1.5% SL / +3.0% TP)"
                
            elif stop_strategy.lower() == "atr":
                trail_sl = peak_price * 0.98
                sl_price = max(avg_entry * 0.98, trail_sl)
                tp_price = avg_entry * 1.06
                reason = f"ATR Chandelier Trail (Trailing 2.0% behind peak ${peak_price:.2f})"
                
            elif stop_strategy.lower() == "beta":
                if unrealized_pl_usd >= 50.0:
                    buffer_usd = 25.0
                    protected_usd = max(0.0, unrealized_pl_usd - buffer_usd)
                    sl_price = avg_entry + (protected_usd / qty) if qty > 0 else avg_entry * 0.985
                else:
                    sl_price = avg_entry * 0.985
                tp_price = avg_entry * 1.05
                reason = "Beta-Weighted Dollar Trail (Floor Protection)"
                
            else:  # default "tiered" step-up ratchet (Approach B)
                gain_from_peak_pct = ((peak_price - avg_entry) / avg_entry) * 100.0 if avg_entry > 0 else 0.0
                if gain_from_peak_pct >= 5.0:
                    sl_price = peak_price * 0.98  # Tier 3: Trailing 2% behind peak
                    tier_str = "Tier 3 (Trailing 2% behind peak)"
                elif gain_from_peak_pct >= 3.0:
                    sl_price = avg_entry * 1.015  # Tier 2: Lock in +1.5% profit floor
                    tier_str = "Tier 2 (+1.5% Profit Floor locked)"
                elif gain_from_peak_pct >= 1.5:
                    sl_price = avg_entry * 1.002  # Tier 1: Lock in Breakeven + 0.2%
                    tier_str = "Tier 1 (Breakeven+ locked)"
                else:
                    sl_price = avg_entry * 0.985  # Tier 0: Initial -1.5% defensive stop
                    tier_str = "Tier 0 (-1.5% Initial Defensive Stop)"
                reason = f"Tiered Step-Up Ratchet [{tier_str}]"
                
            # Approach B: Kronos Rolling Re-Forecast Continuation (Strictly for Crypto 24/7 markets)
            is_crypto_pos = "/" in symbol or "-" in symbol or symbol.upper().endswith("USD")
            if predictor and stop_strategy.lower() == "tiered" and is_crypto_pos and len(symbol) >= 3:
                try:
                    is_crypto_sym = is_crypto_pos
                    yf_sym = symbol.replace("/", "-") if is_crypto_sym else symbol
                    if yf_sym.endswith("USD") and "-" not in yf_sym and len(yf_sym) > 3:
                        yf_sym = yf_sym[:-3] + "-USD"
                        
                    stock = yf.Ticker(yf_sym)
                    df_sym = stock.history(period="15d", interval="5m")
                    if not df_sym.empty and len(df_sym) >= 400:
                        df_sym.reset_index(inplace=True)
                        for col in ['Datetime', 'Date']:
                            if col in df_sym.columns:
                                df_sym.rename(columns={col: 'timestamps'}, inplace=True)
                                break
                        df_sym.columns = [c.lower() for c in df_sym.columns]
                        df_sym['timestamps'] = pd.to_datetime(df_sym['timestamps'])
                        x_sym = df_sym.iloc[-400:].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
                        x_sym_ts = df_sym.iloc[-400:]['timestamps'].reset_index(drop=True)
                        x_sym['amount'] = x_sym['volume'] * x_sym[['open', 'high', 'low', 'close']].mean(axis=1)
                        y_sym_ts = pd.Series(pd.date_range(start=x_sym_ts.iloc[-1] + datetime.timedelta(minutes=5), periods=120, freq="5min"))
                        
                        re_pred = predictor.predict(df=x_sym, x_timestamp=x_sym_ts, y_timestamp=y_sym_ts, pred_len=120, verbose=False)
                        new_target = float(re_pred['high'].max())
                        
                        if new_target > tp_price and new_target > current_price * 1.02:
                            tp_price = new_target
                            pos_state["tp_price"] = tp_price
                            print(f"   🔮 Approach B Re-Forecast: Strong future upside predicted (${new_target:,.4f})! Rolling target TP extended to ${tp_price:,.4f}.")
                except Exception as ex_re:
                    pass
                    
            pos_state["tp_price"] = tp_price
            state[symbol] = pos_state
                
            print(f"📊 [LIVE POSITION] {symbol}: Qty {p.qty} | Current: ${current_price:,.4f} | Entry: ${avg_entry:,.4f} | P&L: ${unrealized_pl_usd:+.2f} ({gain_pct:+.2f}%)")
            print(f"   🛡️ Stop-Loss Strategy [{reason}]: SL Trigger @ ${sl_price:,.4f} | Target TP @ ${tp_price:,.4f}")
            
            # Check for Stop-Loss or Take-Profit Trigger
            trigger_type = None
            if current_price <= sl_price and sl_price > 0:
                trigger_type = f"STOP-LOSS 🛑 (Price ${current_price:,.4f} <= SL ${sl_price:,.4f})"
            elif current_price >= tp_price and tp_price > 0:
                trigger_type = f"TAKE-PROFIT ✅ (Price ${current_price:,.4f} >= TP ${tp_price:,.4f})"
                
            if trigger_type:
                print(f"   🚨 {trigger_type} TRIGGERED FOR {symbol}!")
                print(f"   🛒 Executing Software Stop: Submitting Market SELL Order to close position...")
                try:
                    client.close_position(symbol_or_asset_id=symbol)
                    print(f"   ✅ Position successfully liquidated via Alpaca SDK close_position!")
                    open_symbols.discard(symbol)
                    if symbol in state:
                        del state[symbol]
                except Exception as e:
                    print(f"   ❌ Could not automatically liquidate position: {e}")
                    
        # Save state to persistence file
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
            
    except Exception as e:
        print(f"⚠️ Error in software stop-loss monitor: {e}")
        
    return open_symbols

def evaluate_and_trade(client, predictor, watchlist, trade_amount_usd=1000, stop_strategy="tiered"):
    # First monitor active positions and enforce software stop-loss
    open_symbols = monitor_active_positions(client, stop_strategy, predictor)
    
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Phase 1: Scanning Watchlist & Quant Conviction Scoring")
    candidate_signals = []
    
    # Real-Time Exchange Clock & Market Open Awareness
    market_is_open = True
    if client:
        try:
            clock = client.get_clock()
            market_is_open = clock.is_open
            if market_is_open:
                print("🟢 [EXCHANGE STATUS] US Equity Markets are LIVE! Automated stock trading engines initialized and actively evaluating order setups.")
            else:
                next_open = clock.next_open
                now_ts = clock.timestamp
                rem_seconds = max(0, (next_open - now_ts).total_seconds())
                rem_h, rem_m = int(rem_seconds // 3600), int((rem_seconds % 3600) // 60)
                next_open_str = next_open.strftime("%a %b %d at %H:%M EST")
                print(f"⏸️  [EXCHANGE STATUS] US Equity Markets are currently CLOSED. Next opening bell: {next_open_str} (in ~{rem_h}h {rem_m}m). Automated stock trading will commence instantly at market open!")
        except Exception:
            market_is_open = True

    for ticker in watchlist:
        is_crypto = ("/" in ticker or "-" in ticker or ticker.upper().endswith("USD")) and len(ticker) > 4
        yf_ticker = ticker.replace("/", "-") if is_crypto else ticker
        alpaca_symbol = ticker.replace("-", "/") if is_crypto else ticker
        
        # Check against open symbols (Alpaca sometimes lists BTC positions as BTCUSD or BTC/USD)
        check_symbols = {ticker, yf_ticker, alpaca_symbol, ticker.replace("-", "").replace("/", "")}
        if any(s in open_symbols for s in check_symbols):
            print(f"⏭️  Skipping {ticker} — already holding an active simulated trade.")
            continue
            
        if not is_crypto and not market_is_open:
            print(f"⏸️  [MARKET CLOSED GUARD] Skipping overnight analysis for Stock 📈 {ticker}. Automated alpha evaluation will run automatically at market open.")
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
            
            # Run Macro & News Sentiment Analysis
            macro = analyze_macro_and_news(ticker, yf_ticker, is_crypto)
            print(f"   📰 Macro & News Sentiment: {macro['verdict']} (Score: {macro['score']:+d}) | Top Story: \"{macro['top_headline']}\"")

            if not signal:
                print(f"   📉 {ticker}: No confident quantitative breakout predicted. Holding pattern.")
                continue
                
            print(f"   🚨 BUY SIGNAL GENERATED [{ticker}]: Entry ~${current_price:.2f} | Target TP: ${signal['take_profit']} | Defensive SL: ${signal['stop_loss']}")
            
            # Gatekeeper Check: Veto trades if Macro & Headline sentiment is heavily toxic or bearish
            if macro['score'] <= -20:
                print(f"   🛑 TRADE VETOED BY MACRO FILTER: Adverse breaking news / macro sentiment ({macro['verdict']}, Score: {macro['score']:+d}) poses high drawdown risk! Aborting entry.")
                continue
            elif macro['score'] >= 20:
                print(f"   🔥 HIGH CONVICTION ALIGNED SETUP: Kronos Quant Signal + Bullish Macro Fundamentals!")
                
            gain_pct = ((signal['take_profit'] - current_price) / current_price) * 100.0 if current_price > 0 else 0.0
            conviction_score = round(gain_pct + (macro['score'] * 0.1), 2)
            
            candidate_signals.append({
                "ticker": ticker,
                "alpaca_symbol": alpaca_symbol,
                "current_price": current_price,
                "signal": signal,
                "macro": macro,
                "is_crypto": is_crypto,
                "conviction_score": conviction_score,
                "gain_pct": gain_pct
            })
            print(f"   🌟 Candidate Logged: Conviction Score {conviction_score} (Target Upside: +{gain_pct:.2f}%)")

        except Exception as e:
            print(f"   ❌ Exception analyzing {ticker}: {e}")

    # Phase 2: Top-N Selective High-Conviction Execution
    if candidate_signals:
        print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🏆 SELECTIVE CONVICTION RANKING LEADERBOARD")
        candidate_signals.sort(key=lambda x: x["conviction_score"], reverse=True)
        for idx_r, c in enumerate(candidate_signals, 1):
            print(f"   #{idx_r} {c['ticker']} | Conviction Score: {c['conviction_score']} | Target Upside: +{c['gain_pct']:.2f}% | Macro: {c['macro']['verdict']}")
            
        min_conviction_threshold = 2.0  # Fund ANY setup that demonstrates sufficient quant + macro conviction
        selected = [c for c in candidate_signals if c["conviction_score"] >= min_conviction_threshold]
        print(f"   🎯 Conviction Cut-off (Score >= {min_conviction_threshold}): Deploying capital into {len(selected)} of {len(candidate_signals)} approved setup(s)!")
        
        for trade in selected:
            t_ticker = trade["ticker"]
            a_sym = trade["alpaca_symbol"]
            c_price = trade["current_price"]
            sig = trade["signal"]
            is_cryp = trade["is_crypto"]
            
            if not client:
                print(f"   ℹ️ [DRY-RUN] Would have submitted BUY order for ~${trade_amount_usd} of {t_ticker}.")
                continue

            if is_cryp:
                qty = round(trade_amount_usd / c_price, 6)
                tif = TimeInForce.GTC
                unit_label = "coins/units"
            else:
                qty = max(1, int(trade_amount_usd / c_price))
                tif = TimeInForce.DAY
                unit_label = "share(s)"
            
            print(f"\n   🛒 Deploying Capital: Buy {qty} {unit_label} of {a_sym}...")
            try:
                order_data = MarketOrderRequest(
                    symbol=a_sym,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=tif,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=sig['take_profit']),
                    stop_loss=StopLossRequest(stop_price=sig['stop_loss'])
                )
                order = client.submit_order(order_data)
                print(f"   ✅ Bracket Trade Executed! Order ID: {order.id} (Check your TradingView charts!)")
            except Exception as e:
                print(f"   ⚠️ Could not submit bracket structure ({e}). Fallback to standard market buy...")
                try:
                    simple_order = MarketOrderRequest(
                        symbol=a_sym,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=tif
                    )
                    order = client.submit_order(simple_order)
                    print(f"   ✅ Standard Market Trade Executed! Order ID: {order.id} (Live immediately!)")
                except Exception as e2:
                    print(f"   ❌ Trade submission failed completely: {e2}")
    else:
        print(f"\n   ℹ️ No actionable alpha setups passed high-conviction screening during this sweep.")

def main():
    parser = argparse.ArgumentParser(description="Kronos Autonomous Paper Trading Engine")
    parser.add_argument("--watchlist", nargs="+", default=["NVDA", "TSLA", "NOW", "PLTR", "AAPL", "MSFT", "META", "AMZN", "AMD", "AVGO", "GLD", "SLV"], help="List of ticker symbols to evaluate")
    parser.add_argument("--crypto", action="store_true", help="Use default 24/7 weekend cryptocurrency watchlist (BTC, ETH, SOL, DOGE)")
    parser.add_argument("--amount", type=float, default=10000.0, help="Target dollar amount per position (default $10,000 for $100k equity)")
    parser.add_argument("--interval", type=int, default=5, help="Minutes to wait between evaluation sweeps")
    parser.add_argument("--once", action="store_true", help="Perform one scan across the watchlist and exit immediately")
    parser.add_argument("--stop-strategy", choices=["tiered", "static", "atr", "beta"], default="tiered", help="Select software stop-loss management algorithm")
    parser.add_argument("--monitor-only", action="store_true", help="Only evaluate live positions against software stop-loss rules without generating new signals")
    args = parser.parse_args()

    watchlist = args.watchlist
    if args.crypto and watchlist == ["NVDA", "TSLA", "NOW", "PLTR", "AAPL", "MSFT", "META", "AMZN", "AMD", "AVGO", "GLD", "SLV"]:
        watchlist = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD"]

    print("======================================================================")
    print("🤖 KRONOS AUTONOMOUS PAPER TRADING ENGINE STARTING...")
    print(f"💵 Configured Position Sizing: ${args.amount:,.2f} per trade")
    print(f"🛡️ Active Stop-Loss Algorithm: {args.stop_strategy.upper()}")
    if args.crypto:
        print("🌐 24/7 WEEKEND CRYPTO MODE ENABLED")
    if args.monitor_only:
        print("🔎 MONITOR-ONLY MODE ENABLED (No new signals will be generated)")
    print("======================================================================")
    
    client = init_alpaca_client()
    predictor = None if args.monitor_only else load_kronos_predictor()
    
    while True:
        if args.monitor_only:
            monitor_active_positions(client, stop_strategy=args.stop_strategy, predictor=predictor)
        else:
            evaluate_and_trade(client, predictor, watchlist, args.amount, stop_strategy=args.stop_strategy)
            
        if args.once or args.monitor_only:
            print("\n🏁 Execution scan concluded. Exiting cleanly.")
            break
            
        print(f"\n⏳ Cycle finished. Sleeping for {args.interval} minutes before next evaluation...")
        time.sleep(args.interval * 60)

if __name__ == "__main__":
    main()
