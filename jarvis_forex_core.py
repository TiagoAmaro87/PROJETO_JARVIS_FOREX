import os
import sys
import time
import logging
import datetime
from mt5_interface import MT5Interface
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
import MetaTrader5 as mt5

# --- SYSTEM CONFIGuration (Independent of Manual Interaction) ---
CONFIG = {
    "SYMBOLS": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
    "TF_H4": mt5.TIMEFRAME_H4,
    "TF_M15": mt5.TIMEFRAME_M15,
    "TF_M5": mt5.TIMEFRAME_M5,
    "RISK_PER_TRADE_PCT": 0.005,  # 0.5%
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183,
    "MT5_PASSWORD": "UiS!6mBq",
    "MT5_SERVER": "MetaQuotes-Demo",
    "LOG_FILE": "jarvis_forex_core.log",
    "HEARTBEAT_SEC": 60,
    "SMC_PERIOD": 500,
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.FileHandler(CONFIG["LOG_FILE"]), logging.StreamHandler()]
)
logger = logging.getLogger("JARVIS_CORE")

class JarvisOrchestrator:
    def __init__(self):
        self.mt5_api = MT5Interface(CONFIG)
        self.analyzer = MarketAnalyzer(CONFIG)
        self.risk = RiskManager(CONFIG)
        self.is_running = True
        self.active_signals = {} # Track signals per symbol

    def bootstrap(self):
        logger.info("Initializing Jarvis Orchestrator...")
        if not self.mt5_api.connect():
            logger.critical("Failed to connect to MT5. Jarvis system offline.")
            return False
        logger.info("Connection stable. Jarvis system live.")
        return True

    def fetch_market_state(self, symbol):
        """Unified market view across TFs."""
        h4_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_H4"], n=100)
        m15_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_M15"], n=300)
        m5_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_M5"], n=100)
        
        if h4_rates.empty or m15_rates.empty or m5_rates.empty:
            return None
        
        return {
            "h4": h4_rates,
            "m15": m15_rates,
            "m5": m5_rates
        }

    def process_symbol(self, symbol):
        state = self.fetch_market_state(symbol)
        if not state: return

        # 1. SMC: Identify H4 Trend & Order Blocks
        h4_obs = self.analyzer.find_order_blocks(state["h4"])
        last_h4_ob = h4_obs[-1] if h4_obs else None
        
        # 2. SMC: Identify M15 Entry FVGs/OBs
        m15_obs = self.analyzer.find_order_blocks(state["m15"])
        m15_fvgs = self.analyzer.find_fvg(state["m15"])
        
        # 3. Quant Filter: Z-Score for statistical exhaustion
        z_score = self.analyzer.get_z_score(state["m15"])
        
        # 4. MSS Detection
        mss = self.analyzer.detect_mss(state["m5"])
        
        # 5. Entry Signal Logic: H4 OB touch -> M15 FVG Presence -> M5 MSS Confirmation
        # Check current price vs H4 OB
        current_tick = mt5.symbol_info_tick(symbol)
        if not current_tick: return

        # Simplified SMC Strategy entry logic
        if last_h4_ob:
            price = current_tick.ask if last_h4_ob['type'] == 'bullish' else current_tick.bid
            
            # Distance from H4 OB (Within 10 pips)
            point = mt5.symbol_info(symbol).point
            dist = abs(price - last_h4_ob['price']) / (point * 10)
            
            if dist < 1.0: # Near H4 OB
                if mss == last_h4_ob['type']: # MSS Alignment
                    if (mss == 'bullish' and z_score < -2.0) or (mss == 'bearish' and z_score > 2.0): # Quant Filter
                        # Execute Trade
                        self.trigger_trade(symbol, mss, price, last_h4_ob['price'])

    def trigger_trade(self, symbol, trend, price, ob_price):
        # Stop Loss at the extreme of the signal wick/OB
        point = mt5.symbol_info(symbol).point
        atr = self.analyzer.calculate_atr(self.mt5_api.get_rates(symbol, CONFIG["TF_M15"], n=50))
        
        sl_points = atr * 1.5 / point
        if trend == 'bullish':
            sl = price - (sl_points * point)
            tp = price + (sl_points * 3 * point) # 1:3 RR
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + (sl_points * point)
            tp = price - (sl_points * 3 * point) # 1:3 RR
            order_type = mt5.ORDER_TYPE_SELL
        
        lot = self.risk.calculate_lot_size(symbol, sl_points)
        
        # Final Correlation Check
        # ... logic if needed across symbols
        
        logger.info(f"Triggering Jarvis SMC Execution on {symbol} | Type: {trend} | Lot: {lot}")
        self.mt5_api.send_order(symbol, order_type, lot, price, sl, tp, comment="Jarvis Autonomous SMC")

    def manage_positions(self):
        positions = self.mt5_api.get_positions()
        if not positions: return
        
        for pos in positions:
            symbol = pos.symbol
            tick = mt5.symbol_info_tick(symbol)
            point = mt5.symbol_info(symbol).point
            
            # Break-Even & Trailing Stop Logic
            entry = pos.price_open
            profit_points = (tick.bid - entry) / point if pos.type == mt5.ORDER_TYPE_BUY else (entry - tick.ask) / point
            
            sl_dist = abs(entry - pos.sl) / point if pos.sl else 100
            
            # If profit is 1:1, move Stop Loss to BE + fees
            if profit_points >= sl_dist and (pos.sl < entry if pos.type == mt5.ORDER_TYPE_BUY else pos.sl > entry):
                be_sl = entry + (5 * point) if pos.type == mt5.ORDER_TYPE_BUY else entry - (5 * point)
                self.mt5_api.modify_position(pos.ticket, be_sl, pos.tp)
                logger.info(f"Jarvis PROTECT: Move to BE on {symbol}")

    def main_loop(self):
        if not self.bootstrap(): return
        
        while self.is_running:
            try:
                # Latency & Health Check
                start_calc = time.time()
                
                # Scan symbols
                for symbol in CONFIG["SYMBOLS"]:
                    self.process_symbol(symbol)
                    
                self.manage_positions()
                
                # Check performance factor (Placeholder for Walk-Forward)
                # ... recalibration logic ...
                
                latency = (time.time() - start_calc) * 1000
                if latency > 2000:
                    logger.warning(f"High computation latency: {latency:.2f}ms")
                
                time.sleep(CONFIG["HEARTBEAT_SEC"])
                
            except Exception as e:
                logger.error(f"Global Orcherstrator Error: {e}")
                time.sleep(30)
                continue

if __name__ == "__main__":
    jarvis = JarvisOrchestrator()
    jarvis.main_loop()
