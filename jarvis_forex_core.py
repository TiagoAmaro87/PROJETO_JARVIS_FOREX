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
    # Removed EURUSD temporarily to optimize performance based on Elite Audit results
    "SYMBOLS": ["GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
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
        """Unified market view across TFs including D1 for ADR."""
        h4_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_H4"], n=100)
        m15_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_M15"], n=300)
        m5_rates = self.mt5_api.get_rates(symbol, CONFIG["TF_M5"], n=100)
        d1_rates = self.mt5_api.get_rates(symbol, mt5.TIMEFRAME_D1, n=10)
        
        if h4_rates.empty or m15_rates.empty or m5_rates.empty or d1_rates.empty:
            return None
        
        return {
            "h4": h4_rates, "m15": m15_rates, "m5": m5_rates, "d1": d1_rates
        }

    def process_symbol(self, symbol):
        # 0. Session Filter: Only trade during high liquidity
        if not self.analyzer.is_trading_session():
            return

        state = self.fetch_market_state(symbol)
        if not state: return

        current_tick = mt5.symbol_info_tick(symbol)
        if not current_tick: return
        price = current_tick.ask

        # 1. ADR Check: Is the market already exhausted for the day?
        if self.analyzer.is_adr_exhausted(state["d1"], price):
            return

        # 2. SMC: Identify H4 Trend & Order Blocks
        h4_obs = self.analyzer.find_order_blocks(state["h4"])
        last_h4_ob = h4_obs[-1] if h4_obs else None
        
        # 3. Quant Filter: Z-Score
        z_score = self.analyzer.get_z_score(state["m15"])
        
        # 4. MSS Detection
        mss = self.analyzer.detect_mss(state["m5"])
        
        if last_h4_ob:
            entry_price = current_tick.ask if last_h4_ob['type'] == 'bullish' else current_tick.bid
            
            # Zone Check
            point = mt5.symbol_info(symbol).point
            buffer = 3 * point * 10 
            in_zone = (entry_price <= last_h4_ob['top'] + buffer) and (entry_price >= last_h4_ob['bottom'] - buffer)
            
            if in_zone and mss == last_h4_ob['type']:
                if (mss == 'bullish' and z_score < -1.2) or (mss == 'bearish' and z_score > 1.2): 
                    self.trigger_trade(symbol, mss, entry_price)

    def trigger_trade(self, symbol, trend, price):
        point = mt5.symbol_info(symbol).point
        atr = self.analyzer.calculate_atr(self.mt5_api.get_rates(symbol, CONFIG["TF_M15"], n=50))
        
        sl_points = atr * 2.0 / point
        tp1_dist = sl_points * 1.5
        tp2_dist = sl_points * 3.0 # TP2 is further, to be trailed
        
        lot_total = self.risk.calculate_lot_size(symbol, sl_points)
        lot_split = round(lot_total / 2, 2)
        if lot_split < 0.01: lot_split = 0.01

        if trend == 'bullish':
            sl = price - (sl_points * point)
            tp1 = price + (tp1_dist * point)
            tp2 = price + (tp2_dist * point)
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + (sl_points * point)
            tp1 = price - (tp1_dist * point)
            tp2 = price - (tp2_dist * point)
            order_type = mt5.ORDER_TYPE_SELL
        
        logger.info(f"Jarvis ELITE Entry on {symbol} | Split Orders: 2x {lot_split}")
        # Send 2 orders (Scale-out strategy)
        self.mt5_api.send_order(symbol, order_type, lot_split, price, sl, tp1, comment="Jarvis TP1")
        self.mt5_api.send_order(symbol, order_type, lot_split, price, sl, tp2, comment="Jarvis TP2-Trail")

    def manage_positions(self):
        positions = self.mt5_api.get_positions()
        if not positions: return
        
        for pos in positions:
            symbol = pos.symbol
            tick = mt5.symbol_info_tick(symbol)
            point = mt5.symbol_info(symbol).point
            entry = pos.price_open
            
            # PNL Calculation in points
            profit_points = (tick.bid - entry) / point if pos.type == mt5.ORDER_TYPE_BUY else (entry - tick.ask) / point
            sl_dist = abs(entry - pos.sl) / point if pos.sl else 100

            # 1. Break-Even Implementation (When 1:1 reached)
            if profit_points >= sl_dist and (pos.sl < entry if pos.type == mt5.ORDER_TYPE_BUY else pos.sl > entry):
                be_sl = entry + (2 * point * 10) if pos.type == mt5.ORDER_TYPE_BUY else entry - (2 * point * 10)
                self.mt5_api.modify_position(pos.ticket, be_sl, pos.tp)
                logger.info(f"Jarvis PROTECT: BE+ set for {symbol} Ticket {pos.ticket}")

            # 2. Dynamic Trailing for TP2 orders
            if "Trail" in pos.comment and profit_points > sl_dist * 1.5:
                # Trail by 1.5x ATR
                atr = self.analyzer.calculate_atr(self.mt5_api.get_rates(symbol, CONFIG["TF_M15"], n=50))
                new_sl = tick.bid - (atr * 1.5) if pos.type == mt5.ORDER_TYPE_BUY else tick.ask + (atr * 1.5)
                
                # Only move SL favorably
                if pos.type == mt5.ORDER_TYPE_BUY and new_sl > pos.sl:
                    self.mt5_api.modify_position(pos.ticket, new_sl, pos.tp)
                elif pos.type == mt5.ORDER_TYPE_SELL and new_sl < pos.sl:
                    self.mt5_api.modify_position(pos.ticket, new_sl, pos.tp)

    def main_loop(self):
        if not self.bootstrap(): return
        
        last_session_status = None
        
        while self.is_running:
            try:
                # Session Awareness
                is_active = self.analyzer.is_trading_session()
                if is_active != last_session_status:
                    status = "ACTIVE (London/NY Window)" if is_active else "HIBERNATING (Low Liquidity)"
                    logger.info(f"Jarvis Session Status Change: {status}")
                    last_session_status = is_active

                if not is_active:
                    time.sleep(300) # Sleep longer during hibernation
                    continue

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
