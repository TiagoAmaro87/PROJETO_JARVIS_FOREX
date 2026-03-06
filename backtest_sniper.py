import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
import random
from datetime import datetime
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
from mt5_interface import MT5Interface

CONFIG_BT = {
    "SYMBOLS": ["AUDUSD"], 
    "TF_H4": mt5.TIMEFRAME_H4, "TF_M15": mt5.TIMEFRAME_M15, "TF_M5": mt5.TIMEFRAME_M5,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
    "RISK_PER_TRADE_PCT": 0.01,
}

logging.basicConfig(level=logging.ERROR)

class BacktestSniper:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_returns = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS SNIPER PERFORMANCE AUDIT (AUDUSD)".center(50, "="))
        
        dxy_data = self.api.get_rates("USDX", self.config["TF_M15"], n=5000)
        self.backtest_symbol("AUDUSD", dxy_data)
        self.report()

    def backtest_symbol(self, symbol, dxy_full):
        # Increased data window for deep history
        m15 = self.api.get_rates(symbol, self.config["TF_M15"], n=5000)
        h4 = self.api.get_rates(symbol, self.config["TF_H4"], n=1200)
        
        if m15.empty: return

        trades = []
        point = mt5.symbol_info(symbol).point
        last_trade_day = None

        for i in range(300, len(m15) - 60):
            row = m15.iloc[i]
            t = row['time']
            
            # 1. ONE TRADE PER DAY ONLY
            if last_trade_day == t.date(): continue

            # 2. SESSION FILTER
            if not (7 <= t.hour <= 20): continue
            
            price = row['close']
            c_h4 = h4[h4['time'] < t].tail(100)
            c_m15 = m15.iloc[i-200:i+1]
            if c_h4.empty: continue

            # SNIPER CORES
            obs = self.analyzer.find_order_blocks(c_h4)
            if not obs: continue
            last_ob = obs[-1]
            
            # Zone Check (Tight 2 pips)
            in_zone = (price <= last_ob['top'] + 20*point) and (price >= last_ob['bottom'] - 20*point)
            if not in_zone: continue

            # Triple Quant
            z = self.analyzer.get_z_score(c_m15)
            rsi = self.analyzer.get_rsi(c_m15)
            c_dxy = dxy_full[dxy_full['time'] < t].tail(100)
            dxy_trend = self.analyzer.get_dxy_trend(c_dxy)

            signal = None
            if last_ob['type'] == 'bullish' and z < -2.0 and rsi < 30 and dxy_trend == 'bearish':
                signal = "BUY"
            elif last_ob['type'] == 'bearish' and z > 2.0 and rsi > 70 and dxy_trend == 'bullish':
                signal = "SELL"

            if signal:
                atr = self.analyzer.calculate_atr(c_m15)
                sl_d = atr * 2.5
                tp_d = sl_d * 2.5 # Aggressive RR for Sniper
                
                trade = {
                    't': t, 'type': signal, 'p': price, 
                    'sl': price-sl_d if signal=="BUY" else price+sl_d,
                    'tp': price+tp_d if signal=="BUY" else price-tp_d,
                    'res': 'Open', 'ret': 0
                }
                
                for j in range(i+1, len(m15)):
                    b = m15.iloc[j]
                    if trade['type'] == "BUY":
                        if b['low'] <= trade['sl']: trade['res'] = 'Loss'; trade['ret'] = -0.01; break
                        if b['high'] >= trade['tp']: trade['res'] = 'Win'; trade['ret'] = 0.025; break
                    else:
                        if b['high'] >= trade['sl']: trade['res'] = 'Loss'; trade['ret'] = -0.01; break
                        if b['low'] <= trade['tp']: trade['res'] = 'Win'; trade['ret'] = 0.025; break
                
                if trade['res'] != 'Open':
                    trades.append(trade)
                    self.all_returns.append(trade['ret'])
                    last_trade_day = t.date()
                    i += 100 # Skip day

        self.trades = trades

    def report(self):
        print(f"Total Trades: {len(self.trades)}")
        wins = [t for t in self.trades if t['res'] == 'Win']
        losses = [t for t in self.trades if t['res'] == 'Loss']
        wr = (len(wins)/len(self.trades)*100) if self.trades else 0
        pnl = sum([t['ret'] for t in self.trades]) * 100
        
        print(f"Win Rate:     {wr:.1f}%")
        print(f"Total Net PNL: {pnl:>+6.2f}%")
        print(f"Avg PnL/Trade:{pnl/len(self.trades) if self.trades else 0:.2f}%")
        print("=" * 50)

if __name__ == "__main__":
    BacktestSniper(CONFIG_BT).run()
