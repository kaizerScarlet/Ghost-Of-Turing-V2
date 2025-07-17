

"""
@author: Kaizer
# -*- coding: utf-8 -*-
iteration looks good, off to studying for supps the following still need to be implemented
SL setting based on ATR.
TP setting based on ATR.

Do All the functions work? Unit testing and integration testing. TP setting, limit #. of trades based on how risk we are
taking sl is your guide.
"""
"Ultimate Trading System with AI, Order Flow, Risk Management, Dynamic Adjustments,"
"Spoofing Detection, and Trade Logging."


import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from statsmodels.tsa.arima.model import ARIMA
from sklearn.cluster import KMeans
import pandas as pd
import statistics
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from statsmodels.tsa.arima.model import ARIMA
from collections import deque

        
import MetaTrader5 as mt5
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import MetaTrader5 as mt5
import pandas as pd

# --- Initialization ---
try:
    if not mt5.initialize():  
        raise Exception("Failed to initialize MetaTrader 5.")
except Exception as e:
    print(f"Initialization error: {e}")
    quit()

# Account details
account_id = 5033349986  # Replace with your MT5 account ID
password = "8kEoXb@d"  # Replace with your MT5 account password
server = "MetaQuotes-Demo"

try:
    if not mt5.login(account_id, password=password, server=server):
        raise Exception("Login failed.")
    print("Connected to MetaTrader 5.")
except Exception as e:
    print(f"Login error: {e}")
    quit()

symbol = "XAUUSD"  # Replace with your desired trading symbol

# --- Helper Functions ---
def get_bid_price(symbol):
    """Fetch the current bid price for the given symbol."""
    tick = mt5.symbol_info_tick(symbol)
    return tick.bid if tick else None

def get_ask_price(symbol):
    """Fetch the current ask price for the given symbol."""
    tick = mt5.symbol_info_tick(symbol)
    return tick.ask if tick else None

