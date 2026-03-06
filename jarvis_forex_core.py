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
        start_balance = self.mt5.get_account_info().balance
        
        while True:
            try:
                acc = self.mt5.get_account_info()
                now_utc = datetime.datetime.utcnow()
                daily_pnl = acc.equity - start_balance
                
                # --- VISUAL DASHBOARD ---
                print("\n" + "="*45)
                print(f" JARVIS sniper - STATUS: {'LIVE' if 8 <= now_utc.hour <= 16 else 'SLEEPING'}")
                print(f" CAPITAL: ${acc.equity:,.2f} | DAILY PnL: ${daily_pnl:>+7.2f}")
                print(f" PST LOCK: {'ACTIVE' if self.has_any_position() else 'READY'}")
                print(f" TIME: {now_utc.strftime('%H:%M:%S UTC')} | DAY: {now_utc.strftime('%A')}")
                print("="*45)

                # 1. FRIDAY KILL-SWITCH
                if now_utc.weekday() == 4 and now_utc.hour >= 16:
                    time.sleep(3600); continue

                # 2. PEAK SESSION: 08:00 - 16:00 UTC
                if not (8 <= now_utc.hour <= 16): 
                    time.sleep(600); continue

                # 3. GLOBAL CORRELATION LOCK
                if self.has_any_position():
                    time.sleep(60); continue

                for symbol in CONFIG["SYMBOLS"]:
                    self.process_symbol(symbol)
                
                time.sleep(60)
            except Exception as e:
                logger.error(f"Hyper Loop Error: {e}")
                time.sleep(10)

    def process_symbol(self, symbol):
        df = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=250)
        if df.empty: return

        # 4. ATR SPIKE GUARD
        atr_series = self.analyzer.calculate_atr_series(df)
        if (atr_series.iloc[-1] > atr_series.tail(14).mean() * 2.0):
            return

        # 5. HYPER-SELECT LOGIC (RR 1:4)
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema10'] = df['close'].ewm(span=10).mean()
        rsi = self.analyzer.get_rsi(df)
        
        last = df.iloc[-1]
        price = mt5.symbol_info_tick(symbol).ask if last['close'] > last['ema200'] else mt5.symbol_info_tick(symbol).bid

        # COMPRA: Tendencia Alta + Pullback EMA10 + RSI Exaustao
        if last['close'] > last['ema200'] and last['low'] <= last['ema10'] and rsi < 35:
            self.fire_hyper(symbol, mt5.ORDER_TYPE_BUY, price, 4.0)
        
        # VENDA: Tendencia Baixa + Pullback EMA10 + RSI Exaustao
        elif last['close'] < last['ema200'] and last['high'] >= last['ema10'] and rsi > 65:
            self.fire_hyper(symbol, mt5.ORDER_TYPE_SELL, price, 4.0)

    def has_any_position(self):
        return len(mt5.positions_get()) > 0

    def fire_hyper(self, symbol, type, price, rr):
        atr = self.analyzer.calculate_atr(self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=50))
        point = mt5.symbol_info(symbol).point
        
        sl_pts = (atr * 1.5) / point # Tighter SL
        if sl_pts < 100: sl_pts = 100
        
        lot = self.risk.calculate_lot_size(symbol, sl_pts)
        sl = price - (sl_pts * point) if type == mt5.ORDER_TYPE_BUY else price + (sl_pts * point)
        tp = price + (sl_pts * rr * point) if type == mt5.ORDER_TYPE_BUY else price - (sl_pts * rr * point)
        
        logger.info(f"HYPER GATILHO: {symbol} | RR 1:{rr} | SL Pts: {sl_pts:.0f}")
        self.mt5.send_order(symbol, type, lot, price, sl, tp, comment="JarvisHyper_1K")

    def has_position(self, symbol):
        return len(mt5.positions_get(symbol=symbol)) > 0

if __name__ == "__main__":
    JarvisHolyGrail().run()
