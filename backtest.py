import yfinance as yf
import pandas as pd
import numpy as np
import random
import argparse
import sys
import os
import datetime
import torch

# Import Kronos
sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

def run_backtest(ticker, num_samples, lookback, pred_len):
    print(f"Loading data for {ticker}...")
    stock = yf.Ticker(ticker)
    df = stock.history(period="60d", interval="5m")
    
    if df.empty:
        print("No data found!")
        return

    df.reset_index(inplace=True)
    if 'Datetime' in df.columns:
        df.rename(columns={'Datetime': 'timestamps'}, inplace=True)
    elif 'Date' in df.columns:
        df.rename(columns={'Date': 'timestamps'}, inplace=True)
        
    df.columns = [c.lower() for c in df.columns]
    df['timestamps'] = pd.to_datetime(df['timestamps'])
    
    if len(df) < lookback + pred_len:
        print("Not enough data to backtest!")
        return
        
    print(f"Total historical 5m bars: {len(df)}")
    
    # Load model
    device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Loading Kronos model ({device.upper()})...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
    
    print(f"Starting simulation for {num_samples} random points...")
    
    # Pick random indices
    max_idx = len(df) - pred_len
    min_idx = lookback
    
    if num_samples > (max_idx - min_idx):
        num_samples = max_idx - min_idx
        
    # We want to avoid highly overlapping samples if possible
    # Just simple random choice for now
    test_indices = sorted(random.sample(range(min_idx, max_idx), num_samples))
    
    total_trades = 0
    wins = 0
    losses = 0
    timeouts = 0
    total_pnl = 0.0
    
    portfolio_size = 10000.0 # USD ($10k per trade)
    
    for count, idx in enumerate(test_indices, 1):
        print(f"\n--- Trade {count}/{num_samples} ---")
        trade_time = df['timestamps'].iloc[idx-1]
        print(f"Simulating state at: {trade_time}")
        
        # Prepare x
        x_df = df.iloc[idx-lookback : idx].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
        x_timestamp = df.iloc[idx-lookback : idx]['timestamps'].reset_index(drop=True)
        x_df['amount'] = x_df['volume'] * x_df[['open', 'high', 'low', 'close']].mean(axis=1)
        
        # y_timestamp (the actual times of the future)
        actual_y = df.iloc[idx : idx+pred_len].reset_index(drop=True)
        y_timestamp = actual_y['timestamps']
        
        print("Running Kronos inference...")
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False
        )
        
        # Determine signal based on max profit
        buy_time_long, sell_time_long = None, None
        buy_price_long, sell_price_long = 0, 0
        max_profit_long = -float('inf')
        
        sell_time_short, buy_time_short = None, None
        sell_price_short, buy_price_short = 0, 0
        max_profit_short = -float('inf')
        
        prediction_data = [row for _, row in pred_df.iterrows()]
        
        if len(prediction_data) > 1:
            # LONG
            min_price_idx = 0
            for i in range(1, len(prediction_data)):
                if prediction_data[i]['close'] < prediction_data[min_price_idx]['close']:
                    min_price_idx = i
                profit = prediction_data[i]['close'] - prediction_data[min_price_idx]['close']
                if profit > max_profit_long and i > min_price_idx:
                    max_profit_long = profit
                    buy_time_long = y_timestamp.iloc[min_price_idx]
                    sell_time_long = y_timestamp.iloc[i]
                    buy_price_long = prediction_data[min_price_idx]['close']
                    sell_price_long = prediction_data[i]['close']

            # SHORT
            max_price_idx = 0
            for i in range(1, len(prediction_data)):
                if prediction_data[i]['close'] > prediction_data[max_price_idx]['close']:
                    max_price_idx = i
                profit = prediction_data[max_price_idx]['close'] - prediction_data[i]['close']
                if profit > max_profit_short and i > max_price_idx:
                    max_profit_short = profit
                    sell_time_short = y_timestamp.iloc[max_price_idx]
                    buy_time_short = y_timestamp.iloc[i]
                    sell_price_short = prediction_data[max_price_idx]['close']
                    buy_price_short = prediction_data[i]['close']
                    
        trade_type = None
        if max_profit_long > 0 or max_profit_short > 0:
            if max_profit_long >= max_profit_short:
                trade_type = "LONG"
                entry_time = buy_time_long
                exit_time = sell_time_long
                entry_price = buy_price_long
                take_profit = sell_price_long
                
                # SL for LONG: minimum predicted low between entry and exit
                min_between = entry_price
                start_counting = False
                for idx in range(len(pred_df)):
                    p = pred_df.iloc[idx]
                    if y_timestamp.iloc[idx] == entry_time: start_counting = True
                    if start_counting:
                        if p['low'] < min_between: min_between = p['low']
                    if y_timestamp.iloc[idx] == exit_time: break
                stop_loss = min_between * 0.995 
                if stop_loss > entry_price * 0.99:
                    stop_loss = entry_price * 0.99
            else:
                trade_type = "SHORT"
                entry_time = sell_time_short
                exit_time = buy_time_short
                entry_price = sell_price_short
                take_profit = buy_price_short
                
                max_between = entry_price
                start_counting = False
                for idx in range(len(pred_df)):
                    p = pred_df.iloc[idx]
                    if y_timestamp.iloc[idx] == entry_time: start_counting = True
                    if start_counting:
                        if p['high'] > max_between: max_between = p['high']
                    if y_timestamp.iloc[idx] == exit_time: break
                stop_loss = max_between * 1.005
                if stop_loss < entry_price * 1.01:
                    stop_loss = entry_price * 1.01
        
        if not trade_type:
            print("No profitable trade identified by model. Skipping.")
            continue
            
        print(f"Signal: {trade_type} | Entry: ${entry_price:.2f} | TP: ${take_profit:.2f} | SL: ${stop_loss:.2f}")
        
        # Simulation
        total_trades += 1
        trade_active = False
        outcome = "TIMEOUT"
        pnl = 0.0
        shares = portfolio_size / entry_price
        
        for i, row in actual_y.iterrows():
            t = row['timestamps']
            
            # Check entry
            if not trade_active and t >= entry_time:
                # Approximate entry at open of that candle
                trade_active = True
                print(f"  [Sim] Trade entered at {t} (Actual Open: ${row['open']:.2f})")
                
            if trade_active:
                # Check SL/TP based on high/low
                if trade_type == "LONG":
                    if row['low'] <= stop_loss:
                        outcome = "LOSS (SL Hit)"
                        pnl = shares * (stop_loss - entry_price)
                        print(f"  [Sim] 🛑 Stop Loss triggered at {t}")
                        break
                    elif row['high'] >= take_profit:
                        outcome = "WIN (TP Hit)"
                        pnl = shares * (take_profit - entry_price)
                        print(f"  [Sim] ✅ Take Profit triggered at {t}")
                        break
                else: # SHORT
                    if row['high'] >= stop_loss:
                        outcome = "LOSS (SL Hit)"
                        # Short loss: sell_price - buy_price
                        pnl = shares * (entry_price - stop_loss)
                        print(f"  [Sim] 🛑 Stop Loss triggered at {t}")
                        break
                    elif row['low'] <= take_profit:
                        outcome = "WIN (TP Hit)"
                        pnl = shares * (entry_price - take_profit)
                        print(f"  [Sim] ✅ Take Profit triggered at {t}")
                        break
                        
                # Check timeout exit
                if t >= exit_time:
                    outcome = "TIMEOUT (Time Exit)"
                    close_price = row['close']
                    if trade_type == "LONG":
                        pnl = shares * (close_price - entry_price)
                    else:
                        pnl = shares * (entry_price - close_price)
                    print(f"  [Sim] ⏱️ Timeout exit at {t} (Price: ${close_price:.2f})")
                    break

        if outcome.startswith("WIN") or (outcome.startswith("TIMEOUT") and pnl > 0):
            wins += 1
        elif outcome.startswith("LOSS") or (outcome.startswith("TIMEOUT") and pnl < 0):
            losses += 1
        else:
            timeouts += 1 # Timeout at 0 pnl
            
        total_pnl += pnl
        print(f"Result: {outcome} | P&L: ${pnl:.2f}")
        print("-" * 40)
        
    print("\n" + "="*40)
    print("BACKTEST SUMMARY")
    print("="*40)
    print(f"Total Trades Taken: {total_trades}")
    if total_trades > 0:
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        print(f"Timeouts (Break Even): {timeouts}")
        print(f"Win Rate (including profitable timeouts): {(wins/total_trades)*100:.1f}%")
        print(f"Total P&L: ${total_pnl:.2f}")
        print(f"Average P&L per Trade: ${(total_pnl/total_trades):.2f}")
    print("="*40)
    
    return {
        "ticker": ticker,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate": (wins/total_trades)*100 if total_trades > 0 else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": (total_pnl/total_trades) if total_trades > 0 else 0.0
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kronos Backtester")
    parser.add_argument("--ticker", type=str, default="PLTR", help="Ticker symbol")
    parser.add_argument("--samples", type=int, default=10, help="Number of random trades to simulate")
    parser.add_argument("--lookback", type=int, default=400, help="Model lookback period")
    parser.add_argument("--pred_len", type=int, default=120, help="Model prediction length")
    args = parser.parse_args()
    
    run_backtest(args.ticker, args.samples, args.lookback, args.pred_len)
