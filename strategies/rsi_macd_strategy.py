# strategies/rsi_macd_strategy.py
# ♦️ Pluggable strategy wrapper (RSI + MACD)

from collections import deque
from utils import ta_utils  # artık ta_utils kullanılıyor

class RSI_MACD_Strategy:
    """
    RSI + MACD tabanlı örnek strateji.
    Kapanış fiyatlarını besle, basit BUY/SELL sinyali döner.
    """

    def __init__(self, symbol: str, lookback: int = 500, rsi_period: int = 14):
        self.symbol = symbol
        self.closes = deque(maxlen=lookback)
        self.rsi_period = rsi_period

    def on_new_close(self, close: float):
        """Yeni kapanış fiyatı ekle ve sinyal üret."""
        self.closes.append(close)
        if len(self.closes) < self.rsi_period + 1:
            return None

        # closes → DataFrame'e çevir
        import pandas as pd
        df = pd.DataFrame({"close": list(self.closes)})

        # RSI
        rsi_val = ta_utils.rsi(df, period=self.rsi_period).iloc[-1]

        # MACD
        macd_line, signal_line, hist = ta_utils.macd(df)
        macd_h = hist.iloc[-1]

        if pd.isna(rsi_val) or pd.isna(macd_h):
            return None

        # Basit kurallar
        if rsi_val < 30 and macd_h > 0:
            return {
                "type": "BUY",
                "strength": 0.6,
                "payload": {"rsi": rsi_val, "macd_h": macd_h, "price": close}
            }
        elif rsi_val > 70 and macd_h < 0:
            return {
                "type": "SELL",
                "strength": 0.6,
                "payload": {"rsi": rsi_val, "macd_h": macd_h, "price": close}
            }

        return None
