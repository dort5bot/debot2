# handlers/p_handler.py
#- 	/p →CONFIG.SCAN_SYMBOLS default
#- 	/P n → sayı girilirse limit = n oluyor.
#- 	/P d → düşenler.
#- 	/P coin1 coin2... → manuel seçili coinler.


import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from utils.binance_api import get_binance_api
from utils.config import CONFIG

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

COMMAND = "P"
HELP = (
    "/P → ENV'deki SCAN_SYMBOLS listesi\n"
    "/P n → En çok yükselen n coin (varsayılan 20)\n"
    "/P d → En çok düşen 20 coin\n"
    "/P coin1 coin2 ... → Belirtilen coin(ler)"
)

# -------------------------------------------------
# Ticker verisi çekme
# -------------------------------------------------
async def fetch_ticker_data(symbols=None, descending=True, limit=20):
    api = get_binance_api()
    data = await api.get_all_24h_tickers()
    if not data:
        return []

    # Sadece USDT pariteleri
    usdt_pairs = [d for d in data if d["symbol"].endswith("USDT")]

    # İstenen coinler varsa filtrele
    if symbols:
        wanted = {s.upper() + "USDT" for s in symbols}
        usdt_pairs = [d for d in usdt_pairs if d["symbol"] in wanted]

    # Yüzdelik değişime göre sırala
    usdt_pairs.sort(key=lambda x: float(x["priceChangePercent"]), reverse=descending)

    # İlk n sonucu döndür
    return usdt_pairs[:limit]

# -------------------------------------------------
# Rapor formatlama
# -------------------------------------------------
def format_report(data, title):
    lines = [f"📈 {title}", "⚡Coin | Değişim | Hacim | Fiyat"]
    for i, coin in enumerate(data, start=1):
        symbol = coin["symbol"].replace("USDT", "")
        change = float(coin["priceChangePercent"])
        vol_usd = float(coin["quoteVolume"])
        price = float(coin["lastPrice"])

        # Hacim formatı
        if vol_usd >= 1_000_000_000:
            vol_fmt = f"${vol_usd/1_000_000_000:.1f}B"
        else:
            vol_fmt = f"${vol_usd/1_000_000:.1f}M"

        lines.append(f"{i}. {symbol}: {change:.2f}% | {vol_fmt} | {price}")
    return "\n".join(lines)

# -------------------------------------------------
# Telegram handler
# -------------------------------------------------
async def p_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    title = ""
    data = []

    if not args:  
        # Varsayılan: ENV’deki SCAN_SYMBOLS
        data = await fetch_ticker_data(symbols=[s.replace("USDT", "") for s in CONFIG.SCAN_SYMBOLS])
        title = "SCAN_SYMBOLS Listesi"

    elif args[0].lower() == "d":
        data = await fetch_ticker_data(descending=False, limit=20)
        title = "Düşüş Trendindeki Coinler"

    elif args[0].isdigit():
        limit = int(args[0])
        data = await fetch_ticker_data(limit=limit)
        title = f"En Çok Yükselen {limit} Coin"

    else:
        data = await fetch_ticker_data(symbols=args)
        title = "Seçili Coinler"

    if not data:
        await update.message.reply_text("Veri alınamadı.")
        return

    report = format_report(data, title)
    await update.message.reply_text(report)

# -------------------------------------------------
# Plugin loader entry
# -------------------------------------------------
def register(application):
    application.add_handler(CommandHandler(COMMAND, p_handler))
    LOG.info("P handler registered.")
