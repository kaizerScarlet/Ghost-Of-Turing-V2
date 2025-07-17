import aiofiles
import asyncio
import json
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime, timedelta
from textblob import TextBlob
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import MinMaxScaler
from statsmodels.tsa.arima.model import ARIMA
from transformers import TimeSeriesTransformer
from forexcalendar import ForexCalendar
import yfinance as yf
import tweepy
import newsapi
import pandas as pd
from datetime import date
from datetime import datetime
import traceback
from orderflowBinance import orderflowBinance
import nest_asyncio
nest_asyncio.apply()
import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime 
import numpy as np
import tensorflow as tf
import asyncio
import json
import pandas as pd
import traceback
import MetaTrader5 as mt5
import websockets
from datetime import datetime


symbol_binance = "btcusdt"
symbol_mt5 = "BTCUSD"  # Adjust based on your MT5 broker
depth_url = f"wss://stream.binance.com:9443/ws/{symbol_binance}@depth@100ms"
aggtrade_url = f"wss://stream.binance.com:9443/ws/{symbol_binance}@aggTrade"

tolerance = 1.0
order_state = {}


# Account details
account_id = 48838391  # Replace with your MT5 account ID
password = "asfhajsfghu"  # Replace with your MT5 account password
server = "HFMarketsSA-Demo"



if not mt5.initialize():
    print("Initialization failed:", mt5.last_error())
    mt5.shutdown()
    exit()

if not mt5.login(account_id, password=password, server=server):
    print("Login failed:", mt5.last_error())
    mt5.shutdown()
    exit()

print("✅ Login success!")


async def now():
    return datetime.utcnow()

# Get latest buy price for symbol
async def get_bid_price(symbol):
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"Could not retrieve tick data for symbol {symbol}")
        return tick.bid
    except Exception as e:
        print(f"Error in get_bid_price: {e}")
        return None

# Fetch the latest sell price for the symbol
async def get_ask_price(symbol):
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"Could not retrieve tick data for symbol {symbol}")
        return tick.ask
    except Exception as e:
        print(f"Error in get_ask_price: {e}")
        return None

# Get spread of Symbol
async def get_spread(symbol):
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"Could not retrieve tick data for symbol {symbol}")
        return tick.ask - tick.bid
    except Exception as e:
        print(f"Error in get_spread: {e}")
        return None



#Get the mid price
async def get_mt5_price():
    tick = mt5.symbol_info_tick(symbol_mt5)
    return (tick.ask + tick.bid) / 2 if tick else None


#Initial SL and TP placement when trades are placed for the first time
async def calculate_sl_tp_from_snapshot(action, snapshot_file, top_n=10, min_qty=0.5):
    """Stream of consciousness"""
    #What is missing is the data and T$S is continuously getting streamed into a file
    #we need to have a routine that dynamically determines the liquidity pool at each stream
    #this will ensure that when ever this function is called the SL and TP is always placed in accordance to liquidity pool
    #There has to be a way of tracking liquidity shift in the function, to guard secured profits and reduce losses.
    
    try:
        with open(snapshot_file, "r") as f:
            lines = f.readlines()
            if not lines:
                return None, None

            last_line = lines[-1]
            snapshot = json.loads(last_line)
            df = pd.DataFrame(snapshot)
            if df.empty or "price" not in df or "quantity" not in df or "side" not in df:
                return None, None

            bids = df[df["side"] == "bid"].copy()
            asks = df[df["side"] == "ask"].copy()
            bids = bids[bids["quantity"] >= min_qty]
            asks = asks[asks["quantity"] >= min_qty]

            current_price = get_mt5_price()
            if action == "buy":
                # SL below big bid, TP just below resistance ask
                if bids.empty or asks.empty:
                    return None, None
                nearest_bid = bids[bids["price"] < current_price].sort_values("price", ascending=False).head(top_n)
                resistance_pool = asks[asks["price"] > current_price].sort_values("price").head(top_n)

                stop_loss = nearest_bid["price"].min()
                take_profit = resistance_pool["price"].max()

            elif action == "sell":
                # SL above big ask, TP just above support bid
                if bids.empty or asks.empty:
                    return None, None
                nearest_ask = asks[asks["price"] > current_price].sort_values("price").head(top_n)
                support_pool = bids[bids["price"] < current_price].sort_values("price", ascending=False).head(top_n)

                stop_loss = nearest_ask["price"].max()
                take_profit = support_pool["price"].min()

            else:
                return None, None

            return round(stop_loss, 2), round(take_profit, 2) if stop_loss and take_profit else (None, None)

    except Exception as e:
        print("❗ Error calculating SL/TP from snapshot:", e)
        return None, None


