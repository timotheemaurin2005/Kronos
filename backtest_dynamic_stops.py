import yfinance as yf
import pandas as pd
import numpy as np
import random
import sys
import os
import datetime
import torch

sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

def compute_atr(df, period=14):
    """Computes Average True Range (ATR) over high, low, close."""
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    return float(atr.iloc[-1])

def evaluate_strategies_on_trade(ticker, trade_type, entry_time, exit_time, entry_price, initial_tp, initial_sl, actual_y, atr_value, asset_beta, portfolio_size=10000.0, log_file=None):
    shares = portfolio_size / entry_price
    
    # 4 Strategy States
    # Strategy 1: Static Baseline
    st1 = {"name": "1. Static Brackets", "sl": initial_sl, "tp": initial_tp, "status": "ACTIVE", "pnl": 0.0, "outcome": "", "logs": []}
    
    # Strategy 2: ATR Trailing Stop (2x ATR Chandelier Exit)
    atr_gap = 2.0 * atr_value
    st2 = {"name": "2. ATR Chandelier Trail", "sl": entry_price - atr_gap if trade_type=="LONG" else entry_price + atr_gap, "tp": initial_tp, "status": "ACTIVE", "pnl": 0.0, "outcome": "", "logs": []}
    
    # Strategy 3: Beta-Adjusted Dollar Buffer
    st3 = {"name": "3. Beta-Weighted Dollar Trail", "sl": initial_sl, "tp": initial_tp, "status": "ACTIVE", "pnl": 0.0, "outcome": "", "high_water_usd": 0.0, "logs": []}
    
    # Strategy 4: Step-Up Milestone Ratchet
    st4 = {"name": "4. Tiered Step-Up Ratchet", "sl": initial_sl, "tp": initial_tp, "status": "ACTIVE", "pnl": 0.0, "outcome": "", "tier": 0, "logs": []}

    strategies = [st1, st2, st3, st4]
    
    trade_active = False
    high_water_mark = entry_price
    low_water_mark = entry_price
    
    for i, row in actual_y.iterrows():
        t = row['timestamps']
        
        if not trade_active and t >= entry_time:
            trade_active = True
            for st in strategies:
                st["logs"].append(f"[{t}] Trade Entered @ ${row['open']:.4f}")
        
        if trade_active:
            high = row['high']
            low = row['low']
            close = row['close']
            
            # Track peaks for trailing calculations
            high_water_mark = max(high_water_mark, high)
            low_water_mark = min(low_water_mark, low)
            
            for st in strategies:
                if st["status"] != "ACTIVE":
                    continue
                
                # Dynamic adjustment check before checking hits
                if st["name"] == "2. ATR Chandelier Trail":
                    if trade_type == "LONG":
                        potential_sl = high_water_mark - (1.5 * atr_value)
                        if potential_sl > st["sl"]:
                            st["sl"] = potential_sl
                            st["logs"].append(f"[{t}] 📈 ATR Trail adjusted Stop-Loss UP to ${st['sl']:.4f}")
                    else:
                        potential_sl = low_water_mark + (1.5 * atr_value)
                        if potential_sl < st["sl"]:
                            st["sl"] = potential_sl
                            st["logs"].append(f"[{t}] 📉 ATR Trail adjusted Stop-Loss DOWN to ${st['sl']:.4f}")

                elif st["name"] == "3. Beta-Weighted Dollar Trail":
                    # Unrealized USD profit at current peak
                    unrealized_peak = shares * (high_water_mark - entry_price) if trade_type=="LONG" else shares * (entry_price - low_water_mark)
                    if unrealized_peak >= 100.0: # Trigger threshold
                        # Subtract beta-scaled dollar buffer (e.g. $50 * Beta)
                        buffer_usd = 40.0 * asset_beta
                        locked_usd = max(0.0, unrealized_peak - buffer_usd)
                        if locked_usd > st["high_water_usd"]:
                            st["high_water_usd"] = locked_usd
                            if trade_type == "LONG":
                                st["sl"] = entry_price + (locked_usd / shares)
                            else:
                                st["sl"] = entry_price - (locked_usd / shares)
                            st["logs"].append(f"[{t}] 🛡️ Beta-Weighted Stop adjusted to lock in +${locked_usd:.2f} (SL: ${st['sl']:.4f})")

                elif st["name"] == "4. Tiered Step-Up Ratchet":
                    gain_pct = ((high_water_mark - entry_price)/entry_price)*100 if trade_type=="LONG" else ((entry_price - low_water_mark)/entry_price)*100
                    if st["tier"] == 0 and gain_pct >= 1.5:
                        st["tier"] = 1
                        st["sl"] = entry_price * 1.002 if trade_type=="LONG" else entry_price * 0.998
                        st["logs"].append(f"[{t}] 🔒 Tier 1 Reached (+1.5%): Stop moved to Breakeven+ (${st['sl']:.4f})")
                    elif st["tier"] == 1 and gain_pct >= 3.0:
                        st["tier"] = 2
                        st["sl"] = entry_price * 1.015 if trade_type=="LONG" else entry_price * 0.985
                        st["logs"].append(f"[{t}] 🔒 Tier 2 Reached (+3.0%): Stop moved to +1.5% profit floor (${st['sl']:.4f})")
                    elif st["tier"] == 2 and gain_pct >= 5.0:
                        trail_sl = high_water_mark * 0.98 if trade_type=="LONG" else low_water_mark * 1.02
                        if (trade_type=="LONG" and trail_sl > st["sl"]) or (trade_type=="SHORT" and trail_sl < st["sl"]):
                            st["sl"] = trail_sl
                            st["logs"].append(f"[{t}] 🚀 Tier 3 Trailing Reached: Stop following peak (${st['sl']:.4f})")

                # Check SL / TP Triggers
                if trade_type == "LONG":
                    if low <= st["sl"]:
                        st["status"] = "CLOSED"
                        st["outcome"] = "SL HIT"
                        st["pnl"] = float(shares * (st["sl"] - entry_price))
                        st["logs"].append(f"[{t}] 🛑 STOP-LOSS triggered @ ${st['sl']:.4f} (P&L: ${st['pnl']:.2f})")
                    elif high >= st["tp"]:
                        st["status"] = "CLOSED"
                        st["outcome"] = "TP HIT"
                        st["pnl"] = float(shares * (st["tp"] - entry_price))
                        st["logs"].append(f"[{t}] ✅ TAKE-PROFIT triggered @ ${st['tp']:.4f} (P&L: ${st['pnl']:.2f})")
                else: # SHORT
                    if high >= st["sl"]:
                        st["status"] = "CLOSED"
                        st["outcome"] = "SL HIT"
                        st["pnl"] = float(shares * (entry_price - st["sl"]))
                        st["logs"].append(f"[{t}] 🛑 STOP-LOSS triggered @ ${st['sl']:.4f} (P&L: ${st['pnl']:.2f})")
                    elif low <= st["tp"]:
                        st["status"] = "CLOSED"
                        st["outcome"] = "TP HIT"
                        st["pnl"] = float(shares * (entry_price - st["tp"]))
                        st["logs"].append(f"[{t}] ✅ TAKE-PROFIT triggered @ ${st['tp']:.4f} (P&L: ${st['pnl']:.2f})")
                
                if st["status"] == "ACTIVE" and t >= exit_time:
                    st["status"] = "CLOSED"
                    st["outcome"] = "TIME EXIT"
                    st["pnl"] = float(shares * (close - entry_price) if trade_type=="LONG" else shares * (entry_price - close))
                    st["logs"].append(f"[{t}] ⏱️ TIMEOUT reached. Exit @ ${close:.4f} (P&L: ${st['pnl']:.2f})")
                    
    # Write details to log file
    if log_file:
        with open(log_file, "a") as f:
            f.write(f"\n========================================================================\n")
            f.write(f"🪙 ASSET: {ticker} | SIGNAL: {trade_type} | ENTRY PRICE: ${entry_price:.4f} | ATR: ${atr_value:.4f} | BETA: {asset_beta}\n")
            f.write(f"========================================================================\n")
            for st in strategies:
                f.write(f"--- Strategy: {st['name']} (Outcome: {st['outcome']} | P&L: ${st['pnl']:.2f}) ---\n")
                for entry in st["logs"]:
                    f.write(f"   {entry}\n")
            f.write(f"------------------------------------------------------------------------\n")

    return {st["name"]: {"pnl": st["pnl"], "win": st["pnl"] > 0, "outcome": st["outcome"]} for st in strategies}

