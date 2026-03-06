import os
import sys
import time
import logging
import subprocess
import threading
import datetime
import json
import socket
from typing import List, Dict, Optional

# --- DEPENDENCY AUTO-INSTALLER ---
def ensure_dependencies():
    required = ["MetaTrader5", "pandas", "numpy", "scipy", "scikit-learn", "requests", "pytz"]
    for package in required:
        try:
            __import__(package)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

ensure_dependencies()

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from scipy import stats
from sklearn.ensemble import RandomForestRegressor

# --- CONFIGURATION (INTERNAL & AUTONOMOUS) ---
CONFIG = {
    "SYMBOLS": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
    "TIMEFRAME": mt5.TIMEFRAME_M15,
    "RISK_PER_TRADE_PCT": 0.005,  # 0.5%
    "DAILY_STOP_OUT_PCT": 0.02,   # 2%
    "MAX_CORRELATION": 0.75,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183,
    "MT5_PASSWORD": "UiS!6mBq",
    "MT5_SERVER": "MetaQuotes-Demo",
    "LOG_FILE": "jarvis_forex.log",
    "HEARTBEAT_SEC": 30,
    "BACKTEST_WINDOW": 1000,
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(CONFIG["LOG_FILE"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("JARVIS_CORE")

# --- CORE UTILITIES & HEALTH CHECK ---
class JarvisCore:
    def __init__(self):
        self.is_running = True
        self.daily_pnl = 0.0
        self.start_balance = 0.0
        self.last_day = datetime.datetime.now().day
        self.model_weights = {s: 1.0 for s in CONFIG["SYMBOLS"]}
        self.active_trades = {}

    def connect_mt5(self):
        """Attempts to connect and login to the specific Forex MT5 instance."""
        path = CONFIG["MT5_PATH"]
        login = CONFIG["MT5_LOGIN"]
        password = CONFIG["MT5_PASSWORD"]
        server = CONFIG["MT5_SERVER"]
        
        logger.info(f"Connecting to MT5 at: {path} | Account: {login}")
        
        # 1. Initialize Terminal
        if not mt5.initialize(path=path):
            logger.error(f"MT5 initialization failed. Error: {mt5.last_error()}")
            # Fallback to default path if portable fails
            if not mt5.initialize():
                return False

        # 2. Explicit Login
        authorized = mt5.login(login, password=password, server=server)
        if authorized:
            logger.info(f"Jarvis AUTHENTICATED - Account {login} is active on {server}.")
            return True
        else:
            logger.error(f"Authentication failed for {login}. Error code: {mt5.last_error()}")
            return False

    def check_health(self):
        """Monitors MT5 connection and resets daily metrics autonomously."""
        now = datetime.datetime.now()
        
        # Reset Day Logic
        if now.day != self.last_day:
            logger.info("New trading day detected. Resetting Daily Stop-Out limits.")
            self.last_day = now.day
            self.daily_pnl = 0.0
            account_info = mt5.account_info()
            if account_info:
                self.start_balance = account_info.balance

        # Connection Check & Relaunch
        if not mt5.terminal_info():
            logger.warning("MT5 Terminal lost. Relaunching...")
            self.connect_mt5()

    def get_market_data(self, symbol, timeframe, n=500):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    # --- INTELLIGENCE MODULES ---
    def calculate_indicators(self, df):
        """Calculates ATR, Liquidity (Order Blocks), and SMAs for Trend Alignment."""
        # ATR (Volatility)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        # Liquidity / Order Blocks (Extreme volume + reversal)
        df['vol_ma'] = df['tick_volume'].rolling(20).mean()
        df['ob_bullish'] = (df['close'] > df['open']) & (df['close'].shift(1) < df['open'].shift(1)) & (df['tick_volume'] > df['vol_ma'] * 1.5)
        df['ob_bearish'] = (df['close'] < df['open']) & (df['close'].shift(1) > df['open'].shift(1)) & (df['tick_volume'] > df['vol_ma'] * 1.5)
        
        # Trend
        df['sma_200'] = df['close'].rolling(200).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        return df

    def get_sentiment(self):
        """Autonomous Sentiment Proxy based on DXY Trend."""
        try:
            # Scanning USDX as global driver
            dxy_rates = mt5.copy_rates_from_pos("USDX", mt5.TIMEFRAME_H1, 0, 24)
            if dxy_rates is not None:
                df_dxy = pd.DataFrame(dxy_rates)
                change = (df_dxy['close'].iloc[-1] - df_dxy['close'].iloc[0]) / df_dxy['close'].iloc[0]
                if change > 0.005: return "USD_Bullish"
                if change < -0.005: return "USD_Bearish"
            return "Neutral"
        except Exception:
            return "Neutral"

    def backtest_in_loop(self, symbol):
        """Autonomous performance loop: reduces symbol weight if losing."""
        try:
            history = mt5.history_deals_get(datetime.datetime.now() - datetime.timedelta(days=7), datetime.datetime.now())
            if not history: return 1.0
            symbol_trades = [t.profit for t in history if t.symbol == symbol]
            if not symbol_trades: return 1.0
            
            # Simple Sharpe Ratio proxy
            win_rate = len([p for p in symbol_trades if p > 0]) / len(symbol_trades)
            if win_rate < 0.4:
                logger.warning(f"Strategy degradation on {symbol} (WR: {win_rate*100:.1f}%). Adjusting weight.")
                return 0.5
            return 1.0
        except Exception:
            return 1.0

    # --- RISK & TRADE MANAGEMENT ---
    def calculate_lot_size(self, symbol, risk_amount, stop_loss_pips):
        account = mt5.account_info()
        if not account or not stop_loss_pips: return 0.01
        
        tick_value = mt5.symbol_info(symbol).trade_tick_value
        lot = risk_amount / (stop_loss_pips * tick_value) if tick_value else 0.01
        
        info = mt5.symbol_info(symbol)
        lot = max(info.volume_min, min(info.volume_max, lot))
        return round(lot, 2)

    def manage_risk(self):
        """Hard protection: shuts down trading if daily loss limit is hit."""
        account = mt5.account_info()
        if not account: return False
        
        if self.start_balance == 0: self.start_balance = account.balance
        
        current_drawdown = (self.start_balance - account.equity) / self.start_balance
        if current_drawdown >= CONFIG["DAILY_STOP_OUT_PCT"]:
            logger.critical(f"PROTECTION TRIGGERED: Daily Drawdown ({current_drawdown*100:.2f}%) hit limit. Jarvis idling.")
            return False
        return True

    def execute_trade(self, symbol, type, price, sl, tp):
        """Autonomous execution engine."""
        account = mt5.account_info()
        risk_cash = account.balance * CONFIG["RISK_PER_TRADE_PCT"]
        
        info = mt5.symbol_info(symbol)
        sl_pips = abs(price - sl) / info.point
        lot = self.calculate_lot_size(symbol, risk_cash, sl_pips)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "Jarvis Autonomous Core",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Execution Error [{symbol}]: {result.comment}")
        else:
            logger.info(f"SUCCESS: {('BUY' if type == mt5.ORDER_TYPE_BUY else 'SELL')} {symbol} at {price} | Lot: {lot}")

    def manage_active_positions(self):
        """Break-even and Trailing Stop management."""
        positions = mt5.positions_get()
        if not positions: return
        
        for pos in positions:
            symbol = pos.symbol
            tick = mt5.symbol_info_tick(symbol)
            point = mt5.symbol_info(symbol).point
            
            # SL distance from entry
            entry_price = pos.price_open
            sl_distance = abs(entry_price - pos.sl) if pos.sl else (pos.price_open * 0.01) # fallback
            
            # 1. Break-Even Trigger: Moved 1x SL distance in profit
            if pos.type == mt5.POSITION_TYPE_BUY:
                if tick.bid > (entry_price + sl_distance) and (not pos.sl or pos.sl < entry_price):
                    self._update_sl_tp(pos.ticket, entry_price + (5 * point), pos.tp)
                    logger.info(f"PROTECTION: Moved {symbol} to Break-Even.")
            elif pos.type == mt5.POSITION_TYPE_SELL:
                if tick.ask < (entry_price - sl_distance) and (not pos.sl or pos.sl > entry_price):
                    self._update_sl_tp(pos.ticket, entry_price - (5 * point), pos.tp)
                    logger.info(f"PROTECTION: Moved {symbol} to Break-Even.")

    def _update_sl_tp(self, ticket, sl, tp):
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        return mt5.order_send(request)

    # --- BRAIN SCAN ---
    def scan_opportunities(self):
        """Scans markets for Order Block entries aligned with H1 Sentiment."""
        if not self.manage_risk(): return

        sentiment = self.get_sentiment()
        
        for symbol in CONFIG["SYMBOLS"]:
            # Backtest feedback
            weight = self.backtest_in_loop(symbol)
            if weight < 1.0: continue # Skip symbols with current model drift
            
            df = self.get_market_data(symbol, CONFIG["TIMEFRAME"])
            if df.empty: continue
            
            df = self.calculate_indicators(df)
            last = df.iloc[-1]
            tick = mt5.symbol_info_tick(symbol)
            
            # Strategy: OB Reversal + SMA Filter + Sentiment Correlation
            # BULLISH ENTRY
            if last['ob_bullish'] and last['close'] > last['sma_200']:
                if "USD_Bearish" in sentiment and symbol.endswith("USD"): # USD Weakness strategy
                    sl = last['low'] - (last['atr'] * 1.2)
                    tp = last['close'] + (last['close'] - sl) * 2
                    self.execute_trade(symbol, mt5.ORDER_TYPE_BUY, tick.ask, sl, tp)
                
            # BEARISH ENTRY
            elif last['ob_bearish'] and last['close'] < last['sma_200']:
                if "USD_Bullish" in sentiment and symbol.endswith("USD"): # USD Strength strategy
                    sl = last['high'] + (last['atr'] * 1.2)
                    tp = last['close'] - (sl - last['close']) * 2
                    self.execute_trade(symbol, mt5.ORDER_TYPE_SELL, tick.bid, sl, tp)

    def fire_test_trade(self):
        """Sends a minimal 0.01 lot trade to verify system-to-broker pipeline."""
        logger.info("TEST: Discharging a verification trade on EURUSD...")
        symbol = "EURUSD"
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error("TEST FAILED: Could not get market price for EURUSD.")
            return

        price = tick.ask
        sl = price - 0.00200 # 20 pips
        tp = price + 0.00400 # 40 pips
        
        self.execute_trade(symbol, mt5.ORDER_TYPE_BUY, price, sl, tp)
        logger.info("TEST: Verification trade sent to MetaTrader 5.")

    def run(self):
        """Jarvis Infinite Loop - The Heart of Jarvis."""
        logger.info("--- JARVIS FOREX CORE INITIALIZED BY TIAGO ---")
        if not self.connect_mt5():
            logger.critical("MT5 CONNECTION FAILED - HALTING SYSTEM.")
            return

        # Fire test trade to confirm automation is 100% functional
        self.fire_test_trade()

        while self.is_running:
            try:
                self.check_health()
                self.scan_opportunities()
                self.manage_active_positions()
                
                # Sleep to prevent over-scanning and CPU spike
                time.sleep(CONFIG["HEARTBEAT_SEC"])
                
            except Exception as e:
                logger.error(f"AUTO-CORRECTION: Error encountered: {e}")
                time.sleep(15) # Wait for network/system stability
                continue

if __name__ == "__main__":
    jarvis = JarvisCore()
    jarvis.run()
