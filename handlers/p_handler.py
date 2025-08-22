# handlers/p_handler.py
import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from utils.binance_api import get_binance_api

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

COMMAND = "P"
HELP = "/P [coin...] — Trend coinleri gösterir.\n/P d — Düşüşteki coinler."

# -------------------------------------------------
# Ticker verisi çekme
# -------------------------------------------------
async def fetch_ticker_data(symbols=None, descending=True):
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

    # İlk 20 sonucu döndür
    return usdt_pairs[:20]

# -------------------------------------------------
# Rapor formatlama
# -------------------------------------------------
def format_report(data, title):
    #lines = [f"📈 {title}"]
    lines = [f"📈 {title}", "⚡Coin | Değişim | Hacim | Fiyat"]  # Kolon başlıkları eklendi
    for i, coin in enumerate(data, start=1):
        symbol = coin["symbol"].replace("USDT", "")
        change = float(coin["priceChangePercent"])
        vol_usd = float(coin["quoteVolume"])
        price = float(coin["lastPrice"])

        # Hacim M veya B formatı
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

    if args and args[0].lower() == "d":
        data = await fetch_ticker_data(descending=False)
        title = "Düşüş Trendindeki Coinler"
    elif args:
        data = await fetch_ticker_data(symbols=args)
        title = "Seçili Coinler"
    else:
        data = await fetch_ticker_data()
        title = "Trend Coinler"

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
