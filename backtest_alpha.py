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
    "SYMBOLS": ["AUDUSD", "GBPUSD", "USDJPY"], 
    "TF_H4": mt5.TIMEFRAME_H4, "TF_M15": mt5.TIMEFRAME_M15, "TF_M5": mt5.TIMEFRAME_M5,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
    "RISK_PER_TRADE_PCT": 0.005,
}

logging.basicConfig(level=logging.ERROR)

class BacktestAlpha:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_returns = []
        self.results = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS ALPHA MULTI-STRATEGY AUDIT".center(50, "="))
        
        dxy_data = self.api.get_rates("USDX", self.config["TF_M15"], n=4500)
        
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol, dxy_data)
        
        self.report()
        self.monte_carlo_simulation()

    def backtest_symbol(self, symbol, dxy_full):
        m15 = self.api.get_rates(symbol, self.config["TF_M15"], n=4000)
        h4 = self.api.get_rates(symbol, self.config["TF_H4"], n=1000)
        m5 = self.api.get_rates(symbol, self.config["TF_M5"], n=6000)
        
        if m15.empty: return

        trades = []
        point = mt5.symbol_info(symbol).point
        buffer = 5 * point * 10

        for i in range(300, len(m15) - 50):
            row = m15.iloc[i]
            t = row['time']
            
            # 1. Session Filter
            if not (7 <= t.hour <= 20): continue
            
            price = row['close']
            
            # Setup context
            c_h4 = h4[h4['time'] < t].tail(100)
            c_m15 = m15.iloc[i-200:i+1]
            c_m5 = m5[m5['time'] < t].tail(50)
            if c_h4.empty or c_m5.empty: continue

            # STRATEGY 1: SMC
            obs = self.analyzer.find_order_blocks(c_h4)
            last_ob = obs[-1] if obs else None
            mss = self.analyzer.detect_mss(c_m5)
            
            entered = False
            trend = None
            strat = ""

            if last_ob and mss == last_ob['type']:
                if (price <= last_ob['top'] + buffer) and (price >= last_ob['bottom'] - buffer):
                    trend = mss; strat = "SMC"; entered = True

            # STRATEGY 2: REVERSION
            if not entered:
                upper, lower = self.analyzer.get_bollinger_bands(c_m15)
                rsi = self.analyzer.get_rsi(c_m15)
                z = self.analyzer.get_z_score(c_m15)
                if rsi > 70 and z > 1.8 and price >= upper:
                    trend = "bearish"; strat = "REV"; entered = True
                elif rsi < 30 and z < -1.8 and price <= lower:
                    trend = "bullish"; strat = "REV"; entered = True

            if entered:
                atr = self.analyzer.calculate_atr(c_m15)
                sl_d = atr * 2.5
                tp_d = sl_d * 1.5 # Conservative RR
                
                trade = {
                    't': t, 'type': trend, 'p': price, 
                    'sl': price-sl_d if trend=='bullish' else price+sl_d,
                    'tp': price+tp_d if trend=='bullish' else price-tp_d,
                    'res': 'Open', 'ret': 0
                }
                
                # Scan for result
                for j in range(i+1, len(m15)):
                    b = m15.iloc[j]
                    if trade['type'] == 'bullish':
                        if b['low'] <= trade['sl']: trade['res'] = 'Loss'; trade['ret'] = -0.005; break
                        if b['high'] >= trade['tp']: trade['res'] = 'Win'; trade['ret'] = 0.0075; break
                    else:
                        if b['high'] >= trade['sl']: trade['res'] = 'Loss'; trade['ret'] = -0.005; break
                        if b['low'] <= trade['tp']: trade['res'] = 'Win'; trade['ret'] = 0.0075; break
                
                if trade['res'] != 'Open':
                    trades.append(trade)
                    self.all_returns.append(trade['ret'])
                    i += 40

        self.results.append({'s': symbol, 'trades': trades})

    def report(self):
        all_t = []
        for r in self.results:
            wins = len([t for t in r['trades'] if t['res'] == 'Win'])
            pnl = sum([t['ret'] for t in r['trades']]) * 100
            wr = (wins/len(r['trades'])*100) if r['trades'] else 0
            print(f"{r['s'].ljust(10)} | {str(len(r['trades'])).ljust(3)} trades | WR: {wr:>5.1f}% | PNL: {pnl:>+6.2f}%")
            all_t.extend(r['trades'])
        
        tw = len([t for t in all_t if t['res'] == 'Win'])
        gpnl = sum([t['ret'] for t in all_t]) * 100
        print("-" * 50)
        print(f"GLOBAL ALPHA | Trades: {len(all_t)} | Win Rate: {(tw/len(all_t)*100 if all_t else 0):.1f}% | Net PNL: {gpnl:.2f}%")
        print("=" * 50 + "\n")

    def monte_carlo_simulation(self, iterations=1000):
        if not self.all_returns: return
        print(f"MONTE CARLO STRESS TEST ({iterations} Iterations)...")
        final_balances = []
        initial = 100000.0
        for _ in range(iterations):
            bal = initial
            sim = random.choices(self.all_returns, k=len(self.all_returns))
            for r in sim: bal *= (1 + r)
            final_balances.append(bal)
        
        prob_prof = len([b for b in final_balances if b > initial]) / iterations * 100
        print(f"  Probability of Monthly Profit: {prob_prof:.1f}%")
        print(f"  Worst Case Scenario:           ${np.min(final_balances):,.2f}")
        print("=" * 50 + "\n")

if __name__ == "__main__":
    BacktestAlpha(CONFIG_BT).run()
