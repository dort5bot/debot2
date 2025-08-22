# main.py — Modern & Stabil Telegram Trading Bot Entrypoint
# - Temiz event loop yaşam döngüsü (asyncio.run + manual PTB lifecycle)
# - Arka plan görevleri için düzenli başlatma/durdurma
# - Kapanışta cancel + await (Task was destroyed... hatası yok)
# - Plugin/handler loader uyumlu
# - Keep-alive web server ayrı thread'de
# - Tüm parametreler (STREAM_SYMBOLS, STREAM_INTERVAL, PAPER_MODE, EVALUATOR_WINDOW, EVALUATOR_THRESHOLD) config üzerinden okunuyor.
# - ImportError veya eski değişken eksiklikleri ortadan kalktı.
# - .env dosyası ile kolayca değerleri değiştirebilirsin.
# - tüm STREAM_*, PAPER_MODE, EVALUATOR_* sabitlerini tamamen CONFIG üzerinden okuyan sürümü

import asyncio
import os
import signal
import logging
from typing import Dict

from telegram.ext import ApplicationBuilder

from keep_alive import keep_alive
from utils.db import init_db
from utils.monitoring import configure_logging
from utils.config import CONFIG
from utils.handler_loader import load_handlers
from utils.binance_api import BinanceClient
from utils.stream_manager import StreamManager
from utils.order_manager import OrderManager
from strategies.rsi_macd_strategy import RSI_MACD_Strategy

# -------------------------------
# Global logging
configure_logging(logging.INFO)
LOG = logging.getLogger("main")

# -------------------------------
# Helpers: stream list
def build_stream_list(symbols, interval):
    return [f"{s.lower()}@kline_{interval}" for s in symbols] + [f"{s.lower()}@ticker" for s in symbols]

# -------------------------------
# Main async entry
async def async_main():
    LOG.info("Booting bot...")
    init_db()

    token = CONFIG.TELEGRAM.BOT_TOKEN
    if not token:
        LOG.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    # PTB Application (manual lifecycle; run_polling kullanılmıyor)
    app = ApplicationBuilder().token(token).build()

    # Keep-alive web server (thread)
    keep_alive()

    loop = asyncio.get_running_loop()

    # --- Core services created inside running loop (loop uyumu için) ---
    bin_client = BinanceClient()
    stream_mgr = StreamManager(bin_client, loop=loop)
    order_manager = OrderManager(paper_mode=CONFIG.BOT.PAPER_MODE)

    # SignalEvaluator: loop uyumu için burada oluştur
    from utils.signal_evaluator import SignalEvaluator

    async def decision_cb(decision: Dict):
        # Order routing burada
        return await order_manager.process_decision(decision)

    # Config üzerinden değerler
    evaluator = SignalEvaluator(
        decision_callback=decision_cb,
        loop=loop,
        window_seconds=CONFIG.BOT.EVALUATOR_WINDOW,
        threshold=CONFIG.BOT.EVALUATOR_THRESHOLD,
    )

    # Strategies & data queue
    strategies: Dict[str, RSI_MACD_Strategy] = {
        sym: RSI_MACD_Strategy(sym) for sym in CONFIG.BINANCE.TOP_SYMBOLS_FOR_IO
    }
    kline_queue: asyncio.Queue = asyncio.Queue()

    # Bridge: WS mesaj yönlendirici
    async def bridge(msg):
        from handlers import funding_handler, ticker_handler
        try:
            data = msg.get("data") if isinstance(msg, dict) else msg
            if isinstance(data, dict) and "k" in data:
                await kline_queue.put(data)
            else:
                await funding_handler.handle_funding_data(data)
                await ticker_handler.handle_ticker_data(data)
        except Exception:
            LOG.exception("bridge error")

    # Kline processor
    async def kline_processor():
        from handlers import signal_handler
        while True:
            data = await kline_queue.get()
            try:
                k = data.get("k", {})
                # Sadece kapanan mumlar
                if not k.get("x"):
                    continue
                close_price = float(k["c"])
                symbol = data.get("s")
                strat = strategies.get(symbol)
                if strat:
                    sig = strat.on_new_close(close_price)
                    if sig:
                        await signal_handler.publish_signal(
                            "rsi_macd",
                            symbol,
                            sig["type"],
                            strength=sig["strength"],
                            payload=sig["payload"],
                        )
            except asyncio.CancelledError:
                # graceful exit
                raise
            except Exception:
                LOG.exception("kline_processor error")
            finally:
                kline_queue.task_done()

    # Handlers yükle ve evaluator'ü enjekte et
    from handlers import signal_handler
    signal_handler.set_evaluator(evaluator)
    load_handlers(app)

    # --- Start background services ---
    background_tasks = []

    # 1) Evaluator loop
    evaluator.start()

    # 2) Streams
    streams = build_stream_list(CONFIG.BINANCE.TOP_SYMBOLS_FOR_IO, CONFIG.BINANCE.STREAM_INTERVAL)
    stream_mgr.start_combined_groups(streams, bridge)

    # 3) Periodic funding poller
    stream_mgr.start_periodic_funding_poll(
        CONFIG.BINANCE.TOP_SYMBOLS_FOR_IO,
        interval_sec=60,
        callback=lambda data: asyncio.create_task(
            __import__("handlers").funding_handler.handle_funding_data(data)
        ),
    )

    # 4) Kline processor task
    kline_task = asyncio.create_task(kline_processor(), name="kline_processor")
    background_tasks.append(kline_task)

    LOG.info(
        "Services started. PAPER_MODE=%s | Streams=%s",
        CONFIG.BOT.PAPER_MODE,
        ", ".join(CONFIG.BINANCE.TOP_SYMBOLS_FOR_IO),
    )

    # --- Graceful shutdown mechanics ---
    stop_event = asyncio.Event()

    def _request_shutdown(signame: str):
        LOG.warning("Signal received: %s — shutting down...", signame)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig.name)
        except NotImplementedError:
            # Windows uyumluluk
            signal.signal(sig, lambda *_: _request_shutdown(sig.name))

    # --- PTB manual lifecycle ---
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    LOG.info("Telegram polling started.")

    # Wait until stop requested
    await stop_event.wait()

    LOG.info("Stopping Telegram polling...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()

    # --- Stop background services ---
    LOG.info("Stopping background services...")
    evaluator.stop()
    stream_mgr.cancel_all()
    for t in background_tasks:
        t.cancel()

    # Drain queue fast (optional)
    try:
        while not kline_queue.empty():
            kline_queue.get_nowait()
            kline_queue.task_done()
    except Exception:
        pass

    # Await cancellations
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        LOG.info("Awaiting %d pending tasks...", len(pending))
        await asyncio.gather(*pending, return_exceptions=True)

    LOG.info("Shutdown complete. Bye.")

# -------------------------------
if __name__ == "__main__":
    asyncio.run(async_main())