#Place market order
async def place_market_order(action):
    today_str = datetime.now().date().isoformat()
    stop_loss, take_profit = calculate_sl_tp_from_snapshot(
        action, f"btcusdt-updates-{today_str}.txt"
    )
    #insert a conditional check here to improve trade check if it can handle the liquidity build up
    # if the determined SL stays too far from what the account can handle on a determined risk percentage then pass on the trade, no use 
    #entering even if you are right because the liquidity grab will blow account
    if stop_loss is None or take_profit is None:
        print("⚠️ Could not determine SL/TP — skipping order")
        return

    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol_mt5).ask if action == "buy" else mt5.symbol_info_tick(symbol_mt5).bid
    
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol_mt5,
        "volume": 0.01,
        "type": order_type,
        "price": price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 10,
        "magic": 10001,
        "comment": "GhostOfTuring",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    print(f"🚀 Market {action.upper()} placed at {price} | SL: {stop_loss} | TP: {take_profit} — result: {result}")

#Place stop order
async def place_stop_order(action, stop_price):
    today_str = datetime.now().date().isoformat()
    stop_loss, take_profit = calculate_sl_tp_from_snapshot(
        action, f"btcusdt-updates-{today_str}.txt"
    )
    #insert a conditional check here to improve trade check if it can handle the liquidity build up
    # if the determined SL stays too far from what the account can handle on a determined risk percentage then pass on the trade, no use 
    #entering even if you are right because the liquidity grab will blow account
    if stop_loss is None or take_profit is None:
        print("⚠️ Could not determine SL/TP for stop order — skipping")
        return

    order_type = mt5.ORDER_TYPE_BUY_STOP if action == "buy" else mt5.ORDER_TYPE_SELL_STOP
    
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol_mt5,
        "volume": 0.01,
        "type": order_type,
        "price": stop_price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 10,
        "magic": 10001,
        "comment": "GhostOfTuring",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(request)
    print(f"⏱️ STOP {action.upper()} @ {stop_price} | SL: {stop_loss} | TP: {take_profit} — result:", result)

    
    
#checks if it can place a trade    
async def can_place_order(order_price, current_price, stop_level_points, point_size, direction="above"):
    """Check if the order price is valid given min stop level"""
    #insert a conditional check here to improve trade check if it can handle the liquidity build up
    # if the determined SL stays too far from what the account can handle on a determined risk percentage then pass on the trade, no use 
    #entering even if you are right because the liquidity grab will blow account
    #this must be modified so that we do clutter the order placement functions
    min_distance = stop_level_points * point_size
    if direction == "above":
        return (order_price - current_price) >= min_distance
    else:  # direction == "below"
        return (current_price - order_price) >= min_distance

    
#Place limit order
async def place_limit_order(action, limit_price):
    today_str = datetime.now().date().isoformat()
    stop_loss, take_profit = calculate_sl_tp_from_snapshot(
        action, f"btcusdt-updates-{today_str}.txt"
    )
    #insert a conditional check here to improve trade check if it can handle the liquidity build up
    # if the determined SL stays too far from what the account can handle on a determined risk percentage then pass on the trade, no use 
    #entering even if you are right because the liquidity grab will blow account
    if stop_loss is None or take_profit is None:
        print("⚠️ Could not determine SL/TP for limit order — skipping")
        return

    order_type = mt5.ORDER_TYPE_BUY_LIMIT if action == "buy" else mt5.ORDER_TYPE_SELL_LIMIT
    
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol_mt5,
        "volume": 0.01,
        "type": order_type,
        "price": limit_price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 10,
        "magic": 10001,
        "comment": "GhostOfTuring",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(request)
    print(f"📥 LIMIT {action.upper()} @ {limit_price} | SL: {stop_loss} | TP: {take_profit} — result:", result)


