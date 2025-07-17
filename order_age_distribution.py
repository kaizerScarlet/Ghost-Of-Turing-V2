# -*- coding: utf-8 -*-
"""
Created on Tue May 13 01:27:44 2025

@author: Kaizer


This part of the system handles how long orders have been siting on the L2 book
1. if they sit for long what does that mean?
2. if they sit for a short period what does it mean?
3. if they they are immediately filled then what?



"""
import nest_asyncio
nest_asyncio.apply()
import asyncio
import json
import nest_asyncio
import numpy as np
import aiofiles
from websockets import connect
from datetime import datetime
from collections import defaultdict

nest_asyncio.apply()

# --- Config ---
PAIR = "btcusdt"
WS_URL = f"wss://stream.binance.com:9443/ws/{PAIR}@depth@100ms"
DISTRIBUTION_FILE = f"order_age_distribution_{datetime.utcnow().date()}.json"

# Store order timestamps
order_ages = {
    "bids": defaultdict(float),  # price -> insertion time
    "asks": defaultdict(float)
}

lifespan_data = {
    "bids": [],
    "asks": []
}

# --- Utilities ---
def utc_ts():
    return datetime.utcnow().timestamp()

async def log_lifespans_to_file():
    async with aiofiles.open(DISTRIBUTION_FILE, "w") as f:
        await f.write(json.dumps({
            "timestamp": utc_ts(),
            "bids": lifespan_data["bids"],
            "asks": lifespan_data["asks"]
        }, indent=2))
    print(f"[✓] Lifespan distribution saved to {DISTRIBUTION_FILE}")

# --- Handler ---
async def process_depth(data):
    timestamp = utc_ts()
    for side_key, updates in [("bids", data.get("b", [])), ("asks", data.get("a", []))]:
        side_orders = order_ages[side_key]
        for price_str, qty_str in updates:
            price = float(price_str)
            qty = float(qty_str)

            if qty == 0:  # Order cancelled or removed
                if price in side_orders:
                    age = timestamp - side_orders.pop(price)
                    lifespan_data[side_key].append(age)
            else:  # Order added or updated
                if price not in side_orders:
                    side_orders[price] = timestamp  # mark time of appearance

# --- Stream Listener ---
async def listen_and_track_order_age():
    print("[*] Tracking order age from Binance depth stream...")
    async with connect(WS_URL) as ws:
        try:
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                await process_depth(data)
        except Exception as e:
            print(f"[!] Error: {e}")
        finally:
            await log_lifespans_to_file()

# --- Entry ---
if __name__ == "__main__":
    asyncio.run(listen_and_track_order_age())
