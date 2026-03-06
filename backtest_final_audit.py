import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
import random
import matplotlib.pyplot as plt
from datetime import datetime
from market_analyzer import MarketAnalyzer
from risk_manager import RiskManager
from mt5_interface import MT5Interface

CONFIG_BT = {
    "GBPUSD": "GEKKO",
    "EURUSD": "GEKKO",
    "AUDUSD": "SNIPER",
    "INITIAL_BALANCE": 1000.0,
    "RISK_PER_TRADE_PCT": 0.005, # 0.5%
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
}

logging.basicConfig(level=logging.ERROR)

class FinalAlphaAudit:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_trades = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS FINAL ALPHA AUDIT ($1000 BANK)".center(50, "="))
        
        dxy_data = self.api.get_rates("USDX", mt5.TIMEFRAME_M15, n=5000)
        
        for symbol, strategy in self.config.items():
            if symbol in ["GBPUSD", "EURUSD", "AUDUSD"]:
                self.backtest_asset(symbol, strategy, dxy_data)
        
        self.all_trades.sort(key=lambda x: x['t'])
        self.report_and_plot()
        self.monte_carlo(iterations=1000)

    def backtest_asset(self, symbol, strategy, dxy_full):
        m15 = self.api.get_rates(symbol, mt5.TIMEFRAME_M15, n=4000)
        h4 = self.api.get_rates(symbol, mt5.TIMEFRAME_H4, n=1000)
        m5 = self.api.get_rates(symbol, mt5.TIMEFRAME_M5, n=4000)
        if m15.empty: return

        p = mt5.symbol_info(symbol).point
        
        for i in range(300, len(m15) - 50):
            row = m15.iloc[i]
            t = row['time']
            if not (7 <= t.hour <= 20): continue
            
            price = row['close']
            c_m15 = m15.iloc[i-200:i+1]
            
            entered = False
            trend = None
            
            if strategy == "GEKKO":
                c_m15_ema = c_m15.copy()
                c_m15_ema['ema200'] = c_m15_ema['close'].ewm(span=200).mean()
                c_m15_ema['ema20'] = c_m15_ema['close'].ewm(span=20).mean()
                last, prev = c_m15_ema.iloc[-1], c_m15_ema.iloc[-2]
                
                if last['close'] > last['ema200'] and prev['low'] <= prev['ema20'] and last['close'] > last['ema20']:
                    trend = "bullish"; entered = True
                elif last['close'] < last['ema200'] and prev['high'] >= prev['ema20'] and last['close'] < last['ema20']:
                    trend = "bearish"; entered = True
                rr = 2.5
                
            elif strategy == "SNIPER":
                c_h4 = h4[h4['time'] < t].tail(100)
                obs = self.analyzer.find_order_blocks(c_h4)
                if not obs: continue
                last_ob = obs[-1]
                in_zone = (price <= last_ob['top'] + 20*p) and (price >= last_ob['bottom'] - 20*p)
                z = self.analyzer.get_z_score(c_m15)
                c_dxy = dxy_full[dxy_full['time'] < t].tail(100)
                dxy_trend = self.analyzer.get_dxy_trend(c_dxy)
                
                if in_zone and last_ob['type'] == 'bullish' and z < -1.5 and dxy_trend == 'bearish':
                    trend = "bullish"; entered = True
                elif in_zone and last_ob['type'] == 'bearish' and z > 1.5 and dxy_trend == 'bullish':
                    trend = "bearish"; entered = True
                rr = 2.0

            if entered:
                atr = self.analyzer.calculate_atr(c_m15)
                sl_d = atr * 2.0
                tp_d = sl_d * rr
                
                trade = {'t': t, 's': symbol, 'p': price, 'res': 'Open', 'ret': 0}
                sl = price - sl_d if trend == "bullish" else price + sl_d
                tp = price + tp_d if trend == "bullish" else price - tp_d
                
                for j in range(i+1, len(m15)):
                    b = m15.iloc[j]
                    if trend == "bullish":
                        if b['low'] <= sl: trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                        if b['high'] >= tp: trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * rr; break
                    else:
                        if b['high'] >= sl: trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                        if b['low'] <= tp: trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * rr; break
                
                if trade['res'] != 'Open':
                    self.all_trades.append(trade)
                    i += 60

    def report_and_plot(self):
        balance = self.config["INITIAL_BALANCE"]
        history = [balance]
        times = [datetime.now()] # Placeholder for start
        
        wins = 0
        for tr in self.all_trades:
            balance *= (1 + tr['ret'])
            history.append(balance)
            times.append(tr['t'])
            if tr['res'] == 'Win': wins += 1
            
        print(f"Total Trades: {len(self.all_trades)}")
        print(f"Win Rate:     {(wins/len(self.all_trades)*100 if self.all_trades else 0):.1f}%")
        print(f"Final Balance: ${balance:,.2f}")
        print(f"Net Profit:   ${(balance - self.config['INITIAL_BALANCE']):,.2f}")
        
        plt.figure(figsize=(12, 6))
        plt.plot(history, color='#00ff88', linewidth=2)
        plt.title(f"Jarvis Alpha Multi-Strategy Performance ($1000 Bank)", color='white', pad=20)
        plt.ylabel("Account Balance ($)", color='white')
        plt.grid(True, alpha=0.2, color='gray')
        plt.gca().set_facecolor('#1a1a1a')
        plt.gcf().set_facecolor('#1a1a1a')
        plt.tick_params(colors='white')
        
        # Save plot
        plot_path = r"c:\Users\tiago\OneDrive\Área de Trabalho\PROJETO_JARVIS_FOREX\performance_chart.png"
        plt.savefig(plot_path)
        print(f"Chart saved to: {plot_path}")

    def monte_carlo(self, iterations=1000):
        if not self.all_trades: return
        returns = [t['ret'] for t in self.all_trades]
        finals = []
        for _ in range(iterations):
            b = self.config["INITIAL_BALANCE"]
            sim = random.choices(returns, k=len(returns))
            for r in sim: b *= (1 + r)
            finals.append(b)
        
        print("\nMonte Carlo (1000 Runs):")
        print(f"  Probability of Profit: {len([b for b in finals if b > self.config['INITIAL_BALANCE']])/iterations*100:.1f}%")
        print(f"  Avg Final Balance:     ${np.mean(finals):,.2f}")
        print(f"  Worst Case Scenario:   ${np.min(finals):,.2f}")

if __name__ == "__main__":
    FinalAlphaAudit(CONFIG_BT).run()
