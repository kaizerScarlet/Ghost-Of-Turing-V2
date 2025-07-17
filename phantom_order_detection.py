# -*- coding: utf-8 -*-
"""
Created on Tue May 13 01:30:55 2025

@author: Kaizer
"""
import nest_asyncio
nest_asyncio.apply()
import asyncio
import json
from datetime import datetime
import aiofiles

phantom_orders = []

DISTANCE_THRESHOLD = 0.005  # 0.5% from mid
MIN_LARGE_ORDER = 10  # Adjust based on typical size

async def detect_imbalance_no_intent(mid, price, qty, side, timestamp, canceled=False):
    global phantom_orders

    # Calculate distance from mid-price
    distance = abs(price - mid) / mid

    if distance > DISTANCE_THRESHOLD and qty >= MIN_LARGE_ORDER:
        if not canceled:
            # Track large, far-from-price passive order
            phantom_orders.append({
                "side": side,
                "price": price,
                "qty": qty,
                "placed_time": timestamp,
                "touched": False
            })
        else:
            # Cancellation: Check if it was likely a phantom order
            for order in phantom_orders:
                if (order["side"] == side and 
                    abs(order["price"] - price) / price < 0.0001 and 
                    not order["touched"]):
                    lifetime = timestamp - order["placed_time"]
                    print(f"Phantom order cancelled: {side} {qty} @ {price}, age {lifetime:.3f}s")
                    await log_phantom_order(order, timestamp, lifetime)
                    phantom_orders.remove(order)

async def log_phantom_order(order, canceled_time, lifetime):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    log_line = json.dumps({
        "time": canceled_time,
        "side": order["side"],
        "price": order["price"],
        "qty": order["qty"],
        "lifetime": lifetime,
        "event": "phantom_order"
    })
    async with aiofiles.open(f"phantom_orders_{today}.jsonl", mode="a") as f:
        await f.write(log_line + "\n")

# Example simulation to test this logic
async def simulate_phantom_order_scenario():
    mid = 100.0
    timestamp = datetime.utcnow().timestamp()

    # Step 1: Large passive order far from mid
    await detect_imbalance_no_intent(mid, 105.5, 20, "ask", timestamp)
    
    # Step 2: Time passes (simulate)
    await asyncio.sleep(1.5)
    new_time = datetime.utcnow().timestamp()

    # Step 3: Order canceled before price moved near
    await detect_imbalance_no_intent(mid, 105.5, 0, "ask", new_time, canceled=True)

if __name__ == "__main__":
    asyncio.run(simulate_phantom_order_scenario())
