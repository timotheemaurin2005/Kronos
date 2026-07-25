print("STARTING SCRIPT")
import pandas as pd
print("pandas imported")
import sys
print("sys imported")
import matplotlib.pyplot as plt
print("plt imported")
sys.path.append("./")
print("Importing model...")
from model import Kronos, KronosTokenizer, KronosPredictor
print("Model imported")

print("Loading model...")
sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

try:
    print("Initializing...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512, device='cpu')

    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "MSFT"
    print(f"Loading data for {ticker}...")
    df = pd.read_csv(f"./{ticker.lower()}_data.csv")
    
    # We already upgraded pandas to 3.0.3 so to_datetime should be fine now
    df['timestamps'] = pd.to_datetime(df['timestamps'])

    lookback = 400
    pred_len = 120

    print("Extracting features...")
    # Take the most recent data
    x_df = df.iloc[-lookback:].reset_index(drop=True)[['open', 'high', 'low', 'close', 'volume', 'amount']]
    x_timestamp = df.iloc[-lookback:]['timestamps'].reset_index(drop=True)
    
    # Generate future timestamps
    last_timestamp = x_timestamp.iloc[-1]
    y_timestamp = pd.Series(pd.date_range(start=last_timestamp + pd.Timedelta(minutes=5), periods=pred_len, freq='5min'))

    print("Running prediction...")
    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
        verbose=True
    )
    
    print("Prediction head:")
    print(pred_df.head())
    
    print("Plotting with mplfinance...")
    import mplfinance as mpf
    
    # Prepare history dataframe (last 100 periods)
    hist_plot = x_df.iloc[-100:].copy()
    hist_plot['timestamps'] = x_timestamp.iloc[-100:].values
    
    # Prepare prediction dataframe
    pred_plot = pred_df.copy()
    pred_plot['timestamps'] = y_timestamp.values
    
    # Combine them
    plot_df = pd.concat([hist_plot, pred_plot], ignore_index=True)
    plot_df.set_index('timestamps', inplace=True)
    
    # mplfinance requires Capitalized column names
    plot_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
    
    # Vertical line indicating where prediction starts
    pred_start_date = y_timestamp.iloc[0]
    
    # mplfinance and pandas often clash with tz-aware vs tz-naive, so strip timezones for plotting
    plot_df.index = plot_df.index.tz_localize(None)
    if hasattr(pred_start_date, 'tz_localize') and pred_start_date.tzinfo is not None:
        pred_start_date = pred_start_date.tz_localize(None)
    
    mpf.plot(
        plot_df, 
        type='candle', 
        style='yahoo', 
        title=f"{ticker} 5-Min Kronos Forecast (Live Data)",
        vlines=dict(vlines=pred_start_date, colors='red', linestyle='dashed', linewidths=1.5),
        savefig=f"{ticker.lower()}_forecast.png",
        figratio=(12, 6)
    )
    print(f"Saved {ticker.lower()}_forecast.png")
except BaseException as e:
    import traceback
    traceback.print_exc()
    print("Caught exception:", repr(e))
