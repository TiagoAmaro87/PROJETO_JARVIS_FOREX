import os
import sys
import time
import logging
import datetime
from mt5_interface import MT5Interface
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
import MetaTrader5 as mt5

# --- JARVIS MULTI-ENGINE CONFIG ---
CONFIG = {
    # MAPPING: Symbol -> Strategy Type
    "ASSETS": {
        "GBPUSD": "GEKKO", # Trend Following EMA 200/20
        "EURUSD": "GEKKO", # Trend Following EMA 200/20
        "AUDUSD": "SNIPER", # SMC Liquidity + DXY Filter
    },
    "RISK_PER_TRADE_PCT": 0.005, # 0.5% per trade
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183,
    "MT5_PASSWORD": "UiS!6mBq",
    "MT5_SERVER": "MetaQuotes-Demo",
    "LOG_FILE": "jarvis_multi_engine.log"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.FileHandler(CONFIG["LOG_FILE"]), logging.StreamHandler()]
)
logger = logging.getLogger("JARVIS_MULTI")

class JarvisMultiEngine:
    def __init__(self):
        self.mt5 = MT5Interface(CONFIG)
        self.analyzer = MarketAnalyzer(CONFIG)
        self.risk = RiskManager(CONFIG)

    def bootstrap(self):
        if not self.mt5.connect(): return False
        logger.info("--- JARVIS MULTI-ENGINE ACTIVE: SPECIALIZED MODE ---")
        return True

    def run(self):
        if not self.bootstrap(): return
        while True:
            try:
                if not self.analyzer.is_trading_session():
                    time.sleep(300); continue

                for symbol, strategy in CONFIG["ASSETS"].items():
                    if strategy == "GEKKO":
                        self.process_gekko(symbol)
                    elif strategy == "SNIPER":
                        self.process_sniper(symbol)
                
                self.manage_positions()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Main Loop Error: {e}")
                time.sleep(10)

    def process_gekko(self, symbol):
        """Trend Following for Volatile Majors."""
        df = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=250)
        if df.empty or self.has_position(symbol): return

        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        last, prev = df.iloc[-1], df.iloc[-2]
        tick = mt5.symbol_info_tick(symbol)
        
        # Bullish Pullback
        if last['close'] > last['ema200'] and prev['low'] <= prev['ema20'] and last['close'] > last['ema20']:
            sl = last['low'] - (5 * mt5.symbol_info(symbol).point * 10)
            tp = last['close'] + (last['close'] - sl) * 2.5
            self.execute(symbol, mt5.ORDER_TYPE_BUY, tick.ask, sl, tp, "Gekko_Trend")

        # Bearish Pullback
        elif last['close'] < last['ema200'] and prev['high'] >= prev['ema20'] and last['close'] < last['ema20']:
            sl = last['high'] + (5 * mt5.symbol_info(symbol).point * 10)
            tp = last['close'] - (sl - last['close']) * 2.5
            self.execute(symbol, mt5.ORDER_TYPE_SELL, tick.bid, sl, tp, "Gekko_Trend")

    def process_sniper(self, symbol):
        """Precision SMC for AUDUSD/Stability Pairs."""
        h4 = self.mt5.get_rates(symbol, mt5.TIMEFRAME_H4, n=100)
        m15 = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=300)
        if h4.empty or m15.empty or self.has_position(symbol): return

        obs = self.analyzer.find_order_blocks(h4)
        if not obs: return
        last_ob = obs[-1]
        
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if last_ob['type'] == 'bullish' else tick.bid
        
        # Zone Check
        point = mt5.symbol_info(symbol).point
        in_zone = (price <= last_ob['top'] + 20*point) and (price >= last_ob['bottom'] - 20*point)
        if not in_zone: return

        # Filters
        z = self.analyzer.get_z_score(m15)
        dxy_data = self.mt5.get_rates("USDX", mt5.TIMEFRAME_M15, n=100)
        dxy_trend = self.analyzer.get_dxy_trend(dxy_data)

        if last_ob['type'] == 'bullish' and z < -1.5 and dxy_trend == 'bearish':
            sl = last_ob['bottom'] - 5*point
            tp = price + (price - sl) * 2.0
            self.execute(symbol, mt5.ORDER_TYPE_BUY, price, sl, tp, "Sniper_SMC")
        elif last_ob['type'] == 'bearish' and z > 1.5 and dxy_trend == 'bullish':
            sl = last_ob['top'] + 5*point
            tp = price - (sl - price) * 2.0
            self.execute(symbol, mt5.ORDER_TYPE_SELL, price, sl, tp, "Sniper_SMC")

    def execute(self, symbol, type, price, sl, tp, comment):
        point = mt5.symbol_info(symbol).point
        sl_pts = abs(price - sl) / point
        lot = self.risk.calculate_lot_size(symbol, sl_pts)
        logger.info(f"DEPLOYING {comment} on {symbol} | Lot: {lot}")
        self.mt5.send_order(symbol, type, lot, price, sl, tp, comment=comment)

    def has_position(self, symbol):
        return len(mt5.positions_get(symbol=symbol)) > 0

    def manage_positions(self):
        # Auto Break-Even after 1:1 RR
        positions = mt5.positions_get()
        for pos in positions:
            if pos.comment not in ["Gekko_Trend", "Sniper_SMC"]: continue
            
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
