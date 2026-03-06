import os
import sys
import time
import logging
import datetime
from mt5_interface import MT5Interface
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
import MetaTrader5 as mt5

# --- JARVIS HOLY GRAIL SNIPER (1k Bank Optimized) ---
CONFIG = {
    "SYMBOLS": ["GBPUSD", "EURUSD"],
    "RISK_PER_TRADE_PCT": 0.01, # 1% for 1k bank recovery
    "RR": 3.0,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183,
    "MT5_PASSWORD": "UiS!6mBq",
    "MT5_SERVER": "MetaQuotes-Demo",
    "LOG_FILE": "jarvis_holy_grail.log"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.FileHandler(CONFIG["LOG_FILE"]), logging.StreamHandler()]
)
logger = logging.getLogger("JARVIS_GRAIL")

class JarvisHolyGrail:
    def __init__(self):
        self.mt5 = MT5Interface(CONFIG)
        self.risk = RiskManager(CONFIG)
        self.analyzer = MarketAnalyzer(CONFIG)
        self.last_trade_time = {}

    def bootstrap(self):
        if not self.mt5.connect(): return False
        logger.info("--- JARVIS HOLY GRAIL ACTIVE: 1K BANK PROTECTION MODE ---")
        return True

    def run(self):
        if not self.bootstrap(): return
        while True:
            try:
                now_utc = datetime.datetime.utcnow()
                
                # 1. FRIDAY KILL-SWITCH: No trading after Friday 16:00 UTC
                if now_utc.weekday() == 4 and now_utc.hour >= 16:
                    logger.info("Friday Kill-Switch active. Hibernating for the weekend.")
                    time.sleep(3600); continue

                # 2. SESSION FILTER: 08:00 - 16:00 UTC Only
                if not (8 <= now_utc.hour <= 16): 
                    time.sleep(600); continue

                # 3. GLOBAL CORRELATION LOCK: Only 1 trade total for 1k bank protection
                if self.has_any_position():
                    time.sleep(60); continue

                for symbol in CONFIG["SYMBOLS"]:
                    self.process_symbol(symbol)
                
                time.sleep(60)
            except Exception as e:
                logger.error(f"Grail Loop Error: {e}")
                time.sleep(10)

    def process_symbol(self, symbol):
        df = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=250)
        if df.empty: return

        # 4. ATR VOLATILITY GUARD: Avoid news spikes (Max 2x Average)
        atr_series = self.analyzer.calculate_atr_series(df)
        current_atr = atr_series.iloc[-1]
        mean_atr = atr_series.tail(14).mean()
        if current_atr > (mean_atr * 2.0):
            logger.warning(f"SPIKE PROTECTION: High Volatility on {symbol} (ATR: {current_atr:.5f} > Buffer). Entry Blocked.")
            return

        # Indicators
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        rsi = self.analyzer.get_rsi(df)
        
        last = df.iloc[-1]
        price = mt5.symbol_info_tick(symbol).ask if last['close'] > last['ema200'] else mt5.symbol_info_tick(symbol).bid

        # --- HOLY GRAIL LOGIC ---
        if last['close'] > last['ema200'] and last['low'] <= last['ema20'] and rsi < 40:
            sl_pts = abs(price - last['ema200']) / mt5.symbol_info(symbol).point
            if sl_pts < 150: sl_pts = 150 # Safety min
            self.fire(symbol, mt5.ORDER_TYPE_BUY, price, sl_pts)

        elif last['close'] < last['ema200'] and last['high'] >= last['ema20'] and rsi > 60:
            sl_pts = abs(price - last['ema200']) / mt5.symbol_info(symbol).point
            if sl_pts < 150: sl_pts = 150 # Safety min
            self.fire(symbol, mt5.ORDER_TYPE_SELL, price, sl_pts)

    def has_any_position(self):
        return len(mt5.positions_get()) > 0

    def fire(self, symbol, type, price, sl_pts):
        point = mt5.symbol_info(symbol).point
        lot = self.risk.calculate_lot_size(symbol, sl_pts)
        
        sl = price - (sl_pts * point) if type == mt5.ORDER_TYPE_BUY else price + (sl_pts * point)
        tp = price + (sl_pts * CONFIG["RR"] * point) if type == mt5.ORDER_TYPE_BUY else price - (sl_pts * CONFIG["RR"] * point)
        
        logger.info(f"GRAIL SIGNAL: {symbol} | RR 1:3 | SL Pts: {sl_pts}")
        self.mt5.send_order(symbol, type, lot, price, sl, tp, comment="JarvisGrail_1K")

    def has_position(self, symbol):
        return len(mt5.positions_get(symbol=symbol)) > 0

if __name__ == "__main__":
    JarvisHolyGrail().run()