#Close Losing position
async def close_losing_positions(symbol):
    try:
        # Fetch all open positions
        positions = mt5.positions_get()
        if positions is None:
            print("No open positions found or failed to retrieve positions.")
            return
        
        for position in positions:
            symbol = position.symbol
            position_id = position.ticket
            profit = position.profit
            volume = position.volume
            
            """Stream of consciousness"""
            # Check if the position is in loss
            #this should be determined as profit based on liquidity pool, not a fixed amount, stay inbetween liquidity pool (between support and resistance to always secure the profits)
            #on every aggTrade stream and Snapshot stream ensure that the latest liquidity pool is captured ans used to determine the SL level
            #always stay at the back of the level to ensure that you survive
            if profit <= -0.70:
                print(f"Attempting to close losing position: {position_id} | Symbol: {symbol} | Profit: {profit} | Volume: {volume}")
                
                # Determine the closing order type
                close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                
                # Get the correct price for closing
                price = get_bid_price(symbol) if close_type == mt5.ORDER_TYPE_SELL else get_ask_price(symbol)
                
                if price is None:
                    print(f"Could not retrieve price for symbol {symbol}. Skipping position {position_id}.")
                    continue

                # Construct the close request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": volume,  # Use the exact volume of the position
                    "type": close_type,
                    "position": position_id,
                    "price": price,
                    "deviation":10,
                    "magic": 234000,
                    "comment": "Pos. Closed",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_RETURN,
                }

                # Send the close request
                result = mt5.order_send(request)
                if result is None:
                    print(f"Failed to send close request for position {position_id}.")
                    continue
                
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Failed to close position {position_id} | Retcode: {result.retcode}")
                else:
                    print(f"Position {position_id} closed successfully.")
    except Exception as e:
        print(f"Error in close_losing_positions: {e}")
    


# Function to close a trade that is in profit, secure all trades 
async def close_profitable_positions(symbol):
    try:
        # Fetch all open positions
        positions = mt5.positions_get()
        if positions is None:
            print("No open positions found or failed to retrieve positions.")
            return
        
        for position in positions:
            symbol = position.symbol
            position_id = position.ticket
            profit = position.profit
            volume = position.volume
            """Stream of consciousness"""
            # Check if the position is in profit
            #this should be determined as profit based on liquidity pool, not a fixed amount, stay inbetween liquidity pool (between support and resistance to always secure the profits)
            #on every aggTrade stream and Snapshot stream ensure that the latest liquidity pool is captured ans used to determine the profit level
            #stay at the back of the TP level to ensure that you always secure the profit level.
            if profit >= 0.30:
                print(f"Attempting to close profitable position: {position_id} | Symbol: {symbol} | Profit: {profit} | Volume: {volume}")
                
                # Determine the closing order type
                close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                
                # Get the correct price for closing
                price = get_bid_price(symbol) if close_type == mt5.ORDER_TYPE_SELL else get_ask_price(symbol)
                
                if price is None:
                    print(f"Could not retrieve price for symbol {symbol}. Skipping position {position_id}.")
                    continue

                # Construct the close request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": volume,  # Use the exact volume of the position
                    "type": close_type,
                    "position": position_id,
                    "price": price,
                    "deviation": 10,
                    "magic": 234000,
                    "comment": "Pos. Closed",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_RETURN,
                }



                # Send the close request
                result = mt5.order_send(request)
                if result is None:
                    print(f"Failed to send close request for position {position_id}.")
                    continue
                
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"Failed to close position {position_id} | Retcode: {result.retcode}")
                else:
                    print(f"Position {position_id} closed successfully.")
    except Exception as e:
        print(f"Error in close_profitable_positions: {e}")

