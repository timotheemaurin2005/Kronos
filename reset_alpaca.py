import os
import dotenv
from alpaca.trading.client import TradingClient

dotenv.load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

def reset_alpaca():
    if not api_key or not secret_key:
        print("Missing Alpaca API credentials in .env")
        return
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        print("Closing all open positions and canceling pending orders on Alpaca Paper Trading...")
        closed_positions = client.close_all_positions(cancel_orders=True)
        if not closed_positions:
            print("No open positions found.")
        else:
            print(f"Issued close requests for {len(closed_positions)} position(s).")
            for pos in closed_positions:
                print(f" - Cancel/Close requested for {pos.symbol}")
        print("✅ Alpaca portfolio has been reset to its initial cash state.")
    except Exception as e:
        print(f"❌ Error resetting Alpaca portfolio: {e}")

if __name__ == "__main__":
    reset_alpaca()
