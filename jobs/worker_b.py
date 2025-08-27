
import asyncio
from utils import cache, config_worker

# Try to import your existing components; they may not all exist
try:
    from utils import signal_evaluator
except Exception:
    signal_evaluator = None

try:
    from strategies import rsi_macd_strategy
except Exception:
    rsi_macd_strategy = None

try:
    from utils import risk_manager, order_manager
except Exception:
    risk_manager = None
    order_manager = None

async def evaluate_and_trade():
    """Example decision loop: read latest cached data, evaluate, maybe place order."""
    ticker = cache.get_latest("ticker") or {}
    funding = cache.get_latest("funding") or {}

    # 1) Build a context/dataset for your strategy
    ctx = {"ticker": ticker, "funding": funding}

    # 2) Evaluate signal (prefer your existing evaluator/strategy if available)
    signal = None
    if signal_evaluator and hasattr(signal_evaluator, "evaluate"):
        try:
            signal = signal_evaluator.evaluate(ctx)
        except Exception as e:
            signal = {"error": str(e)}
    elif rsi_macd_strategy and hasattr(rsi_macd_strategy, "evaluate"):
        try:
            signal = rsi_macd_strategy.evaluate(ctx)
        except Exception as e:
            signal = {"error": str(e)}
    else:
        # minimal placeholder: do nothing
        signal = {"action": "HOLD", "reason": "no strategy available"}

    # 3) Risk checks + order
    if risk_manager and order_manager and isinstance(signal, dict):
        try:
            ok = True
            if hasattr(risk_manager, "check"):
                ok = risk_manager.check(signal, ctx)
            if ok and signal.get("action") in ("BUY","SELL"):
                if hasattr(order_manager, "place_order"):
                    await maybe_async(order_manager.place_order, signal)
        except Exception:
            pass

async def maybe_async(fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res

async def run_forever():
    while True:
        await evaluate_and_trade()
        await asyncio.sleep(config_worker.WORKER_B_INTERVAL)
