import asyncio
import pandas as pd
import sys
import json
import requests

# Antigravity SDK imports
from google.antigravity import Agent, LocalAgentConfig

# Kronos imports
sys.path.append("./")
from model import Kronos, KronosTokenizer, KronosPredictor

# --- MOCK TOOLS FOR INGESTION AGENT ---

def fetch_twitter_sentiment(ticker: str) -> str:
    """Fetches recent social media sentiment and tweets for a given stock ticker.
    
    Args:
        ticker: The stock ticker, e.g. "MSFT" or "AAPL"
    """
    return (
        "NOTE: Real social media sentiment (X/Twitter, StockTwits, Reddit) requires API authentication. "
        "Please rely on the `fetch_news_headlines` and `fetch_macro_calendar` tools for real data until an API key is provided."
    )


def fetch_news_headlines(ticker: str) -> str:
    """Fetches real breaking macroeconomic news and headlines for a given stock ticker using Yahoo Finance.
    
    Args:
        ticker: The stock ticker, e.g. "MSFT" or "AAPL"
    """
    import yfinance as yf
    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news
        if not news_items:
            return f"No breaking news found for {ticker}."
            
        summary = f"Recent News for {ticker}:\n"
        for item in news_items[:5]:  # Get top 5 articles
            # The structure from yfinance is typically item['content']['title']
            content = item.get('content', {})
            title = content.get('title', item.get('title', 'Unknown Title'))
            desc = content.get('summary', item.get('summary', ''))
            pub_date = content.get('pubDate', item.get('pubDate', ''))
            summary += f"- [{pub_date}] {title}\n  Summary: {desc}\n\n"
        return summary
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def fetch_macro_calendar() -> str:
    """Fetches high-impact macroeconomic events and speeches for this week from ForexFactory.
    This is extremely useful for identifying macro headwinds or tailwinds.
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        events = response.json()
        
        # Filter for High impact events
        high_impact = [e for e in events if e.get('impact') == 'High']
        
        if not high_impact:
            return "No high-impact macro events scheduled for this week."
            
        summary = "High Impact Macro Events This Week:\n"
        for e in high_impact:
            date_str = e.get('date', 'Unknown Date')
            title = e.get('title', 'Unknown Event')
            country = e.get('country', '')
            forecast = e.get('forecast', '')
            summary += f"- [{date_str}] {country}: {title} (Forecast: {forecast})\n"
        return summary
    except Exception as e:
        return f"Error fetching macro calendar: {str(e)}"


# --- META ORCHESTRATOR ---

async def run_meta_strategy(ticker: str):
    print(f"--- Running Meta-Strategy for {ticker} ---")
    
    # 1. Gather technical forecast using Kronos
    print("\n[1] Running Kronos Quantitative Model...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    
    # KronosPredictor will automatically fallback to CPU if MPS is detected, per our fix.
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    
    data_file = f"./{ticker.lower()}_data.csv"
    df = pd.read_csv(data_file)
    df['timestamps'] = pd.to_datetime(df['timestamps'])
    lookback = 400
    pred_len = 120
    x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
    x_timestamp = df.loc[:lookback-1, 'timestamps']
    y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']

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
    
    start_price = x_df['close'].iloc[-1]
    end_price = pred_df['close'].iloc[-1]
    pct_change = ((end_price - start_price) / start_price) * 100
    
    print(f"-> Kronos technical prediction: {pct_change:.2f}% price change over next 120 steps.")
    print(f"-> Start Price: ${start_price:.2f}, Projected End Price: ${end_price:.2f}")

    # 2. Gather sentiment using Antigravity News Agent
    print("\n[2] Running Antigravity News Ingestion Agent...")
    config = LocalAgentConfig(
        tools=[fetch_twitter_sentiment, fetch_news_headlines, fetch_macro_calendar],
        system_instructions=(
            "You are an expert financial macro analyst. Use your tools to fetch Twitter sentiment, "
            "news headlines, and the macro economic calendar for the requested ticker. "
            "Analyze the data and provide a concise summary of the fundamental market sentiment. "
            "Conclude with a final Sentiment Rating: Positive, Neutral, or Negative."
        ),
        # Default model is gemini-1.5-pro which is great for analysis
    )
    
    agent_analysis = ""
    async with Agent(config) as agent:
        response = await agent.chat(f"Analyze the current news and sentiment for {ticker}.")
        print("-> Agent Output: ", end="")
        async for chunk in response:
            print(chunk, end="", flush=True)
            agent_analysis += chunk
    print("\n")

    # 3. Meta-Decision (Simple Demo Logic)
    print("\n[3] Meta-Orchestrator Decision...")
    technical_signal = "BULLISH" if pct_change > 0 else "BEARISH"
    fundamental_signal = "POSITIVE" if "Positive" in agent_analysis else ("NEGATIVE" if "Negative" in agent_analysis else "NEUTRAL")
    
    print(f"Technical Signal:  {technical_signal}")
    print(f"Fundamental Signal: {fundamental_signal}")
    
    if technical_signal == "BULLISH" and fundamental_signal == "POSITIVE":
        print(">>> FINAL DECISION: STRONG BUY (Signals aligned)")
    elif technical_signal == "BEARISH" and fundamental_signal == "NEGATIVE":
        print(">>> FINAL DECISION: STRONG SELL (Signals aligned)")
    else:
        print(">>> FINAL DECISION: HOLD (Mixed signals)")

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    asyncio.run(run_meta_strategy(ticker))
