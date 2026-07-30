import os
import dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

dotenv.load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

client = TradingClient(api_key, secret_key, paper=True)

print("Firing test order for 1 share of SPY...")
try:
    order_data = MarketOrderRequest(
        symbol="SPY",
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY
    )
    order = client.submit_order(order_data)
    print(f"✅ Success! Order ID: {order.id}")
    print(f"Status: {order.status} (It will queue and execute automatically at market open!)")
except Exception as e:
    print(f"❌ Failed to submit order: {e}")
