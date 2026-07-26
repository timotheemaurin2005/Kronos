import os
import sys
import time
import random
import datetime
import torch
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

def compute_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return float(tr.rolling(window=period, min_periods=1).mean().iloc[-1])

def evaluate_tiered_stop_step(row, trade_type, entry_price, high_water_mark, low_water_mark, sl_price, tier, t, logs, prefix=""):
    high = row['high']
    low = row['low']
    close = row['close']
    
    high_water_mark = max(high_water_mark, high)
    low_water_mark = min(low_water_mark, low)
    
    gain_pct = ((high_water_mark - entry_price) / entry_price) * 100 if trade_type == "LONG" else ((entry_price - low_water_mark) / entry_price) * 100
    
    if tier == 0 and gain_pct >= 1.5:
        tier = 1
        sl_price = entry_price * 1.002 if trade_type == "LONG" else entry_price * 0.998
        logs.append(f"[{t}] {prefix}🔒 Tier 1 (+1.5% Peak): Stop ratcheted to Breakeven+ (${sl_price:.4f})")
    elif tier == 1 and gain_pct >= 3.0:
        tier = 2
        sl_price = entry_price * 1.015 if trade_type == "LONG" else entry_price * 0.985
        logs.append(f"[{t}] {prefix}🔒 Tier 2 (+3.0% Peak): Stop ratcheted to +1.5% Floor (${sl_price:.4f})")
    elif tier == 2 and gain_pct >= 5.0:
        tier = 3
        logs.append(f"[{t}] {prefix}🚀 Tier 3 (+5.0% Peak): Activated 2.0% Trailing Stop behind peak")
        
    if tier >= 2 and gain_pct >= 5.0:
        trail_sl = high_water_mark * 0.98 if trade_type == "LONG" else low_water_mark * 1.02
        if (trade_type == "LONG" and trail_sl > sl_price) or (trade_type == "SHORT" and trail_sl < sl_price):
            sl_price = trail_sl
            
    return high_water_mark, low_water_mark, sl_price, tier