#SL for open
async def adjust_sl_for_all_trades(symbol, sl_buffer_pips=5):
    """
    Adjust the Stop Loss (SL) for all trades dynamically based on their profit status.

    Args:
        symbol (str): The trading symbol (e.g., "XAUUSD").
        sl_buffer_pips (int): The buffer (in pips) to place the SL for profitable trades.

    Returns:
        None
    """
    try:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None or len(positions) == 0:
            print(f"No open positions for {symbol}.")
            return

        for position in positions:
            trade_type = position.type  # 0 = BUY, 1 = SELL
            current_price = get_ask_price(symbol) if trade_type == mt5.ORDER_TYPE_BUY else get_bid_price(symbol)
            tick_size = mt5.symbol_info(symbol).point
            sl_buffer = sl_buffer_pips * tick_size

            # Check if the trade is in profit
            if (trade_type == mt5.ORDER_TYPE_BUY and current_price > position.price_open) or \
               (trade_type == mt5.ORDER_TYPE_SELL and current_price < position.price_open):
                print(f"Position {position.ticket} is in profit. Adjusting SL.")

                # Calculate new SL for profitable trades
                new_sl = current_price - sl_buffer if trade_type == mt5.ORDER_TYPE_BUY else current_price + sl_buffer

                # Ensure SL doesn't move backward
                if (trade_type == mt5.ORDER_TYPE_BUY and new_sl > position.sl) or \
                   (trade_type == mt5.ORDER_TYPE_SELL and new_sl < position.sl):
                    # Send SL modification request
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": position.ticket,
                        "sl": round(new_sl, 5),
                        "tp": position.tp  # Keep the current TP unchanged
                    }
                    result = mt5.order_send(request)

                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"SL updated for profitable position {position.ticket}: New SL = {new_sl}")
                    else:
                        print(f"Failed to update SL for position {position.ticket}. Error: {result.retcode}")
                else:
                    print(f"New SL does not improve protection for position {position.ticket}. No change made.")

            else:
                print(f"Position {position.ticket} is not in profit. Adjusting SL to opening price.")

                # Adjust SL to the opening price for non-profitable trades
                new_sl = position.price_open
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": position.ticket,
                    "sl": round(new_sl, 5),
                    "tp": position.tp  # Keep the current TP unchanged
                }
                result = mt5.order_send(request)

                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"SL updated to opening price for position {position.ticket}: New SL = {new_sl}")
                else:
                    print(f"Failed to update SL for position {position.ticket}. Error: {result.retcode}")

    except Exception as e:
        print(f"Error adjusting SL for all trades: {e}")



