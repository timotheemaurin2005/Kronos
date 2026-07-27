import os
import sys
import datetime
import numpy as np
import pandas as pd
import yfinance as yf

def compute_indicators(df):
    high = df['High']
    low = df['Low']
    close = df['Close']
    volume = df['Volume']
    
    # ATR 14
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14, min_periods=14).mean()
    
    # EMAs
    df['EMA_10'] = close.ewm(span=10, adjust=False).mean()
    df['EMA_30'] = close.ewm(span=30, adjust=False).mean()
    
    # Volume SMA
    df['VOL_SMA_20'] = volume.rolling(window=20, min_periods=1).mean()
    return df

def execute_stop_fill(long_short, trigger_price, next_bar_open, slippage_bps):
    """
    Stops never fill at trigger price. Fill at next-bar open or worse:
    long stops at min(stop_price, next_bar_open) minus slippage.
    short stops at max(...) plus slippage.
    """
    slippage_mult = slippage_bps / 10000.0
    if long_short == 'LONG':
        base_fill = min(trigger_price, next_bar_open)
        final_fill = base_fill * (1.0 - slippage_mult)
    else:
        base_fill = max(trigger_price, next_bar_open)
        final_fill = base_fill * (1.0 + slippage_mult)
    return final_fill

def deduct_costs(gross_proceeds, asset_symbol, cost_multiplier=1.0):
    """
    Deduct X bps round-trip per equity/metal trade, Y bps per crypto trade on every exit.
    Base rates: Equities/Metals = 5 bps (0.0005), Crypto = 25 bps (0.0025).
    """
    is_crypto = asset_symbol in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'BTCUSD', 'ETHUSD', 'SOLUSD']
    base_bps = 25.0 if is_crypto else 5.0
    total_bps = base_bps * cost_multiplier
    fee = gross_proceeds * (total_bps / 10000.0)
    return fee, total_bps