def run_rolling_forecast_comparison():
    tickers = ["NOW", "TSLA", "NVDA", "AAPL", "AMZN", "MSFT", "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"]
    log_file = "/Users/timotheemaurin/Kronos/backtest_rolling_timeline.log"
    if os.path.exists(log_file):
        os.remove(log_file)
        
    print("=========================================================================================")
    print("🚀 KRONOS ROLLING MULTI-WINDOW CONTINUATION vs. HARD TIME EXIT BACKTESTER")
    print(f"📄 Detailed Rolling Timeline Log File: {log_file}")
    print("=========================================================================================")
    
    device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
    
    totals = {
        "A. Hard Time Exit (1 Window / 10h)": {"pnl": 0.0, "wins": 0, "trades": 0},
        "B. Rolling Forecast Continuation": {"pnl": 0.0, "wins": 0, "trades": 0}
    }
    
    portfolio_size = 10000.0
    
    for ticker in tickers:
        print(f"\nDownloading historical 5-minute candle history for {ticker}...")
        stock = yf.Ticker(ticker)
        df = stock.history(period="60d", interval="5m")
        if df.empty or len(df) < 1000:
            print(f"Skipping {ticker}, insufficient historical records.")
            continue
            
        df.reset_index(inplace=True)
        for col in ['Datetime', 'Date']:
            if col in df.columns:
                df.rename(columns={col: 'timestamps'}, inplace=True)
                break
        df.columns = [c.lower() for c in df.columns]
        df['timestamps'] = pd.to_datetime(df['timestamps'])
        
        # We need enough future runway for up to 4 sequential rolling windows (480 candles = 40 hours)
        max_idx = len(df) - 500
        min_idx = 400
        test_indices = sorted(random.sample(range(min_idx, max_idx), 4))
        
        for idx in test_indices:
            # Initial prediction window setup
            x_df = df.iloc[idx-400:idx].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
            x_timestamp = df.iloc[idx-400:idx]['timestamps'].reset_index(drop=True)
            x_df['amount'] = x_df['volume'] * x_df[['open', 'high', 'low', 'close']].mean(axis=1)
            
            y_window1 = df.iloc[idx:idx+120].reset_index(drop=True)
            
            pred_df = predictor.predict(df=x_df, x_timestamp=x_timestamp, y_timestamp=y_window1['timestamps'], pred_len=120, verbose=False)
            last_close = float(x_df['close'].iloc[-1])
            pred_high = pred_df['high'].max()
            pred_low = pred_df['low'].min()
            
            up_potential = (pred_high - last_close) / last_close
            down_potential = (last_close - pred_low) / last_close
            
            # Identify valid trade opportunity
            trade_type = None
            if up_potential > 0.012 and up_potential > 1.4 * down_potential:
                trade_type = "LONG"
                initial_tp = pred_high
                initial_sl = min(last_close * 0.985, pred_low)
            elif down_potential > 0.012 and down_potential > 1.4 * up_potential:
                trade_type = "SHORT"
                initial_tp = pred_low
                initial_sl = max(last_close * 1.015, pred_high)
            else:
                continue
                
            entry_price = float(y_window1['open'].iloc[0])
            shares = portfolio_size / entry_price
            entry_time = y_window1['timestamps'].iloc[0]
            
            # =========================================================================
            # STRATEGY A: Standard Single-Window with Hard Time Exit @ Candle 120
            # =========================================================================
            sl_A = initial_sl
            tp_A = initial_tp
            hwm_A = entry_price
            lwm_A = entry_price
            tier_A = 0
            status_A = "ACTIVE"
            pnl_A = 0.0
            outcome_A = ""
            logs_A = [f"[{entry_time}] Trade Entered @ ${entry_price:.4f} ({trade_type}) | Initial SL: ${sl_A:.4f}"]
            
            for i, row in y_window1.iterrows():
                t = row['timestamps']
                high, low, close = row['high'], row['low'], row['close']
                hwm_A, lwm_A, sl_A, tier_A = evaluate_tiered_stop_step(row, trade_type, entry_price, hwm_A, lwm_A, sl_A, tier_A, t, logs_A)
                
                if trade_type == "LONG":
                    if low <= sl_A:
                        status_A, outcome_A, pnl_A = "CLOSED", "SL HIT", float(shares * (sl_A - entry_price))
                        logs_A.append(f"[{t}] 🛑 STOP-LOSS hit @ ${sl_A:.4f} (P&L: ${pnl_A:+.2f})")
                        break
                    elif high >= tp_A:
                        status_A, outcome_A, pnl_A = "CLOSED", "TP HIT", float(shares * (tp_A - entry_price))
                        logs_A.append(f"[{t}] ✅ TAKE-PROFIT hit @ ${tp_A:.4f} (P&L: ${pnl_A:+.2f})")
                        break
                else:
                    if high >= sl_A:
                        status_A, outcome_A, pnl_A = "CLOSED", "SL HIT", float(shares * (entry_price - sl_A))
                        logs_A.append(f"[{t}] 🛑 STOP-LOSS hit @ ${sl_A:.4f} (P&L: ${pnl_A:+.2f})")
                        break
                    elif low <= tp_A:
                        status_A, outcome_A, pnl_A = "CLOSED", "TP HIT", float(shares * (entry_price - tp_A))
                        logs_A.append(f"[{t}] ✅ TAKE-PROFIT hit @ ${tp_A:.4f} (P&L: ${pnl_A:+.2f})")
                        break
                        
            if status_A == "ACTIVE":
                final_close = float(y_window1['close'].iloc[-1])
                outcome_A = "HARD TIME EXIT"
                pnl_A = float(shares * (final_close - entry_price) if trade_type=="LONG" else shares * (entry_price - final_close))
                logs_A.append(f"[{y_window1['timestamps'].iloc[-1]}] ⏱️ MANDATORY TIME EXIT @ ${final_close:.4f} (P&L: ${pnl_A:+.2f})")
                
            totals["A. Hard Time Exit (1 Window / 10h)"]["trades"] += 1
            totals["A. Hard Time Exit (1 Window / 10h)"]["pnl"] += pnl_A
            if pnl_A > 0: totals["A. Hard Time Exit (1 Window / 10h)"]["wins"] += 1
            
            # =========================================================================
            # STRATEGY B: Rolling Forecast Continuation with Persisted Tiered Stop
            # =========================================================================
            sl_B = initial_sl
            tp_B = initial_tp
            hwm_B = entry_price
            lwm_B = entry_price
            tier_B = 0
            status_B = "ACTIVE"
            pnl_B = 0.0
            outcome_B = ""
            logs_B = [f"[{entry_time}] Trade Entered @ ${entry_price:.4f} ({trade_type}) | Initial SL: ${sl_B:.4f}"]
            
            # Evaluate across up to 4 consecutive rolling windows (up to 480 candles)
            current_idx = idx
            for window_num in range(1, 5):
                if status_B != "ACTIVE":
                    break
                    
                curr_window = df.iloc[current_idx:current_idx+120].reset_index(drop=True)
                if len(curr_window) < 10:
                    break
                    
                for i, row in curr_window.iterrows():
                    t = row['timestamps']
                    high, low, close = row['high'], row['low'], row['close']
                    hwm_B, lwm_B, sl_B, tier_B = evaluate_tiered_stop_step(row, trade_type, entry_price, hwm_B, lwm_B, sl_B, tier_B, t, logs_B, prefix=f"[W{window_num}] ")
                    
                    if trade_type == "LONG":
                        if low <= sl_B:
                            status_B, outcome_B, pnl_B = "CLOSED", f"SL HIT (Window {window_num})", float(shares * (sl_B - entry_price))
                            logs_B.append(f"[{t}] 🛑 [Window {window_num}] STOP-LOSS triggered @ ${sl_B:.4f} (P&L: ${pnl_B:+.2f})")
                            break
                        elif high >= tp_B:
                            status_B, outcome_B, pnl_B = "CLOSED", f"TP HIT (Window {window_num})", float(shares * (tp_B - entry_price))
                            logs_B.append(f"[{t}] ✅ [Window {window_num}] TAKE-PROFIT triggered @ ${tp_B:.4f} (P&L: ${pnl_B:+.2f})")
                            break
                    else:
                        if high >= sl_B:
                            status_B, outcome_B, pnl_B = "CLOSED", f"SL HIT (Window {window_num})", float(shares * (entry_price - sl_B))
                            logs_B.append(f"[{t}] 🛑 [Window {window_num}] STOP-LOSS triggered @ ${sl_B:.4f} (P&L: ${pnl_B:+.2f})")
                            break
                        elif low <= tp_B:
                            status_B, outcome_B, pnl_B = "CLOSED", f"TP HIT (Window {window_num})", float(shares * (entry_price - tp_B))
                            logs_B.append(f"[{t}] ✅ [Window {window_num}] TAKE-PROFIT triggered @ ${tp_B:.4f} (P&L: ${pnl_B:+.2f})")
                            break
                            
                # If still active at end of window, re-run Kronos forecast instead of forcing hard exit!
                if status_B == "ACTIVE":
                    end_time = curr_window['timestamps'].iloc[-1]
                    end_close = float(curr_window['close'].iloc[-1])
                    if window_num == 4:
                        # Max evaluation horizon reached
                        outcome_B = "MAX HORIZON EXIT (40h)"
                        pnl_B = float(shares * (end_close - entry_price) if trade_type=="LONG" else shares * (entry_price - end_close))
                        logs_B.append(f"[{end_time}] 🏁 Reached max 40-hour backtest horizon. Exit @ ${end_close:.4f} (P&L: ${pnl_B:+.2f})")
                        status_B = "CLOSED"
                    else:
                        # Advance index and re-predict future market momentum
                        current_idx += 120
                        next_x = df.iloc[current_idx-400:current_idx].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
                        next_x['amount'] = next_x['volume'] * next_x[['open', 'high', 'low', 'close']].mean(axis=1)
                        next_y = df.iloc[current_idx:current_idx+120]
                        if len(next_y) == 120:
                            re_pred = predictor.predict(df=next_x, x_timestamp=df.iloc[current_idx-400:current_idx]['timestamps'], y_timestamp=next_y['timestamps'], pred_len=120, verbose=False)
                            new_high = re_pred['high'].max()
                            new_low = re_pred['low'].min()
                            
                            # Update target take profit upwards if forecast expands!
                            if trade_type == "LONG" and new_high > tp_B:
                                tp_B = new_high
                                logs_B.append(f"[{end_time}] 🔮 Re-Forecast: Strong upside continued! TP extended to ${tp_B:.4f}. Rolling into Window {window_num+1} with secured Tier {tier_B} Stop (${sl_B:.4f}).")
                            elif trade_type == "SHORT" and new_low < tp_B:
                                tp_B = new_low
                                logs_B.append(f"[{end_time}] 🔮 Re-Forecast: Bearish continuation forecasted! TP extended to ${tp_B:.4f}. Rolling into Window {window_num+1} with secured Tier {tier_B} Stop (${sl_B:.4f}).")
                            else:
                                logs_B.append(f"[{end_time}] 🔄 Re-Forecast: Maintaining position into Window {window_num+1}. Protected by Tier {tier_B} Stop (${sl_B:.4f}).")

            totals["B. Rolling Forecast Continuation"]["trades"] += 1
            totals["B. Rolling Forecast Continuation"]["pnl"] += pnl_B
            if pnl_B > 0: totals["B. Rolling Forecast Continuation"]["wins"] += 1
            
            with open(log_file, "a") as f:
                f.write(f"\n========================================================================\n")
                f.write(f"🪙 ASSET: {ticker} | SIGNAL: {trade_type} | ENTRY: ${entry_price:.4f}\n")
                f.write(f"========================================================================\n")
                f.write(f"--- Strategy A: Hard Time Exit (Outcome: {outcome_A} | P&L: ${pnl_A:+.2f}) ---\n")
                for entry in logs_A: f.write(f"   {entry}\n")
                f.write(f"\n--- Strategy B: Rolling Continuation (Outcome: {outcome_B} | P&L: ${pnl_B:+.2f}) ---\n")
                for entry in logs_B: f.write(f"   {entry}\n")
                f.write(f"------------------------------------------------------------------------\n")

    print("\n" + "="*80)
    print("🏆 HARD TIME EXIT vs. ROLLING FORECAST CONTINUATION PERFORMANCE SUMMARY 🏆")
    print("="*80)
    print(f"{'Execution Mode':<35} | {'Win Rate':<10} | {'Total P&L ($)':<15} | {'Avg P&L / Trade':<15}")
    print("-" * 80)
    for st_name, stats in totals.items():
        trades = stats["trades"]
        win_rate = (stats["wins"] / trades) * 100 if trades > 0 else 0.0
        tot_pnl = stats["pnl"]
        avg_pnl = tot_pnl / trades if trades > 0 else 0.0
        print(f"{st_name:<35} | {win_rate:>5.1f}%     | ${tot_pnl:>12.2f}  | ${avg_pnl:>12.2f}")
    print("="*80)
    print(f"✅ Detailed multi-window timeline logs written to: {log_file}")

if __name__ == "__main__":
    run_rolling_forecast_comparison()
