
# Which tasks Worker A should run and their intervals (seconds)
WORKER_A_TASKS = [
    {"name": "ticker", "interval": 10},       # Binance ticker (prices) every 10s
    {"name": "funding", "interval": 60},      # Funding rates every 60s (if available)
    # {"name": "oi", "interval": 120},        # Open interest example
]

# Which markets/symbols to watch (examples; adjust in your repo)
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

# Worker B decision loop frequency
WORKER_B_INTERVAL = 5  # seconds

# General cache setup
CACHE_TTL_SECONDS = {
    "ticker": 20,
    "funding": 180,
    "oi": 180
}

CACHE_MAX_ROWS_PER_KEY = 100