def fetch_market_data(symbol, num_bars=60):
    """Retrieve historical market data with calculated spread."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, num_bars)
    if rates is None or len(rates) == 0:
        print("Failed to fetch market data.")
        return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['volatility'] = df['high'] - df['low']

    # Dynamically fetch the current spread using symbol_info_tick
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        df['ask'] = tick.ask
        df['bid'] = tick.bid
        df['spread'] = tick.ask - tick.bid
    else:
        df['ask'] = df['close']
        df['bid'] = df['close']
        df['spread'] = 0

    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df.dropna()

# --- Order Flow Analysis ---

def analyze_order_flow(symbol, size_threshold=None, distance_threshold_pips=10):
    """Classify institutional/retail volume and calculate imbalances."""
    """
    Features Explained
    Dynamic Size Threshold
    Uses mean + 2 standard deviations to adapt to current market conditions. Override with a fixed value via size_threshold.

    Order Book Depth
    Flags orders placed >10 pips away from the best price as institutional (adjustable via distance_threshold_pips).

    Granular Metrics
    Returns institutional/retail buy/sell volumes and imbalances for nuanced analysis.

    Pip Calculation
    Adjust pip_factor based on the symbol’s decimal places (e.g., 100 for JPY pairs).
    """
    # Fetch market book data
    market_book = mt5.market_book_get(symbol)
    if market_book is None or market_book.empty:
        print("Order flow data unavailable.")
        return None

    try:
        # Extract best bid/ask
        bids = [entry.price for entry in market_book if entry.type == 1]
        asks = [entry.price for entry in market_book if entry.type == 0]
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None

        # Calculate dynamic size threshold if not provided
        volumes = [entry.volume for entry in market_book]
        avg_volume = statistics.mean(volumes) if volumes else 0
        std_volume = statistics.stdev(volumes) if len(volumes) > 1 else 0
        size_threshold = size_threshold or (avg_volume + 2 * std_volume)

        # Classify institutional/retail
        inst_buy, inst_sell, retail_buy, retail_sell = 0, 0, 0, 0

        for entry in market_book:
            # Calculate distance from best price (in pips)
            pip_factor = 100  # for XAUUSD
            if entry.type == 1 and best_bid:
                distance = (best_bid - entry.price) * pip_factor
            elif entry.type == 0 and best_ask:
                distance = (entry.price - best_ask) * pip_factor
            else:
                distance = 0

            # Classify based on size and distance
            if entry.volume > size_threshold or distance > distance_threshold_pips:
                if entry.type == 1:
                    inst_buy += entry.volume
                else:
                    inst_sell += entry.volume
            else:
                if entry.type == 1:
                    retail_buy += entry.volume
                else:
                    retail_sell += entry.volume

        # Calculate imbalances
        inst_imbalance = inst_buy - inst_sell
        retail_imbalance = retail_buy - retail_sell

        # Print metrics
        print(f"Institutional Imbalance: {inst_imbalance}")
        print(f"Retail Imbalance: {retail_imbalance}")

        return {
            "institutional": {"buy": inst_buy, "sell": inst_sell},
            "retail": {"buy": retail_buy, "sell": retail_sell}
        }

    except Exception as e:
        print(f"Error processing data: {e}")
        return None

# --- Trend Analysis ---



closing_prices = []

# =============================================================================
# def identify_trend(symbol):
#     """
#     Identify the market trend and execute trading logic based on the trend.
#     """
#     global closing_prices
#
#     def update_prices():
#         """
#         Update the deque with the latest closing price.
#         """
#         market_data = fetch_market_data(symbol, num_bars=1)
#         if market_data is not None and not market_data.empty:
#             latest_price = market_data['close'].iloc[-1]
#             closing_prices.append(latest_price)
#             return latest_price
#         else:
#             print(f"Failed to fetch the latest market data for {symbol}.")
#             return None
#
#     try:
#         # Pre-fill the deque with historical data if not already filled
#         if len(closing_prices) < 20:
#             print("Pre-filling closing prices...")
#             market_data = fetch_market_data(symbol, num_bars=20)
#             if market_data is not None and not market_data.empty:
#                 closing_prices.extend(market_data['close'].tolist())
#             else:
#                 print("Failed to pre-fill closing prices. Returning neutral trend.")
#                 return 0  # Neutral trend
#
#         # Update the deque with the latest price
#         last_closing_price = update_prices()
#         if last_closing_price is None:
#             return 0  # Neutral trend
#
#         # Ensure there are enough data points for ARIMA
#         if len(closing_prices) < 20:
#             print("Not enough data points for ARIMA. Returning neutral trend.")
#             return 0  # Neutral trend
#
#         # Convert deque to a pandas Series
#         prices = pd.Series(closing_prices)
#
#         # Ensure variability in the prices
#         if prices.std() == 0:
#             print("Data is constant within the past 20 minutes. Returning neutral trend.")
#             return 0  # Neutral trend
#
#         # Fit ARIMA model
#         model = ARIMA(prices, order=(1, 1, 0))
#         model_fit = model.fit()
#
#         # Forecast the next price
#         forecasted_price = model_fit.forecast(steps=1)[0]
#
#         print(f"Forecasted Price: {forecasted_price}, Last Price: {last_closing_price}")
#
#         # Determine trend direction
#         if forecasted_price > last_closing_price:
#             return forecasted_price  # Upward trend
#         elif forecasted_price < last_closing_price:
#             return forecasted_price  # Downward trend
#         else:
#             return 0  # Neutral trend
#
#     except Exception as e:
#         print(f"Error in identify_trend function: {e}")
#         return 0  # Neutral trend
# =============================================================================



# --- Dynamic Adjustments ---
def adjust_sl_tp(trend, last_closing_price):
    """Dynamically adjust SL and TP levels based on trend and price."""
    #use calculate ATR if provided, else default to 5
    data = get_last_20_minutes_close(symbol)
    df = pd.DataFrame(data)
    
    if not all(col in df.columns for col in ['high','low','close']):
        raise ValueError("DataFrame must contain high, low, and close")
    #calculate ATR
    df['tr'] = df [['high', 'low','close']].apply(
        lambda row: max (row['high'] - row['low'],
                         abs(row['high'] - row['close']),
                         abs(row['low'] - row['close'])),
        axis=1
        )
    #calculate ATR
    df['atr'] = df['tr'].rolling(window=1440).mean()
    
    atr = df['atr'].iloc[-1]
    #set sl and tp based on ATR
    offset = atr if atr is not None else 5
    if trend > last_closing_price:  # Buy Condition
        sl = get_ask_price(symbol) - offset  # SL below the price
        tp = get_ask_price(symbol) + offset  # TP above the price
    elif trend < last_closing_price:  # Sell Condition
        tp = get_bid_price(symbol) - offset  # SL above the price
        sl = get_bid_price(symbol) + offset  # TP below the price
    else:
        print("No adjustment")
        return None  # Return None if no adjustment is needed
    print(f"Adjusted TP: {tp}, SL: {sl}")
    return {"tp": tp, "sl": sl}

#SL for open
def adjust_sl_for_all_trades(symbol, sl_buffer_pips=5):
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

def scale_lot_size(market_data):
    """Dynamically scale lot size based on market conditions."""
    volatility = market_data['volatility'].iloc[-1]
    lot_size = max(0.1, 1 / volatility)  # Example scaling
    print(f"Lot Size: {lot_size}")
    return lot_size

