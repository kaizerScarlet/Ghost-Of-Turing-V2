# -*- coding: utf-8 -*-
"""
Created on Tue May 13 01:24:54 2025

@author: Kaizer

This part will monitor trades that are slowly fed from L2 to the Time and sales
This will check the upper and lower limits of these trades

"""
import nest_asyncio
nest_asyncio.apply()
import asyncio
import json
import nest_asyncio
from websockets import connect
from collections import defaultdict, deque
from datetime import datetime
import aiofiles

nest_asyncio.apply()

# --- Configuration ---
PAIR = "btcusdt"
DEPTH_STREAM = f"wss://stream.binance.com:9443/ws/{PAIR}@depth@100ms"
LAYER_THRESHOLD = 10.0       # minimum quantity to consider a "layer"
LAYER_CANCEL_WINDOW = 2.0    # seconds to cancel and be considered "layering"
PATTERN_WINDOW = 10          # seconds to group suspicious activity
MIN_LAYER_EVENTS = 3         # number of cancellations within window to trigger alert

# --- Internal State ---
order_book = {"bids": {}, "asks": {}}
layer_timestamps = defaultdict(lambda: defaultdict(float))  # [side][price] = time
layer_events = deque(maxlen=1000)  # (timestamp, side, price, qty)

# --- Utilities ---
def utc_ts():
    return datetime.utcnow().timestamp()

def now_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

async def log_layering_event(event):
    async with aiofiles.open(f"layering_events_{now_str()}.jsonl", mode="a") as f:
        await f.write(json.dumps(event) + "\n")

async def detect_layering_pattern():
    current_time = utc_ts()
    recent = [e for e in layer_events if current_time - e["time"] <= PATTERN_WINDOW]
    if len(recent) >= MIN_LAYER_EVENTS:
        print(f"[!] ALERT: Potential order layering detected ({len(recent)} in {PATTERN_WINDOW}s)")
        await log_layering_event({
            "alert_time": current_time,
            "event": "layering_pattern",
            "count": len(recent),
            "window": PATTERN_WINDOW,
            "details": recent
        })

# --- Handler ---
async def handle_depth(data):
    timestamp = utc_ts()
    for side in ["b", "a"]:  # bids, asks
        updates = data.get(side, [])
        side_str = "bids" if side == "b" else "asks"
        for price_str, qty_str in updates:
            price = float(price_str)
            qty = float(qty_str)
            book = order_book[side_str]

            if qty == 0:  # Cancellation
                if price in book:
                    book.pop(price)
                    placed_time = layer_timestamps[side_str].pop(price, None)
                    if placed_time and (timestamp - placed_time) <= LAYER_CANCEL_WINDOW:
                        print(f"[x] Suspicious cancel at {side_str[:-1]} {price} (quick removal)")
                        event = {
                            "time": timestamp,
                            "price": price,
                            "side": side_str,
                            "latency": round((timestamp - placed_time) * 1000, 2),
                            "event": "layering_cancel"
                        }
                        layer_events.append(event)
                        await log_layering_event(event)
                        await detect_layering_pattern()
            else:  # New quote
                book[price] = qty
                if qty >= LAYER_THRESHOLD:
                    layer_timestamps[side_str][price] = timestamp

# --- Listener ---
async def listen_depth():
    async with connect(DEPTH_STREAM) as ws:
        print("[*] Listening for depth updates...")
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            await handle_depth(data)

# --- Entry Point ---
async def main():
    await listen_depth()

if __name__ == "__main__":
    asyncio.run(main())
