import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
import random
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
from mt5_interface import MT5Interface

CONFIG_BT = {
    "SYMBOLS": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
    "TF_H4": mt5.TIMEFRAME_H4, "TF_M15": mt5.TIMEFRAME_M15, "TF_M5": mt5.TIMEFRAME_M5,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
    "RISK_PER_TRADE_PCT": 0.005,
    "RR_RATIO": 1.5, # Adjusted for higher win rate
    "Z_THRESHOLD": 1.2, # More generous frequency
}

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("JARVIS_BACKTEST")

class BacktestEngine:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.results = []
        self.all_returns = []

    def run(self):
        if not self.api.connect(): return
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol)
        
        self.report()
        self.monte_carlo_simulation()

    def backtest_symbol(self, symbol):
        # Increased data fetch for better sample size
        m15 = self.api.get_rates(symbol, self.config["TF_M15"], n=5000)
        h4 = self.api.get_rates(symbol, self.config["TF_H4"], n=1000)
        m5 = self.api.get_rates(symbol, self.config["TF_M5"], n=6000)
        if m15.empty: return

        trades = []
        p = mt5.symbol_info(symbol).point
        buf = 30 * p # 3-pip buffer

        for i in range(300, len(m15) - 20):
            t = m15['time'].iloc[i]
            c_h4 = h4[h4['time'] < t].tail(100)
            c_m15 = m15.iloc[i-200:i+1]
            c_m5 = m5[m5['time'] < t].tail(50)
            if c_h4.empty or c_m5.empty: continue

            obs = self.analyzer.find_order_blocks(c_h4)
            last_ob = obs[-1] if obs else None
            z = self.analyzer.get_z_score(c_m15)
            mss = self.analyzer.detect_mss(c_m5)

            if last_ob:
                price = m15['close'].iloc[i]
                in_zone = (price <= last_ob['top'] + buf) and (price >= last_ob['bottom'] - buf)
                
                if in_zone and mss == last_ob['type']:
                    if (mss == 'bullish' and z < -self.config["Z_THRESHOLD"]) or \
                       (mss == 'bearish' and z > self.config["Z_THRESHOLD"]):
                        
                        atr = self.analyzer.calculate_atr(c_m15)
                        sl_d = atr * 2.0 # More space for noise
                        tp_d = sl_d * self.config["RR_RATIO"]
                        
                        trade = {
                            't': t, 'type': mss, 'p': price, 
                            'sl': price-sl_d if mss=='bullish' else price+sl_d,
                            'tp': price+tp_d if mss=='bullish' else price-tp_d,
                            'res': 'Open', 'ret': 0
                        }
                        
                        for j in range(i+1, len(m15)):
                            b = m15.iloc[j]
                            if trade['type'] == 'bullish':
                                if b['low'] <= trade['sl']: 
                                    trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                                if b['high'] >= trade['tp']: 
                                    trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * self.config["RR_RATIO"]; break
                            else:
                                if b['high'] >= trade['sl']: 
                                    trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                                if b['low'] <= trade['tp']: 
                                    trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * self.config["RR_RATIO"]; break
                        
                        if trade['res'] != 'Open':
                            trades.append(trade)
                            self.all_returns.append(trade['ret'])
                            i += 30 # Avoid cluster signals

        self.results.append({'s': symbol, 'trades': trades})

    def report(self):
        print("\n" + "REFINED JARVIS FOREX AUDIT".center(50, "="))
        all_t = []
        for r in self.results:
            wins = len([t for t in r['trades'] if t['res'] == 'Win'])
            losses = len([t for t in r['trades'] if t['res'] == 'Loss'])
            wr = (wins / (wins+losses)) * 100 if (wins+losses) > 0 else 0
            pnl_pct = sum([t['ret'] for t in r['trades']]) * 100
            print(f"{r['s'].ljust(10)} | {str(len(r['trades'])).ljust(3)} trades | WR: {wr:>5.1f}% | PNL: {pnl_pct:>+6.2f}%")
            all_t.extend(r['trades'])
        
        tw = len([t for t in all_t if t['res'] == 'Win'])
        tl = len([t for t in all_t if t['res'] == 'Loss'])
        gwr = (tw / (tw+tl)) * 100 if (tw+tl) > 0 else 0
        gpnl = sum([t['ret'] for t in all_t]) * 100
        print("-" * 50)
        print(f"GLOBAL SUMMARY | Trades: {len(all_t)} | Win Rate: {gwr:.1f}% | Total PNL: {gpnl:.2f}%")
        print("=" * 50 + "\n")

    def monte_carlo_simulation(self, iterations=1000):
        if not self.all_returns: return
        print("RUNNING MONTE CARLO SIMULATION (1000 Runs)...")
        
        final_balances = []
        initial_balance = 100000.0
        
        for _ in range(iterations):
            balance = initial_balance
            # Shuffle returns to simulate sequence risk
            sim_returns = random.choices(self.all_returns, k=len(self.all_returns))
            for ret in sim_returns:
                balance *= (1 + ret)
            final_balances.append(balance)
        
        avg_final = np.mean(final_balances)
        min_final = np.min(final_balances)
        max_final = np.max(final_balances)
        prob_profit = len([b for b in final_balances if b > initial_balance]) / iterations * 100
        
        print(f"Monte Carlo Results (Based on {len(self.all_returns)} trades):")
        print(f"  Probability of Profit: {prob_profit:.1f}%")
        print(f"  Average Final Balance: ${avg_final:,.2f}")
        print(f"  Worst Case Scenario:   ${min_final:,.2f}")
        print(f"  Best Case Scenario:    ${max_final:,.2f}")
        print("=" * 50 + "\n")

if __name__ == "__main__":
    BacktestEngine(CONFIG_BT).run()
