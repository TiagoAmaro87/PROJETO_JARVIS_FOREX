import os
import sys
import time
import logging
import datetime
from mt5_interface import MT5Interface
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
import MetaTrader5 as mt5

# --- JARVIS GEKKO ALPHA CONFIG ---
CONFIG = {
    "SYMBOLS": ["GBPUSD", "EURUSD"], # Only the profitable core
    "TF": mt5.TIMEFRAME_M15,
    "RISK_PER_TRADE_PCT": 0.01, # 1% risk
    "RR": 2.5,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183,
    "MT5_PASSWORD": "UiS!6mBq",
    "MT5_SERVER": "MetaQuotes-Demo",
    "LOG_FILE": "jarvis_gekko.log"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.FileHandler(CONFIG["LOG_FILE"]), logging.StreamHandler()]
)
logger = logging.getLogger("JARVIS_GEKKO")

class JarvisGekko:
    def __init__(self):
        self.mt5 = MT5Interface(CONFIG)
        self.risk = RiskManager(CONFIG)

    def bootstrap(self):
        if not self.mt5.connect(): return False
        logger.info("--- JARVIS GEKKO ALPHA LIVE: TREND SURFING MODE ---")
        return True

    def run(self):
        if not self.bootstrap(): return
        while True:
            try:
                # Session Check
                now = datetime.datetime.utcnow().hour
                if not (7 <= now <= 18): 
                    time.sleep(600); continue

                for symbol in CONFIG["SYMBOLS"]:
                    self.process_symbol(symbol)
                
                self.manage_active_positions()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Gekko Loop Error: {e}")
                time.sleep(10)

    def process_symbol(self, symbol):
        df = self.mt5.get_rates(symbol, CONFIG["TF"], n=250)
        if df.empty: return

        # Indicators
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask
        
        # Avoid duplicate trades on same symbol
        if self.has_position(symbol): return

        # --- TREND GEKKO LOGIC ---
        # 1. Bullish: Above EMA200 + Touch EMA20 + Close back above EMA20
        if last['close'] > last['ema200']:
            if prev['low'] <= prev['ema20'] and last['close'] > last['ema20']:
                sl = last['low'] - (5 * mt5.symbol_info(symbol).point * 10)
                tp = last['close'] + (last['close'] - sl) * CONFIG["RR"]
                self.fire_order(symbol, mt5.ORDER_TYPE_BUY, price, sl, tp)

        # 2. Bearish: Below EMA200 + Touch EMA20 + Close back below EMA20
        elif last['close'] < last['ema200']:
            if prev['high'] >= prev['ema20'] and last['close'] < last['ema20']:
                sl = last['high'] + (5 * mt5.symbol_info(symbol).point * 10)
                tp = last['close'] - (sl - last['close']) * CONFIG["RR"]
                self.fire_order(symbol, mt5.ORDER_TYPE_SELL, price, sl, tp)

    def fire_order(self, symbol, type, price, sl, tp):
        point = mt5.symbol_info(symbol).point
        sl_points = abs(price - sl) / point
        lot = self.risk.calculate_lot_size(symbol, sl_points)
        
        logger.info(f"GEKKO SIGNAL: {symbol} | Type: {type} | SL: {sl} | TP: {tp}")
        self.mt5.send_order(symbol, type, lot, price, sl, tp, comment="JarvisGekko_V1")

    def has_position(self, symbol):
        positions = mt5.positions_get(symbol=symbol)
        return len(positions) > 0

    def manage_active_positions(self):
        # Auto Break-Even after 1:1 RR
        positions = mt5.positions_get()
        for pos in positions:
            if pos.comment != "JarvisGekko_V1": continue
            
            point = mt5.symbol_info(pos.symbol).point
            entry = pos.price_open
            current = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
            
            pnl_points = abs(current - entry) / point
            sl_dist = abs(entry - pos.sl) / point if pos.sl else 100
            
            # If 1:1 reached, move to BE
            if pnl_points >= sl_dist:
                if pos.type == 0 and pos.sl < entry: # Buy
                    mt5.TradeRequest(action=mt5.TRADE_ACTION_SLTP, position=pos.ticket, sl=entry + 10*point, tp=pos.tp)
                elif pos.type == 1 and pos.sl > entry: # Sell
                    mt5.TradeRequest(action=mt5.TRADE_ACTION_SLTP, position=pos.ticket, sl=entry - 10*point, tp=pos.tp)

if __name__ == "__main__":
    JarvisGekko().run()