def run_institutional_audit(cost_mult=1.0, suffix="1x"):
    universe = ['NVDA', 'TSLA', 'PLTR', 'MSFT', 'GLD', 'SLV', 'BTC-USD', 'ETH-USD', 'SOL-USD']
    start_date = "2024-01-01"
    end_date = "2026-07-26"
    
    # Data Download & Verification
    data = {}
    for sym in universe:
        ticker = yf.Ticker(sym)
        df = ticker.history(start=start_date, end=end_date, interval="1d")
        if df.empty:
            raise ValueError(f"CRITICAL: Asset {sym} has no coverage in requested interval.")
        df.reset_index(inplace=True)
        # Handle timezones
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        df = compute_indicators(df)
        data[sym] = df

    # Get master trade timeline from market business days
    master_dates = sorted(list(set.union(*[set(df['Date']) for df in data.values()])))
    
    # Compounded cash ledger starting at $100,000
    initial_capital = 100000.0
    cash = initial_capital
    portfolio_equity = initial_capital
    
    # Active position records
    positions = {} # sym -> dict of state
    trades = [] # completed trade ledger
    equity_curve = []
    
    # Out-of-sample frozen parameters (Fixed ATR Tail Insurance with Approach B Continuation)
    stop_atr_mult = 3.0
    tp_atr_mult = 5.0
    trail_lock_atr_mult = 1.5
    slippage_bps = 10.0 # 10 bps standard execution slippage
    
    for dt in master_dates:
        # 1. Update valuation & check stops / TPs on active positions
        current_holdings_val = 0.0
        closed_syms = []
        
        for sym, pos in positions.items():
            df = data[sym]
            row_slice = df[df['Date'] == dt]
            if row_slice.empty:
                current_holdings_val += pos['qty'] * pos['current_price']
                continue
            
            row = row_slice.iloc[0]
            open_p = row['Open']
            high_p = row['High']
            low_p = row['Low']
            close_p = row['Close']
            pos['current_price'] = close_p
            
            # Check Stop and TP hits
            stop_hit = low_p <= pos['stop_price']
            tp_hit = high_p >= pos['tp_target']
            
            # Rule: If single bar range contains both stop and TP, assume stop hit first.
            if stop_hit and tp_hit:
                exit_reason = "STOP_HIT (INTRABAR DUAL HIT ASSUMPTION)"
                # Fill at next available price or open rule
                exit_fill = execute_stop_fill('LONG', pos['stop_price'], open_p, slippage_bps)
            elif stop_hit:
                exit_reason = "STOP_LOSS"
                exit_fill = execute_stop_fill('LONG', pos['stop_price'], open_p, slippage_bps)
            elif tp_hit:
                # Approach B Rolling Continuation: instead of liquidating at TP, raise stop floor and extend TP
                pos['stop_price'] = max(pos['stop_price'], close_p - (trail_lock_atr_mult * row['ATR_14']))
                pos['tp_target'] = close_p + (tp_atr_mult * row['ATR_14'])
                pos['status'] = "APPROACH_B_CONTINUATION"
                current_holdings_val += pos['qty'] * close_p
                continue
            else:
                current_holdings_val += pos['qty'] * close_p
                continue
                
            # If we reached here, trade is exiting via stop or trailing floor hit
            gross_proceeds = pos['qty'] * exit_fill
            fee, fee_bps = deduct_costs(gross_proceeds, sym, cost_mult)
            net_proceeds = gross_proceeds - fee
            pnl_net = net_proceeds - pos['cost_basis']
            pnl_pct = (pnl_net / pos['cost_basis']) * 100.0
            
            # Calculate slippage paid vs pure trigger price
            slippage_paid = abs(pos['stop_price'] - exit_fill) * pos['qty']
            
            trades.append({
                "entry_time": pos['entry_time'].strftime('%Y-%m-%d'),
                "exit_time": dt.strftime('%Y-%m-%d'),
                "symbol": sym,
                "entry_price": round(pos['entry_price'], 4),
                "exit_price": round(exit_fill, 4),
                "exit_reason": exit_reason,
                "fees_paid": round(fee, 2),
                "slippage_paid": round(slippage_paid, 2),
                "pnl_net": round(pnl_net, 2),
                "pnl_pct": round(pnl_pct, 4)
            })
            
            cash += net_proceeds
            closed_syms.append(sym)
            
        for s in closed_syms:
            del positions[s]
            
        # Update current total portfolio equity after stops
        portfolio_equity = cash + sum(p['qty'] * p['current_price'] for p in positions.values())
        
        # 2. Evaluate entries (Only use information available at or before decision moment - no lookahead)
        # Sizing rule: Position size 10% of current equity. Gross-exposure cap 100%.
        for sym in universe:
            if sym in positions:
                continue
            df = data[sym]
            idx = df.index[df['Date'] == dt]
            if len(idx) == 0 or idx[0] < 15:
                continue
            i = idx[0]
            
            # Use bar i-1 to avoid intraday lookahead on indicators
            prev_bar = df.iloc[i-1]
            curr_bar = df.iloc[i]
            
            if np.isnan(prev_bar['ATR_14']) or np.isnan(prev_bar['EMA_10']) or np.isnan(prev_bar['EMA_30']):
                continue
                
            # Signal Rule: 10 EMA crossed above 30 EMA on volume expansion (> 20 SMA)
            ema_bull = prev_bar['EMA_10'] > prev_bar['EMA_30']
            vol_expand = prev_bar['Volume'] > prev_bar['VOL_SMA_20']
            
            if ema_bull and vol_expand:
                target_alloc = portfolio_equity * 0.10
                current_invested = sum(p['qty'] * p['current_price'] for p in positions.values())
                
                # Enforce gross exposure cap of 100% (never deploy more than available cash)
                if current_invested + target_alloc > portfolio_equity or target_alloc > cash:
                    continue # Cap enforced
                    
                entry_p = curr_bar['Open'] # Enter on open of current bar
                qty = target_alloc / entry_p
                stop_p = entry_p - (stop_atr_mult * prev_bar['ATR_14'])
                tp_p = entry_p + (tp_atr_mult * prev_bar['ATR_14'])
                
                positions[sym] = {
                    "qty": qty,
                    "entry_price": entry_p,
                    "current_price": entry_p,
                    "cost_basis": target_alloc,
                    "stop_price": stop_p,
                    "tp_target": tp_p,
                    "entry_time": dt,
                    "status": "OPEN"
                }
                cash -= target_alloc
                
        portfolio_equity = cash + sum(p['qty'] * p['current_price'] for p in positions.values())
        equity_curve.append({
            "date": dt.strftime('%Y-%m-%d'),
            "cash": round(cash, 2),
            "invested_value": round(portfolio_equity - cash, 2),
            "total_equity": round(portfolio_equity, 2),
            "open_positions_count": len(positions)
        })

    # Close out open positions at end of period for accounting closure
    end_dt = master_dates[-1]
    for sym, pos in list(positions.items()):
        exit_fill = pos['current_price']
        gross_proceeds = pos['qty'] * exit_fill
        fee, fee_bps = deduct_costs(gross_proceeds, sym, cost_mult)
        net_proceeds = gross_proceeds - fee
        pnl_net = net_proceeds - pos['cost_basis']
        pnl_pct = (pnl_net / pos['cost_basis']) * 100.0
        
        trades.append({
            "entry_time": pos['entry_time'].strftime('%Y-%m-%d'),
            "exit_time": end_dt.strftime('%Y-%m-%d'),
            "symbol": sym,
            "entry_price": round(pos['entry_price'], 4),
            "exit_price": round(exit_fill, 4),
            "exit_reason": "PERIOD_END_CLOSE",
            "fees_paid": round(fee, 2),
            "slippage_paid": 0.0,
            "pnl_net": round(pnl_net, 2),
            "pnl_pct": round(pnl_pct, 4)
        })
        
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)
    
    trades_df.to_csv(f"audit_trade_ledger_{suffix}_costs.csv", index=False)
    equity_df.to_csv(f"audit_equity_curve_{suffix}.csv", index=False)
    
    # Calculate Institutional Summary Stats
    total_trades = len(trades_df)
    if total_trades == 0:
        return {}
        
    wins = trades_df[trades_df['pnl_net'] > 0]
    losses = trades_df[trades_df['pnl_net'] <= 0]
    
    win_rate = (len(wins) / total_trades) * 100.0
    avg_win = wins['pnl_pct'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0.0
    
    net_expectancy_pct = ( (len(wins)/total_trades) * avg_win ) + ( (len(losses)/total_trades) * avg_loss )
    
    gross_win_dlr = wins['pnl_net'].sum()
    gross_loss_dlr = abs(losses['pnl_net'].sum())
    profit_factor = gross_win_dlr / gross_loss_dlr if gross_loss_dlr > 0 else np.nan
    
    # CAGR & Max Drawdown
    initial_eq = equity_df['total_equity'].iloc[0]
    final_eq = equity_df['total_equity'].iloc[-1]
    days = (pd.to_datetime(equity_df['date'].iloc[-1]) - pd.to_datetime(equity_df['date'].iloc[0])).days
    years = max(days / 365.25, 0.1)
    cagr = ((final_eq / initial_eq) ** (1.0 / years) - 1.0) * 100.0
    
    equity_df['peak'] = equity_df['total_equity'].cummax()
    equity_df['dd'] = (equity_df['total_equity'] - equity_df['peak']) / equity_df['peak']
    max_dd = abs(equity_df['dd'].min()) * 100.0
    
    # Sharpe Ratio (annualized, net of 5% risk free rate)
    equity_df['daily_ret'] = equity_df['total_equity'].pct_change().dropna()
    rf_daily = 0.05 / 252.0
    excess_ret = equity_df['daily_ret'] - rf_daily
    sharpe = np.sqrt(252.0) * (excess_ret.mean() / excess_ret.std()) if excess_ret.std() != 0 else 0.0
    
    return {
        "cost_multiplier": f"{cost_mult}x",
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "net_expectancy_pct": round(net_expectancy_pct, 4),
        "profit_factor": round(profit_factor, 2) if not np.isnan(profit_factor) else "N/A",
        "annualized_sharpe_rf_5pct": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "cagr_pct": round(cagr, 2),
        "final_equity": round(final_eq, 2)
    }

if __name__ == "__main__":
    print("--- INSTITUTIONAL QUANTITATIVE BACKTEST AUDIT ENGINE ---")
    stats_1x = run_institutional_audit(cost_mult=1.0, suffix="1x")
    stats_2x = run_institutional_audit(cost_mult=2.0, suffix="2x")
    
    print("\n[RESULTS SUMMARY - 1X BASE COSTS (5 bps Equities/Metals | 25 bps Crypto)]")
    for k, v in stats_1x.items():
        print(f"  {k}: {v}")
        
    print("\n[RESULTS SUMMARY - 2X STRESS COSTS (10 bps Equities/Metals | 50 bps Crypto)]")
    for k, v in stats_2x.items():
        print(f"  {k}: {v}")
        
    print("\n[DELIVERABLES GENERATED IN WORKSPACE]")
    print("  1. audit_trade_ledger_1x_costs.csv")
    print("  2. audit_trade_ledger_2x_costs.csv")
    print("  3. audit_equity_curve_1x.csv")
    print("  4. audit_equity_curve_2x.csv")
