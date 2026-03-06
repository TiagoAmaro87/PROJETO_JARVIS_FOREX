import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime

class MarketAnalyzer:
    def __init__(self, config):
        self.config = config

    def calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(period).mean().iloc[-1]

    def find_order_blocks(self, df, n=100):
        """Identify significant Order Blocks (candle with extreme volume followed by reversal)."""
        df['vol_ma'] = df['tick_volume'].rolling(20).mean()
        obs = []
        # Look back through the provided window
        for i in range(len(df) - n, len(df) - 2):
            if i < 0: continue
            if df['tick_volume'].iloc[i] > df['vol_ma'].iloc[i] * 1.1:
                # Bullish OB: Large volume bearish candle followed by higher close
                if df['close'].iloc[i] < df['open'].iloc[i] and df['close'].iloc[i+1:i+3].max() > df['high'].iloc[i]:
                    obs.append({
                        'type': 'bullish', 
                        'top': df['high'].iloc[i], 
                        'bottom': df['low'].iloc[i], 
                        'time': df['time'].iloc[i]
                    })
                # Bearish OB: Large volume bullish candle followed by lower close
                elif df['close'].iloc[i] > df['open'].iloc[i] and df['close'].iloc[i+1:i+3].min() < df['low'].iloc[i]:
                    obs.append({
                        'type': 'bearish', 
                        'top': df['high'].iloc[i], 
                        'bottom': df['low'].iloc[i], 
                        'time': df['time'].iloc[i]
                    })
        return obs

    def find_fvg(self, df, n=50):
        """Identify Fair Value Gaps (FVG)."""
        fvgs = []
        for i in range(len(df) - n, len(df) - 2):
            # Bullish FVG (Gap between candle 1 high and candle 3 low)
            if df['low'].iloc[i+2] > df['high'].iloc[i]:
                fvgs.append({'type': 'bullish', 'top': df['low'].iloc[i+2], 'bottom': df['high'].iloc[i]})
            # Bearish FVG (Gap between candle 1 low and candle 3 high)
            elif df['high'].iloc[i+2] < df['low'].iloc[i]:
                fvgs.append({'type': 'bearish', 'top': df['low'].iloc[i], 'bottom': df['high'].iloc[i+2]})
        return fvgs

    def get_z_score(self, df, period=20):
        """Statistical exhaustion detection."""
        prices = df['close']
        ma = prices.rolling(period).mean()
        std = prices.rolling(period).std()
        z_score = (prices.iloc[-1] - ma.iloc[-1]) / std.iloc[-1] if std.iloc[-1] != 0 else 0
        return z_score

    def get_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs)).iloc[-1]

    def get_bollinger_bands(self, df, period=20, std_dev=2):
        ma = df['close'].rolling(period).mean()
        std = df['close'].rolling(period).std()
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        return upper.iloc[-1], lower.iloc[-1]

    def get_trend_ema(self, df):
        ema_fast = df['close'].ewm(span=20).mean().iloc[-1]
        ema_slow = df['close'].ewm(span=50).mean().iloc[-1]
        if ema_fast > ema_slow: return "bullish"
        if ema_fast < ema_slow: return "bearish"
        return "neutral"

    def detect_mss(self, df_m5):
        """Detect Market Structure Shift (MSS) on M5."""
        if len(df_m5) < 10: return False
        
        last_high = df_m5['high'].iloc[-10:-2].max()
        last_low = df_m5['low'].iloc[-10:-2].min()
        
        current_close = df_m5['close'].iloc[-1]
        
        if current_close > last_high: return 'bullish'
        if current_close < last_low: return 'bearish'
        return None

    def is_trading_session(self):
        """Restricts trading to London and NY high-liquidity windows."""
        utc_hour = datetime.utcnow().hour
        # 07:00 to 20:00 UTC covers the main session overlaps
        return 7 <= utc_hour <= 20

    def is_adr_exhausted(self, df_d1, current_price):
        """Prevents trading if daily range is already 85% covered."""
        if len(df_d1) < 5: return False
        range_mean = (df_d1['high'].tail(5) - df_d1['low'].tail(5)).mean()
        daily_open = df_d1['open'].iloc[-1]
        dist = abs(current_price - daily_open)
        return dist > (range_mean * 0.85)

    def get_dxy_trend(self, df_dxy):
        """Analyze Dollar Index trend to filter USD-based trades."""
        if df_dxy.empty: return "neutral"
        # Using simple SMA cross context for DXY
        sma = df_dxy['close'].rolling(20).mean().iloc[-1]
        current = df_dxy['close'].iloc[-1]
        if current > sma: return "bullish"
        if current < sma: return "bearish"
        return "neutral"
