# -*- coding: utf-8 -*-
"""
Created on Tue May  6 18:53:46 2025

@author: Kaizer
"""
import json
import aiofiles
import asyncio
import pandas as pd
from datetime import datetime
from websockets import connect
import httpx
import bisect
import nest_asyncio
nest_asyncio.apply()
import asyncio
from websockets import connect
import aiofiles
import sys
import json
import pandas as pd
import httpx
import requests
from datetime import datetime
from statsmodels.tsa.stattools import acf


class orderflowBinance:
    def __init__(self, pair="BTCUSDT"):
        self.pair = pair.upper()
        self.pair_lower = self.pair.lower()
        self.today = datetime.now().date()
        self.websocket_url = f"wss://stream.binance.com:9443/ws/{self.pair_lower}@depth@100ms"
        self.websocket_trade_url = f"wss://stream.binance.com:9443/ws/{self.pair_lower}@aggTrade"
        self.rest_url = "https://api.binance.com/api/v3/depth"

    async def download_orderbook(self):
        # Initial REST snapshot (not required for stream trading, but useful for reference)
        params = {
            "symbol": self.pair,
            "limit": 5000,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(self.rest_url, params=params)
            snapshot = response.json()
            timestamp = datetime.utcnow().isoformat()
            bid_levels = pd.DataFrame(snapshot["bids"], columns=["price", "quantity"], dtype=float)
            bid_levels["side"] = "bid"
            ask_levels = pd.DataFrame(snapshot["asks"], columns=["price", "quantity"], dtype=float)
            ask_levels["side"] = "ask"
            bid_ask_levels = pd.concat([bid_levels, ask_levels])
            bid_ask_levels["timestamp"] = timestamp

            # Convert the whole snapshot to a JSON array string
            bid_ask_json = bid_ask_levels.to_dict(orient="records")
            async with aiofiles.open(f"{self.pair_lower}-snapshots-{self.today}.txt", mode="a") as f:
                await f.write(json.dumps(bid_ask_json) + "\n")

        # Start streaming order book deltas
        async with connect(self.websocket_url) as websocket:
            while True:
                try:
                    timestamp = datetime.utcnow().isoformat()
                    data = await websocket.recv()
                    snapshot = json.loads(data)

                    bid_levels = pd.DataFrame(snapshot["b"], columns=["price", "quantity"], dtype=float)
                    bid_levels["side"] = "bid"
                    ask_levels = pd.DataFrame(snapshot["a"], columns=["price", "quantity"], dtype=float)
                    ask_levels["side"] = "ask"
                    bid_ask_levels = pd.concat([bid_levels, ask_levels])
                    bid_ask_levels["timestamp"] = timestamp

                    bid_ask_json = bid_ask_levels.to_dict(orient="records")

                    async with aiofiles.open(f"{self.pair_lower}-updates-{self.today}.txt", mode="a") as f:
                        await f.write(json.dumps(bid_ask_json) + "\n")

                except Exception as e:
                    print("❗ Order book error:", e)

    async def stream_trades(self):
        """Stream Binance aggTrades (T&S) and write 1 JSON per line."""
        async with connect(self.websocket_trade_url) as websocket:
            while True:
                try:
                    msg = await websocket.recv()
                    trade = json.loads(msg)
                    trade_data = {
                        "price": float(trade["p"]),
                        "quantity": float(trade["q"]),
                        "timestamp": datetime.utcfromtimestamp(trade["T"] / 1000).isoformat(),
                        "is_buyer_maker": trade["m"]
                    }

                    async with aiofiles.open(f"{self.pair_lower}-aggTrades-{self.today}.jsonl", mode="a") as f:
                        await f.write(json.dumps(trade_data) + "\n")
                except Exception as e:
                    print("❗ Trade stream error:", e)




    async def calculate_threshold(self, filename, method='percentile', quantile=0.95, z_score=2):
        relative_distances = []

        async with aiofiles.open(filename, mode='r') as f:
            async for line in f:
                try:
                    records = json.loads(line)
                    df = pd.DataFrame(records)
                    if df.empty or not {'price', 'quantity', 'side'}.issubset(df.columns):
                        continue
                    best_bid = df[df['side'] == 'bid']['price'].max()
                    best_ask = df[df['side'] == 'ask']['price'].min()
                    if pd.isna(best_bid) or pd.isna(best_ask):
                        continue
                    mid_price = (best_bid + best_ask) / 2
                    df['relative_distance'] = abs(df['price'] - mid_price) / mid_price
                    relative_distances.extend(df['relative_distance'].tolist())
                except Exception as e:
                    print(f"Skipping line due to error: {e}")
                    continue

        if not relative_distances:
            print("No valid data found in file.")
            return None

        distances = pd.Series(relative_distances)
        if method == 'percentile':
            return distances.quantile(quantile)
        elif method == 'zscore':
            return distances.mean() + z_score * distances.std()
        else:
            raise ValueError("Invalid method. Use 'percentile' or 'zscore'.")



    async def calculate_cancel_window(self, l2_path, ts_path, percentile=0.90, tolerance=1.0):
        """Enhanced cancel window using quantity reduction and T&S matching."""
        
        
        """ 🧠 Logic Breakdown:
           Snapshots: Every time the L2 data updates, it records the quantity per price level and side.

        Reductions: If the quantity at a price level decreases, it's flagged.

        Matches: If the reduced amount matches a T&S trade (price + quantity match within 1 second), it’s treated as filled. If not, it's considered canceled.

        Cancel Window: Calculated as the difference between when the order first appeared and when the quantity dropped without execution."""
    
        print("Reading snapshots...")
        async with aiofiles.open(l2_path, "r") as f:
            l2_lines = await f.readlines()
    
        print("Reading trades...")
        async with aiofiles.open(ts_path, "r") as f:
            ts_lines = await f.readlines()
    
        # Preprocess T&S data
        trades = []
        for line in ts_lines:
            trade = json.loads(line)
            trades.append({
                "price": round(float(trade["price"]), 2),
                "quantity": float(trade["quantity"]),
                "timestamp": pd.to_datetime(trade["timestamp"])
                })
            ts_df = pd.DataFrame(trades).sort_values("timestamp").reset_index(drop=True)

        # Store price-level states over time
        order_state = {}  # {price_level: [quantity, timestamp]}
        cancel_windows = []

        for line in l2_lines:
            try:
                snapshot = json.loads(line)
                df = pd.DataFrame(snapshot)
                if df.empty or not {"price", "quantity", "side", "timestamp"}.issubset(df.columns):
                    continue

                timestamp = pd.to_datetime(df["timestamp"].iloc[0])
                for _, row in df.iterrows():
                    price = round(float(row["price"]), 2)
                    qty = float(row["quantity"])
                    side = row["side"]
                    key = f"{side}-{price}"

                    if qty == 0:
                        continue

                    # If this price level already exists, check for reduction
                    if key in order_state:
                        prev_qty, placed_time = order_state[key]
                        if qty < prev_qty:
                            # Quantity reduced = possible fill or cancel
                            qty_diff = round(prev_qty - qty, 6)

                            # Match in T&S within ±tolerance
                            matched_trade = ts_df[
                                (ts_df["price"] == price) &
                                (abs(ts_df["quantity"] - qty_diff) <= 0.0001) &
                                (abs((ts_df["timestamp"] - timestamp).dt.total_seconds()) <= tolerance)
                                ]

                            if matched_trade.empty:
                                # Not filled = canceled
                                cancel_time = (timestamp - placed_time).total_seconds()
                                cancel_windows.append(cancel_time)
                                # Update to reflect reduced quote
                                order_state[key] = (qty, timestamp)
                            else:
                                # Order was likely executed; update to reflect new qty
                                    order_state[key] = (qty, timestamp)
                        else:
                            # Quantity increased or unchanged; update
                            order_state[key] = (qty, order_state[key][1])
                    else:
                        # New price level
                        order_state[key] = (qty, timestamp)

            except Exception as e:
                print(f"Skipping line due to error: {e}")
                continue

        if not cancel_windows:
            raise ValueError("No canceled orders detected.")

        result = pd.Series(cancel_windows).quantile(percentile)
        print(f"Cancel window ({percentile*100}%): {result:.3f}s")
        return result

    async def calculate_min_order_size(self, file_path, method="percentile", value=0.10):
        async with aiofiles.open(file_path, mode="r") as f:
            content = await f.read()
        try:
            df = pd.read_json(content)
        except:
            df = pd.read_json(content, lines=True)

        if "quantity" not in df.columns:
            raise ValueError("Missing 'quantity' column in data.")
        sizes = df["quantity"].astype(float)
        sizes = sizes[sizes > 0]

        if sizes.empty:
            raise ValueError("No valid quantity data found.")

        if method == "percentile":
            return sizes.quantile(value)
        elif method == "mean_std":
            return max(0, sizes.mean() - value * sizes.std())
        elif method == "mode_threshold":
            return sizes.mode().iloc[0]
        else:
            raise ValueError("Invalid method. Choose 'percentile', 'mean_std', or 'mode_threshold'.")

    async def calculate_optimal_history_window(self, file_path, feature="mid_price", threshold=0.05, max_lag=300):
        async with aiofiles.open(file_path, mode="r") as f:
            content = await f.read()
        df = pd.read_json(content)
        if feature not in df.columns:
            raise ValueError(f"Feature '{feature}' not in data.")

        series = df[feature].dropna()
        autocorr_values = acf(series, nlags=max_lag, fft=True)

        for lag, value in enumerate(autocorr_values):
            if abs(value) < threshold:
                return lag
        return max_lag
    
    
    
    async def run_streams(self):
        """Run both order book and trade streams in parallel."""
        asyncio.create_task(self.download_orderbook())
        asyncio.create_task(self.stream_trades())
        
        await asyncio.sleep(2)
