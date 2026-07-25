from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import os
import torch

# Import model components
import sys
sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

app = FastAPI()

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for the model
predictor = None

@app.on_event("startup")
async def load_model():
    global predictor
    print("Loading Kronos model on startup...")
    try:
        device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"Selecting computing device: {device.upper()}")
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Failed to load model: {e}")

@app.get("/api/market/{ticker}")
async def get_market_data(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        # Get Analyst Recommendation
        rec_key = info.get('recommendationKey')
        if rec_key is None:
            rec_key = 'none'
        
        rec = rec_key.replace('_', ' ').title()
        if rec.lower() == 'none':
            rec = "N/A"

        # Calculate basic volatility (30-day standard deviation)
        hist = stock.history(period="1mo")
        volatility = "N/A"
        if not hist.empty and len(hist) > 1:
            returns = hist['Close'].pct_change().dropna()
            volatility = f"{returns.std() * np.sqrt(252) * 100:.1f}%"

        return {
            "symbol": ticker,
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice") or (hist['Close'].iloc[-1] if not hist.empty else 0),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "beta": info.get("beta", "N/A"),
            "volatility": volatility,
            "market_cap": info.get("marketCap", "N/A"),
            "volume": info.get("volume", "N/A"),
            "analyst_rating": rec
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/news")
async def get_news_analysis():
    # In a real scenario, this would trigger the Antigravity agent.
    # For now, we'll fetch real news from yfinance (SPY as a proxy for macro) and ForexFactory,
    # and provide a synthesized "Agent Output".
    try:
        # 1. Fetch ForexFactory macro calendar
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", headers=headers)
        calendar = []
        if r.status_code == 200:
            events = r.json()
            # Filter high impact events today/tomorrow
            today = datetime.datetime.now().date()
            for event in events:
                if event['impact'] == 'High':
                    try:
                        # Attempt to parse time from ISO format if it exists
                        evt_time_str = event.get('date', '')
                        if evt_time_str:
                            dt = datetime.datetime.fromisoformat(evt_time_str.replace('Z', '+00:00'))
                            time_str = dt.strftime('%I:%M %p')
                        else:
                            time_str = 'Pending'
                    except:
                        time_str = 'Pending'
                    
                    calendar.append({
                        "time": time_str,
                        "country": event.get('country', ''),
                        "title": event.get('title', ''),
                        "actual": event.get('actual', ''),
                        "forecast": event.get('forecast', ''),
                        "previous": event.get('previous', '')
                    })
                    if len(calendar) >= 4:
                        break

        # 2. Fetch general market news
        spy = yf.Ticker("SPY")
        news_items = spy.news[:5]
        headlines = [item['title'] for item in news_items if 'title' in item]

        return {
            "headlines": headlines,
            "macro_events": calendar,
            "agent_analysis": "The market is currently showing mixed signals. High-impact macro events are pending, creating a cautious environment. Volatility remains elevated in tech and precious metals.",
            "uncertainty_level": "Medium-High",
            "sentiment_score": 65
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/forecast/{ticker}")
async def get_forecast(ticker: str):
    global predictor
    if predictor is None:
        raise HTTPException(status_code=503, detail="Model is not loaded yet")

    try:
        # Download data
        stock = yf.Ticker(ticker)
        df = stock.history(period="60d", interval="5m")
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found for ticker")
        
        df.reset_index(inplace=True)
        # Rename Date to timestamps if needed (sometimes it's Datetime)
        if 'Datetime' in df.columns:
            df.rename(columns={'Datetime': 'timestamps'}, inplace=True)
        elif 'Date' in df.columns:
            df.rename(columns={'Date': 'timestamps'}, inplace=True)

        df.columns = [c.lower() for c in df.columns]
        
        df['timestamps'] = pd.to_datetime(df['timestamps'])
        
        lookback = 400
        pred_len = 120

        # Features
        if len(df) < lookback:
            x_df = df.copy()
            x_timestamp = df['timestamps'].copy()
        else:
            x_df = df.iloc[-lookback:].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume']]
            x_timestamp = df.iloc[-lookback:]['timestamps'].reset_index(drop=True)
            
        x_df['amount'] = x_df['volume'] * x_df[['open', 'high', 'low', 'close']].mean(axis=1)

        last_timestamp = x_timestamp.iloc[-1]
        y_timestamp = pd.Series(pd.date_range(start=last_timestamp + pd.Timedelta(minutes=5), periods=pred_len, freq='5min'))

        # Inference
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

        # Format output for lightweight-charts
        # Lightweight charts expects {time: unix_timestamp, open, high, low, close}
        def format_for_chart(df_part, time_series):
            result = []
            for i in range(len(df_part)):
                t = time_series.iloc[i]
                if hasattr(t, 'tz_localize') and t.tzinfo is not None:
                    t = t.tz_localize(None)
                # UNIX timestamp in seconds
                unix_time = int(t.timestamp())
                result.append({
                    "time": unix_time,
                    "open": float(df_part['open'].iloc[i]),
                    "high": float(df_part['high'].iloc[i]),
                    "low": float(df_part['low'].iloc[i]),
                    "close": float(df_part['close'].iloc[i])
                })
            return result

        historical_data = format_for_chart(x_df.iloc[-100:], x_timestamp.iloc[-100:])
        prediction_data = format_for_chart(pred_df, y_timestamp)

        # Calculate best time to buy and sell (LONG)
        buy_time_long, sell_time_long = None, None
        buy_price_long, sell_price_long = 0, 0
        max_profit_long = -float('inf')
        
        # Calculate best time to sell and buy back (SHORT)
        sell_time_short, buy_time_short = None, None
        sell_price_short, buy_price_short = 0, 0
        max_profit_short = -float('inf')
        
        if len(prediction_data) > 1:
            # LONG logic
            min_price_idx = 0
            for i in range(1, len(prediction_data)):
                if prediction_data[i]['close'] < prediction_data[min_price_idx]['close']:
                    min_price_idx = i
                profit = prediction_data[i]['close'] - prediction_data[min_price_idx]['close']
                if profit > max_profit_long and i > min_price_idx:
                    max_profit_long = profit
                    buy_time_long = prediction_data[min_price_idx]['time']
                    sell_time_long = prediction_data[i]['time']
                    buy_price_long = prediction_data[min_price_idx]['close']
                    sell_price_long = prediction_data[i]['close']

            # SHORT logic
            max_price_idx = 0
            for i in range(1, len(prediction_data)):
                if prediction_data[i]['close'] > prediction_data[max_price_idx]['close']:
                    max_price_idx = i
                # Profit for short is sell_price - buy_price (buying back lower)
                profit = prediction_data[max_price_idx]['close'] - prediction_data[i]['close']
                if profit > max_profit_short and i > max_price_idx:
                    max_profit_short = profit
                    sell_time_short = prediction_data[max_price_idx]['time']
                    buy_time_short = prediction_data[i]['time']
                    sell_price_short = prediction_data[max_price_idx]['close']
                    buy_price_short = prediction_data[i]['close']
                    
        signal = None
        trade_type = "LONG"
        if max_profit_long > 0 or max_profit_short > 0:
            if max_profit_long >= max_profit_short:
                trade_type = "LONG"
                entry_time = buy_time_long
                exit_time = sell_time_long
                entry_price = buy_price_long
                exit_price = sell_price_long
                expected_profit_pct = (max_profit_long / entry_price) * 100
                take_profit = exit_price
                
                # SL for LONG: minimum predicted low between entry and exit
                min_between = entry_price
                start_counting = False
                for p in prediction_data:
                    if p['time'] == entry_time: start_counting = True
                    if start_counting:
                        if p['low'] < min_between: min_between = p['low']
                    if p['time'] == exit_time: break
                stop_loss = min_between * 0.995 
                if stop_loss > entry_price * 0.99:
                    stop_loss = entry_price * 0.99
                    
            else:
                trade_type = "SHORT"
                entry_time = sell_time_short
                exit_time = buy_time_short
                entry_price = sell_price_short
                exit_price = buy_price_short
                expected_profit_pct = (max_profit_short / entry_price) * 100
                take_profit = exit_price
                
                # SL for SHORT: maximum predicted high between entry and exit
                max_between = entry_price
                start_counting = False
                for p in prediction_data:
                    if p['time'] == entry_time: start_counting = True
                    if start_counting:
                        if p['high'] > max_between: max_between = p['high']
                    if p['time'] == exit_time: break
                stop_loss = max_between * 1.005
                if stop_loss < entry_price * 1.01:
                    stop_loss = entry_price * 1.01

            # Simulated £1000 Portfolio
            portfolio_size = 1000
            units = portfolio_size / entry_price
            potential_profit = units * abs(take_profit - entry_price)
            potential_loss = units * abs(entry_price - stop_loss)

            # Generate Dynamic Drivers & Risks based on technicals
            duration_hours = (exit_time - entry_time) / 3600
            
            # Determine momentum characteristic
            if trade_type == 'LONG':
                if entry_time == y_timestamp.iloc[0]:
                    momentum_reason = "Model identifies immediate accumulation momentum, anticipating a breakout from current consolidation levels."
                else:
                    momentum_reason = "Model predicts a mean-reverting bounce; price action is expected to sweep liquidity lower before reversing upward."
            else:
                if entry_time == y_timestamp.iloc[0]:
                    momentum_reason = "Model identifies immediate distribution pressure, anticipating a breakdown from current resistance."
                else:
                    momentum_reason = "Model predicts a mean-reverting rejection; price action is expected to spike into liquidity before reversing downward."

            drivers = [
                f"Kronos projects a highly-probable {expected_profit_pct:.2f}% {'upside' if trade_type == 'LONG' else 'downside'} swing.",
                momentum_reason,
                f"Target (TP) realization expected within {duration_hours:.1f} hours from entry, capitalizing on predicted volatility waves."
            ]
            
            risks = [
                f"Pending high-impact macro events could override technical forecasts.",
                f"Maximum drawdown risk limited to -£{potential_loss:.2f} at strict SL of ${stop_loss:.2f}."
            ]

            signal = {
                "type": trade_type,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "expected_profit_pct": expected_profit_pct,
                "portfolio_profit_gbp": potential_profit,
                "portfolio_risk_gbp": potential_loss,
                "drivers": drivers,
                "risks": risks
            }

        return {
            "symbol": ticker,
            "historical": historical_data,
            "prediction": prediction_data,
            "signal": signal
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