# --- Risk Management ---
def manage_risk(lot_size, max_margin=0.7):
    """Ensure margin usage stays within limits."""
    account_info = mt5.account_info()
    if account_info is None:
        print("Account info unavailable.")
        return False

    margin_used = account_info.margin_used / account_info.balance
    print(f"Margin Used: {margin_used}")
    return margin_used < max_margin

# --- AI Model ---
def train_ai_model(features, target):
    """Train AI model on market data."""
    #features = market_data[["close", "volatility", "spread"]]
    #target = market_data["target"]
    model = RandomForestClassifier()
    #model.fit(features)
    model.fit(features, target)
    return model

def evaluate_model(model, features, target):
    """Evaluate model accuracy."""
    accuracy = model.score(features, target)
    print(f"Model Accuracy: {accuracy}")
    return accuracy

def get_spread(symbol):
    """Calculate the spread for the symbol."""
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"Could not retrieve tick data for symbol {symbol}")
        return tick.ask - tick.bid
    except Exception as e:
        print(f"Error in get_spread: {e}")
        return None
# --- Spoofing Detection ---
def detect_spoofing(order_flow):
    """Detect spoofing using clustering."""
    data = [[order_flow['buy_volume']], [order_flow['sell_volume']]]
    kmeans = KMeans(n_clusters=2)
    kmeans.fit(data)
    labels = kmeans.labels_

    if len(set(labels)) == 1:  # Potential spoofing
        print("Spoofing detected!")

# --- Trade Execution ---
def place_trade(symbol, order_type, price, lot, sl_pips, tp_pips):
    """Place a trade with specified parameters."""
    try:
        # Fetch the symbol's minimum lot size, step, and price increment from MetaTrader 5
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"Could not retrieve symbol information for {symbol}")
       
        # Validate lot size (ensure it complies with the broker's rules)
        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max
        lot_step = symbol_info.volume_step
        if lot < min_lot or lot > max_lot or lot % lot_step != 0:
            # Round lot size to the nearest valid step size
            lot = round(lot / lot_step) * lot_step
            if lot < min_lot:
                lot = min_lot
            elif lot > max_lot:
                lot = max_lot
            print(f"Adjusted lot size to {lot} (within allowed range).")

        # Validate stop loss and take profit (ensure they are a reasonable distance from current price)
        tick_size = symbol_info.point
        spread = get_spread(symbol)
       
        # Ensure SL and TP are at least 10 pips away from current price (this can vary based on the broker)
        if(order_type == mt5.ORDER_TYPE_BUY):
            #sl_tp/10 so that it scales properly
            sl = price - (sl_pips/10) * tick_size
            tp = price + (tp_pips/10) * tick_size
        
        if(order_type == mt5.ORDER_TYPE_SELL):
            sl = price + (sl_pips/10) * tick_size
            tp = price - (sl_pips/10) * tick_size
        
       
        # Ensure SL and TP distance is within acceptable range (avoid market execution issues)
        if abs(sl - price) < 10 * tick_size or abs(tp - price) < 10 * tick_size:
            raise ValueError("Stop Loss or Take Profit is too close to the current price.")

        # Create trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "deviation": 20,  # Allow a deviation of 20 pips
            "magic": 234000,
            "comment": "JOAT",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        # Send the trade request
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise Exception(f"Trade failed with code {result.retcode}, message: {result.comment}")
       
        print(f"Trade opened successfully: {result}")
        return result

    except Exception as e:
        print(f"Error in open_trade: {e}")
        return None
       
def prepare_ai_features(data):
    """Prepare features and target for AI model training."""
    features = data[["close", "high", "low", "tick_volume"]]
    target = (data["close"].shift(-1) > data["close"]).astype(int)
    scaler = MinMaxScaler()
    features_scaled = scaler.fit_transform(features)
    return features_scaled, target