def run_comparative_backtest():
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"]
    betas = {"BTC-USD": 1.0, "ETH-USD": 1.25, "SOL-USD": 1.8, "DOGE-USD": 2.2}
    
    log_file = "/Users/timotheemaurin/Kronos/backtest_dynamic_timeline.log"
    if os.path.exists(log_file):
        os.remove(log_file)
        
    print("======================================================================")
    print("🔬 KRONOS MULTI-OPTION DYNAMIC STOP-LOSS COMPARATIVE BACKTESTER")
    print(f"📄 Full Trade Timeline Log File: {log_file}")
    print("======================================================================")
    
    device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
    
    strategy_totals = {
        "1. Static Brackets": {"pnl": 0.0, "wins": 0, "trades": 0},
        "2. ATR Chandelier Trail": {"pnl": 0.0, "wins": 0, "trades": 0},
        "3. Beta-Weighted Dollar Trail": {"pnl": 0.0, "wins": 0, "trades": 0},
        "4. Tiered Step-Up Ratchet": {"pnl": 0.0, "wins": 0, "trades": 0}
    }
    
    for ticker in tickers:
        print(f"\nLoading 5-minute historical candle data for {ticker}...")
        stock = yf.Ticker(ticker)
        df = stock.history(period="60d", interval="5m")
        if df.empty or len(df) < 600:
            print(f"Skipping {ticker}, insufficient historical data.")
            continue
            
        df.reset_index(inplace=True)
        for col in ['Datetime', 'Date']:
            if col in df.columns:
                df.rename(columns={col: 'timestamps'}, inplace=True)
                break
        df.columns = [c.lower() for c in df.columns]
        df['timestamps'] = pd.to_datetime(df['timestamps'])
        
        # Select 5 random valid historical evaluation windows
        max_idx = len(df) - 120
        min_idx = 400
        test_indices = sorted(random.sample(range(min_idx, max_idx), 5))
        
        for count, idx in enumerate(test_indices, 1):
            x_df = df.iloc[idx-400:idx].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
            x_timestamp = df.iloc[idx-400:idx]['timestamps'].reset_index(drop=True)
            x_df['amount'] = x_df['volume'] * x_df[['open', 'high', 'low', 'close']].mean(axis=1)
            actual_y = df.iloc[idx:idx+120].reset_index(drop=True)
            y_timestamp = actual_y['timestamps']
            
            atr_val = compute_atr(x_df, period=14)
            beta_val = betas.get(ticker, 1.5)
            
            pred_df = predictor.predict(df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp, pred_len=120, verbose=False)
            
            last_x_price = float(x_df['close'].iloc[-1])
            pred_close = pred_df['close']
            pred_high = pred_df['high'].max()
            pred_low = pred_df['low'].min()
            
            up_potential = (pred_high - last_x_price) / last_x_price
            down_potential = (last_x_price - pred_low) / last_x_price
            
            trade_type = None
            if up_potential > 0.015 and up_potential > 1.5 * down_potential:
                trade_type = "LONG"
                take_profit = pred_high
                stop_loss = min(last_x_price * 0.99, pred_low)
            elif down_potential > 0.015 and down_potential > 1.5 * up_potential:
                trade_type = "SHORT"
                take_profit = pred_low
                stop_loss = max(last_x_price * 1.01, pred_high)
            else:
                continue
                
            entry_time = y_timestamp.iloc[0]
            exit_time = y_timestamp.iloc[-1]
            entry_price = float(actual_y['open'].iloc[0])
            
            res = evaluate_strategies_on_trade(ticker, trade_type, entry_time, exit_time, entry_price, take_profit, stop_loss, actual_y, atr_val, beta_val, portfolio_size=10000.0, log_file=log_file)
            
            for st_name, metrics in res.items():
                strategy_totals[st_name]["trades"] += 1
                strategy_totals[st_name]["pnl"] += metrics["pnl"]
                if metrics["win"]:
                    strategy_totals[st_name]["wins"] += 1
                    
    print("\n" + "="*75)
    print("🏆 COMPARATIVE DYNAMIC STOP-LOSS STRATEGY PERFORMANCE SUMMARY 🏆")
    print("="*75)
    print(f"{'Strategy Name':<30} | {'Win Rate':<10} | {'Total P&L ($)':<15} | {'Avg P&L / Trade':<15}")
    print("-" * 75)
    for st_name, stats in strategy_totals.items():
        trades = stats["trades"]
        win_rate = (stats["wins"] / trades) * 100 if trades > 0 else 0.0
        tot_pnl = stats["pnl"]
        avg_pnl = tot_pnl / trades if trades > 0 else 0.0
        print(f"{st_name:<30} | {win_rate:>5.1f}%     | ${tot_pnl:>12.2f}  | ${avg_pnl:>12.2f}")
    print("="*75)
    print(f"✅ Detailed timestamp timeline written to: {log_file}")

if __name__ == "__main__":
    run_comparative_backtest()
