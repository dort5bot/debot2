
import asyncio
from typing import Dict, Any
from utils import cache
from utils import config_worker

# Try to import your existing API utilities; fail gracefully if absent
try:
    from utils import binance_api
except Exception as e:
    binance_api = None

try:
    from utils import coinglass_utils
except Exception as e:
    coinglass_utils = None

async def _task_ticker():
    if not binance_api:
        return
    # Expecting your repo to have an async or sync function. Try both.
    data: Dict[str, Any] = {}
    try:
        # prefer async if present
        if hasattr(binance_api, "async_get_tickers"):
            data = await binance_api.async_get_tickers(symbols=config_worker.SYMBOLS)
        elif hasattr(binance_api, "get_tickers"):
            data = binance_api.get_tickers(symbols=config_worker.SYMBOLS)
        elif hasattr(binance_api, "get_price"):
            # fallback single-symbol; build dict
            data = {sym: binance_api.get_price(sym) for sym in config_worker.SYMBOLS}
    except Exception as e:
        data = {"error": str(e)}
    cache.put("ticker", data, ttl=config_worker.CACHE_TTL_SECONDS.get("ticker", 20),
              max_rows=config_worker.CACHE_MAX_ROWS_PER_KEY)

async def _task_funding():
    if not coinglass_utils:
        return
    try:
        if hasattr(coinglass_utils, "get_funding_rates_async"):
            data = await coinglass_utils.get_funding_rates_async(symbols=config_worker.SYMBOLS)
        else:
            data = coinglass_utils.get_funding_rates(symbols=config_worker.SYMBOLS)  # may not exist; adapt in repo
    except Exception as e:
        data = {"error": str(e)}
    cache.put("funding", data, ttl=config_worker.CACHE_TTL_SECONDS.get("funding", 180),
              max_rows=config_worker.CACHE_MAX_ROWS_PER_KEY)

TASK_MAP = {
    "ticker": _task_ticker,
    "funding": _task_funding,
    # "oi": _task_oi,  # add similarly
}

async def run_once():
    # Run all configured tasks once (in parallel)
    coros = []
    for t in config_worker.WORKER_A_TASKS:
        fn = TASK_MAP.get(t["name"])
        if not fn:
            continue
        coros.append(fn())
    if coros:
        await asyncio.gather(*coros)

async def run_forever():
    # naive scheduler: run tasks at their own intervals
    last = {t["name"]: 0 for t in config_worker.WORKER_A_TASKS}
    while True:
        now = asyncio.get_event_loop().time()
        runs = []
        for t in config_worker.WORKER_A_TASKS:
            name, interval = t["name"], t["interval"]
            if now - last[name] >= interval:
                last[name] = now
                fn = TASK_MAP.get(name)
                if fn:
                    runs.append(fn())
        if runs:
            await asyncio.gather(*runs)
        await asyncio.sleep(1)