# --- Trade Logging ---
def log_trade_data(symbol):
    """Log trade data for further analysis."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        print("No trades to log.")
        return

    trade_data = [{"symbol": pos.symbol, "volume": pos.volume, "price": pos.price_open} for pos in positions]
    trade_df = pd.DataFrame(trade_data)
    trade_df.to_csv("trade_log.csv", index=False)
    print("Trade data logged.")
   
def update_prices():
    """Update the deque with the latest closing price."""
    closing_prices = []
    market_data = fetch_market_data(symbol, num_bars=2)
    if market_data is not None and not market_data.empty:
        latest_price = market_data['close'].iloc[-1]
     
       
        closing_prices.append(latest_price)
        return latest_price
    else:
         print(f"Failed to fetch the latest market data for {symbol}.")
    return None

def get_last_20_minutes_close(symbol):
    # Define the timeframe and the number of minutes to look back
    timeframe = mt5.TIMEFRAME_M1
    minutes_to_look_back = 60

    # Calculate the time 'minutes_to_look_back' minutes ago from now
    utc_to = datetime.now()
    utc_from = utc_to - timedelta(minutes=minutes_to_look_back)

    # Retrieve the rates
    rates = mt5.copy_rates_range(symbol, timeframe, utc_from, utc_to)

    # Check if data was retrieved successfully
    if rates is None or len(rates) == 0:
        print("No data retrieved, error code =", mt5.last_error())
        return None

    # Create a DataFrame from the retrieved data
    rates_frame = pd.DataFrame(rates)

    # Convert the time in seconds into the datetime format
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')

    # Extract the closing prices
    close_prices = rates_frame['close'].tolist()

    return close_prices

# --- Main Loop ---
def main():
    last_price = update_prices()
    print("Lastest close price" , last_price)
    last_twenty_closing_prices = get_last_20_minutes_close(symbol)
    print(last_twenty_closing_prices)
   
    df = pd.DataFrame(last_twenty_closing_prices, columns=['Close'])
    # Define the model
    # Define the model (order=(1, 0, 1))                                                                
    model = ARIMA(df['Close'], order=(1, 0, 1))

    # Fit the model with the correct number of starting parameters (3 values)
    model_fit = model.fit()  # 3 parameters for AR, MA, and constant

    # Forecast the next value
    forecast = model_fit.forecast(steps=1)
   
    trend = forecast.iloc[0]
    print("Identifying market trend")
    print(forecast.iloc[0])
   
    # Extract the predicted value
   #predicted_price = forecast[0]
   ##rint(f"Predicted 21st closing price: {predicted_price}")


   

   

   


    while True:        
         try:
             # Fetch initial market data
             market_data = fetch_market_data(symbol)
             if market_data is None:
                 mt5.shutdown()
                 quit()
             df = pd.DataFrame(last_twenty_closing_prices, columns=['Close'])
              # Define the model
              # Define the model (order=(1, 0, 1))
             model = ARIMA(df['Close'], order=(1, 0, 1))

              # Fit the model with the correct number of starting parameters (3 values)
             model_fit = model.fit()  # 3 parameters for AR, MA, and constant

              # Forecast the next value
             forecast = model_fit.forecast(steps=1)
             
             trend = forecast.iloc[0]
             print("Identifying market trend")
             print(forecast.iloc[0])
              # Prepare features and target
             features, target = prepare_ai_features(market_data)
             print("Preparing AI features and target")                                      
             
             # Initialize the Random Forest model
             model = train_ai_model(features, target)
             print("Starting Random walk")
             # Evaluate model accuracy
             accuracy = evaluate_model(model, features, target)
             print("Evaluating Model Accuracy")
 
             # Fetch order book and analyze
             order_book = analyze_order_flow(symbol)
             print("Fetching Order book")
             
           
 
             
             lot_size = round(scale_lot_size(market_data),  2)
             print("adjusting lot size")
 
             # Risk Management
             #if not manage_risk(lot_size):                                                                                                                                                                                              
              # print("Risk limits exceeded. Skipping trade placement.")
                   #continue
 
             # Place Trades
             # Place Trades
             last_closing_price = market_data['close'].iloc[-1]
 
             if (trend > last_closing_price ) and (accuracy > 0.8) and (order_book >= 0.1):
                 print("Uptrend or Neutral detected: Entering BUY")
                 price = get_ask_price(symbol)
                 sl_tp = adjust_sl_tp(trend, last_closing_price)
                 place_trade(symbol, mt5.ORDER_TYPE_BUY, price, lot_size, sl_tp['sl'], sl_tp['tp'])
                 #adjust_sl_for_all_trades(symbol)
                 log_trade_data(symbol)
             elif (trend < last_closing_price ) and (accuracy > 0.8) and (order_book <= -0.1):
                 print("Downtrend or Neutral detected: Entering SELL")
                 price = get_bid_price(symbol)
                 
                 place_trade(symbol, mt5.ORDER_TYPE_SELL, price, lot_size, sl_tp['sl'], sl_tp['tp'])
               
                 #adjust_sl_for_all_trades(symbol)
                 log_trade_data(symbol)
             else:
                 print("No significant change detected: No Trade")
                 print(f"Trend: {trend}, Last Price: {last_closing_price}, Order Flow: {order_book}, Accuracy: {accuracy}")
                 # Retrieve all open positions
        
 
   
 
             # Sleep for the next iteration
             time.sleep(1)
 
         except Exception as e:
             print(f"Error in main loop: {e}")
        
        
# =============================================================================
               

if __name__ == "__main__":
    main()