# --- Trade Logging ---
async def log_trade_data(symbol):
    """Stream of consciousness"""
    #Log every trade placed
    #Log every modification done to trades

    """Log trade data for further analysis."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        print("No trades to log.")
        return

    trade_data = [{"symbol": pos.symbol, "volume": pos.volume, "price": pos.price_open} for pos in positions]
    trade_df = pd.DataFrame(trade_data)
    trade_df.to_csv("trade_log.csv", index=False)
    print("Trade data logged.")    

async def scale_lot_size(market_data):
    """Stream of consciousness"""
    #scale lot size should also feature these functionality
    # 1. be Kelly Criterion driven
    # 2. Scale lot size in such a way that the maximum losses should position be entered does not trigger margin call and does not exceed risk limit
    # 3. this should still return the lot size


    """Dynamically scale lot size based on market conditions."""
    volatility = market_data['volatility'].iloc[-1]
    lot_size = max(0.1, 1 / volatility)  # Example scaling
    print(f"Lot Size: {lot_size}")
    return lot_size

# --- Risk Management ---
async def manage_risk(lot_size, max_margin=0.1):
    """Stream of consciousness"""
    #Ideally this should still return a bool value, but it needs to perform extended operations
    #needs to check the total cummulative Losses of opened positiions at SL level if they do not exceed the risk percentage determined
    #should margin call of positions be reached

    """Ensure margin usage stays within limits."""
    account_info = mt5.account_info()
    if account_info is None:
        print("Account info unavailable.")
        return False

    margin_used = account_info.margin_used / account_info.balance
    print(f"Margin Used: {margin_used}")
    return margin_used < max_margin



#main execution engine
async def calculate_cancel_window(l2_path, ts_path, percentile=0.90, tolerance=1.0, retries=1000000):
    """
    Calculate cancel window by comparing L2 snapshot quantity reductions with T&S trade data.

    - If quantity drops at a price and is NOT matched in T&S within a window, it's a cancel.
    - Handles delayed or partial fills.
    - Retries on common issues.
    """

    for attempt in range(retries):
        try:
            print(f"Attempt {attempt + 1} — Loading L2 data...")
            async with aiofiles.open(l2_path, "r") as f:
                l2_lines = await f.readlines()

            print("Loading trade data (T&S)...")
            async with aiofiles.open(ts_path, "r") as f:
                ts_lines = await f.readlines()

            trades = []
            for line in ts_lines:
                if not line.strip():
                    continue
                try:
                    trade = json.loads(line)
                    trades.append({
                        "price": round(float(trade["price"]), 2),
                        "quantity": float(trade["quantity"]),
                        "timestamp": pd.to_datetime(trade["timestamp"])
                    })
                except json.JSONDecodeError as e:
                    print(f"Skipping malformed trade line: {e}")
                    continue

            ts_df = pd.DataFrame(trades)
            if ts_df.empty:
                raise ValueError("T&S data is empty.")

            ts_df.sort_values("timestamp", inplace=True)

            cancel_windows = []
            fill_windows =[]
            order_state = {}  # { "side-price": [quantity, placed_time] }
            current_price = get_mt5_price()
            for line in l2_lines:
                if not line.strip():
                    continue
                try:
                    snapshot = json.loads(line)
                    df = pd.DataFrame(snapshot)
                    if df.empty or not {"price", "quantity", "side", "timestamp"}.issubset(df.columns):
                        continue
                except json.JSONDecodeError as e:
                    print(f"Skipping malformed snapshot line: {e}")
                    continue

                timestamp = pd.to_datetime(df["timestamp"].iloc[0])

                for _, row in df.iterrows():
                    
                    price = round(float(row["price"]), 2)
                    qty = float(row["quantity"])
                    side = row["side"]
                    key = f"{side}-{price}"

                    if qty == 0:
                        continue  # skip empty quotes

                    if key in order_state:
                        prev_qty, placed_time = order_state[key]
                        if qty < prev_qty:
                            qty_diff = round(prev_qty - qty, 6)

                            # Match in T&S
                            matched = ts_df[
                                (ts_df["price"] == price) &
                                (abs(ts_df["quantity"] - qty_diff) <= 0.0001) &
                                (abs((ts_df["timestamp"] - timestamp).dt.total_seconds()) <= tolerance)
                            ]

                            if matched.empty:
                                cancel_time = (timestamp - placed_time).total_seconds()
                                cancel_windows.append(cancel_time)
                                print(f"❌ Canceled: {key} in {cancel_time:.3f}s")
                            else:
                                
                                fill_time = (timestamp - placed_time).total_seconds()
                                fill_windows.append(fill_time)
                                print(f"✅ Filled: {key} in {fill_time:.3f}s")
                                if side == "ask":
                                    stop_level = mt5.symbol_info(symbol_mt5).trade_stops_level
                                    point = mt5.symbol_info(symbol_mt5).point
                                    min_distance = stop_level * point
                                    
                                    if abs(current_price - price) < min_distance:
                                        print("📈 Buy market order placed")
                                        place_market_order("buy")

                                    elif price < current_price:
                                        if can_place_order(price, current_price, stop_level, point, "below"):
                                            print("📥 Buy limit placed")
                                            place_limit_order("buy", price)
                                        else:
                                            print("⚠️ Buy limit too close to market, order skipped")

                                    elif price > current_price:
                                        if can_place_order(price, current_price, stop_level, point, "above"):
                                            print("⏱️ Buy stop placed")
                                            place_stop_order("buy", price)
                                        else:
                                            print("⚠️ Buy stop too close to market, order skipped")
                                    else:
                                        print("Trade could not be place for some reason")

                                elif side == "bid":
                                    stop_level = mt5.symbol_info(symbol_mt5).trade_stops_level
                                    point = mt5.symbol_info(symbol_mt5).point
                                    min_distance = stop_level * point

                                    if abs(current_price - price) < min_distance:
                                        print("📉 Sell market order placed")
                                        place_market_order("sell")

                                    elif price > current_price:
                                        if can_place_order(price, current_price, stop_level, point, "above"):
                                            print("📥 Sell limit placed")
                                            place_limit_order("sell", price)
                                        else:
                                            print("⚠️ Sell limit too close to market, order skipped")

                                    elif price < current_price:
                                        if can_place_order(price, current_price, stop_level, point, "below"):
                                            print("⏱️ Sell stop placed")
                                            place_stop_order("sell", price)
                                        else:
                                            print("⚠️ Sell stop too close to market, order skipped")

                                    else:
                                        print("trade could not be placed for some reason")

                                    

                            order_state[key] = (qty, timestamp)
                        else:
                            # updated with same or higher quantity
                            order_state[key] = (qty, order_state[key][1])
                    else:
                        # new quote
                        order_state[key] = (qty, timestamp)

            if not cancel_windows:
                raise ValueError("No canceled orders detected.")
                
            if not fill_windows:
                raise ValueError("No filled orders detected.")

            cancel_result = pd.Series(cancel_windows).quantile(percentile) if cancel_windows else None
            fill_result = pd.Series(fill_windows).quantile(percentile) if fill_windows else None
            print(f"📉 Cancel window ({percentile*100:.0f}%): {cancel_result:.3f}s" if cancel_result else "")
            print(f"📈 Fill window ({percentile*100:.0f}%): {fill_result:.3f}s" if fill_result else "")
            return cancel_result

        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ Error: {e}")
            if attempt + 1 < retries:
                print("🔁 Retrying...")
                await asyncio.sleep(1)
            else:
                print("❌ Max retries reached.")
                return None
        except Exception as e:
            print("Unexpected error occurred:")
            traceback.print_exc()
            return None
        

#L2 and Time and sales data book analysis       
async def background_cancel_monitor():
    """Loop cancel window evaluation every N seconds"""
    while True:
        try:
            today_str = datetime.now().date().isoformat()
            cancel = await calculate_cancel_window(
                f"btcusdt-updates-{today_str}.txt",
                f"btcusdt-aggTrades-{today_str}.jsonl",
                percentile=0.90,
                tolerance=1.0
            )
            print("🧠 Cancel window:", cancel)
        except Exception as e:
            print("❗ Error in cancel window task:", e)
        await asyncio.sleep(10)  # Wait before re-evaluating


async def main():
    #initialize the binance orderflow class
    ob = orderflowBinance(pair="BTCUSDT")
    #start streaming order + trades in the background
    asyncio.create_task(ob.run_streams())
    
    
    #keep the event loop alive indefinitely
    while True:
        """Stream of consciousness"""
        #open trades
        risk = manage_risk(lot_size=0.01, max_margin=0.1)
        if risk == True:
            #Get Open positions
            positions = mt5.positions_get()
            #if position is found at the price then pass do not allow duplicate entires
            if positions in positions:
                pass
            else:
                #if position is not open already then go ahead and open new position
                await background_cancel_monitor()

                #check profitable position and close them (Max TP)
                await close_profitable_positions()

                #check losing positions and close them (Max SL)
                await close_losing_positions()

                #next is to trail TP and SL
                #if a position is in Profit check the next liquidity pools and modify the SL and TP
                if profitable: 
                    new_SL_TP = await calculate_sl_tp_from_snapshot()
                    #Get Open positions and modify SL_TP
                    positions = mt5.positions_get()
                    #Then set the new SLand TP for the old positions at liquidity pool
                
                #else postions are in losses then the next liquidity pool and modify SL and TP
                else: 
                    new_SL_TP = await calculate_sl_tp_from_snapshot()
                    #Get Open positions and modify SL_TP
                    positions = mt5.positions_get()
                    # Then set the new SL and TP for the old positions at liquidity pool                
        else:
            #if risk conditions are not met simply just close the positions based on the profit and loss status
            await close_losing_positions()

            await close_profitable_positions()

        await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(main())




