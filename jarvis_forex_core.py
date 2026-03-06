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
                # 08:00 - 16:00 UTC Only
                now = datetime.datetime.utcnow().hour
                if not (8 <= now <= 16): 
                    time.sleep(600); continue

                for symbol in CONFIG["SYMBOLS"]:
                    self.process_symbol(symbol)
                
                time.sleep(60)
            except Exception as e:
                logger.error(f"Grail Loop Error: {e}")
                time.sleep(10)

    def process_symbol(self, symbol):
        df = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=250)
        if df.empty or self.has_position(symbol): return

        # Cooldown: 1 trade per 12 hours per symbol to ensure high quality
        last_t = self.last_trade_time.get(symbol)
        if last_t and (datetime.datetime.now() - last_t).total_seconds() < 12 * 3600:
            return

        # Indicators
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        rsi = self.analyzer.get_rsi(df)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = mt5.symbol_info_tick(symbol).ask if last['close'] > last['ema200'] else mt5.symbol_info_tick(symbol).bid

        # --- HOLY GRAIL LOGIC ---
        # Long: Above EMA200 + Pullback to EMA20 + RSI < 40 (Exhaustion)
        if last['close'] > last['ema200'] and last['low'] <= last['ema20'] and rsi < 40:
            sl_pts = abs(price - last['ema200']) / mt5.symbol_info(symbol).point
            if sl_pts < 150: sl_pts = 150 # Safety min
            self.fire(symbol, mt5.ORDER_TYPE_BUY, price, sl_pts)

        # Short: Below EMA200 + Pullback to EMA20 + RSI > 60 (Exhaustion)
        elif last['close'] < last['ema200'] and last['high'] >= last['ema20'] and rsi > 60:
            sl_pts = abs(price - last['ema200']) / mt5.symbol_info(symbol).point
            if sl_pts < 150: sl_pts = 150 # Safety min
            self.fire(symbol, mt5.ORDER_TYPE_SELL, price, sl_pts)

    def fire(self, symbol, type, price, sl_pts):
        point = mt5.symbol_info(symbol).point
        lot = self.risk.calculate_lot_size(symbol, sl_pts)
        
        sl = price - (sl_pts * point) if type == mt5.ORDER_TYPE_BUY else price + (sl_pts * point)
        tp = price + (sl_pts * CONFIG["RR"] * point) if type == mt5.ORDER_TYPE_BUY else price - (sl_pts * CONFIG["RR"] * point)
        
        logger.info(f"GRAIL SIGNAL: {symbol} | RR 1:3 | SL Pts: {sl_pts}")
        if self.mt5.send_order(symbol, type, lot, price, sl, tp, comment="JarvisGrail_1K"):
            self.last_trade_time[symbol] = datetime.datetime.now()

    def has_position(self, symbol):
        return len(mt5.positions_get(symbol=symbol)) > 0

if __name__ == "__main__":
    JarvisHolyGrail().run()
