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

    print("Loading data...")
    df = pd.read_csv("./msft_data.csv")
    df['timestamps'] = pd.to_datetime(df['timestamps'])

    lookback = 400
    pred_len = 120

    print("Extracting features...")
    x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
    x_timestamp = df.loc[:lookback-1, 'timestamps']
    y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']

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
    
    print("Plotting...")
    kline_df = df.loc[:lookback+pred_len-1]
    pred_df.index = kline_df.index[-pred_df.shape[0]:]
    sr_close = kline_df['close']
    sr_pred_close = pred_df['close']
    sr_close.name = 'Ground Truth'
    sr_pred_close.name = "Prediction"
    close_df = pd.concat([sr_close, sr_pred_close], axis=1)

    fig, ax1 = plt.subplots(1, 1, figsize=(8, 4))
    ax1.plot(close_df['Ground Truth'], label='Ground Truth', color='blue', linewidth=1.5)
    ax1.plot(close_df['Prediction'], label='Prediction', color='red', linewidth=1.5)
    ax1.set_ylabel('Close Price', fontsize=14)
    ax1.legend(loc='lower left', fontsize=12)
    ax1.grid(True)
    plt.tight_layout()
    plt.savefig('msft_forecast.png')
    print("Saved msft_forecast.png")
except BaseException as e:
    import traceback
    traceback.print_exc()
    print("Caught exception:", repr(e))
