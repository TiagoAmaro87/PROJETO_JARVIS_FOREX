import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import random
import matplotlib.pyplot as plt
from market_analyzer import MarketAnalyzer
from mt5_interface import MT5Interface

CONFIG_BT = {
    "SYMBOLS": ["GBPUSD", "EURUSD"],
    "INITIAL_BALANCE": 1000.0,
    "RISK_PER_TRADE_PCT": 0.01, # 1% for higher growth on small bank
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
}

class HolyGrailAudit:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_trades = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS HOLY GRAIL AUDIT ($1000 BANK)".center(50, "="))
        
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol)
        
        self.all_trades.sort(key=lambda x: x['t'])
        self.report_and_plot()

    def backtest_symbol(self, symbol):
        df = self.api.get_rates(symbol, mt5.TIMEFRAME_M15, n=5000)
        if df.empty: return
        
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        # RSI for extra filter
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + gain/loss))

        p = mt5.symbol_info(symbol).point
        
        for i in range(200, len(df)-50):
            row = df.iloc[i]
            t = row['time']
            # London/NY Peak only (08:00 - 16:00 UTC)
            if not (8 <= t.hour <= 16): continue
            
            entered = False
            side = ""
            
            # SUPER FILTER: Trend + RSI Exhaustion on Pullback
            if row['close'] > row['ema200'] and row['low'] <= row['ema20'] and row['rsi'] < 40:
                side = "BUY"; entered = True
            elif row['close'] < row['ema200'] and row['high'] >= row['ema20'] and row['rsi'] > 60:
                side = "SELL"; entered = True

            if entered:
                sl_dist = abs(row['close'] - row['ema200']) # Deep SL for safety
                if sl_dist < 100*p: sl_dist = 100*p # Minimum SL
                
                tp_dist = sl_dist * 3.0 # High RR 1:3
                
                trade = {'t': t, 's': symbol, 'p': row['close'], 'res': 'Open', 'ret': 0}
                sl = row['close'] - sl_dist if side == "BUY" else row['close'] + sl_dist
                tp = row['close'] + tp_dist if side == "BUY" else row['close'] - tp_dist
                
                for j in range(i+1, len(df)):
                    b = df.iloc[j]
                    if side == "BUY":
                        if b['low'] <= sl: trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                        if b['high'] >= tp: trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * 3.0; break
                    else:
                        if b['high'] >= sl: trade['res'] = 'Loss'; trade['ret'] = -self.config["RISK_PER_TRADE_PCT"]; break
                        if b['low'] <= tp: trade['res'] = 'Win'; trade['ret'] = self.config["RISK_PER_TRADE_PCT"] * 3.0; break
                
                if trade['res'] != 'Open':
                    self.all_trades.append(trade)
                    i += 100 # Very selective

    def report_and_plot(self):
        balance = self.config["INITIAL_BALANCE"]
        history = [balance]
        wins = 0
        for tr in self.all_trades:
            balance *= (1 + tr['ret'])
            history.append(balance)
            if tr['res'] == 'Win': wins += 1
            
        print(f"Total Trades: {len(self.all_trades)}")
        print(f"Win Rate:     {(wins/len(self.all_trades)*100 if self.all_trades else 0):.1f}%")
        print(f"Final Balance: ${balance:,.2f}")
        
        plt.figure(figsize=(10, 5))
        plt.plot(history, color='#00ff88')
        plt.title("Jarvis Holy Grail ($1000 Bank)")
        plt.savefig(r"c:\Users\tiago\OneDrive\Área de Trabalho\PROJETO_JARVIS_FOREX\holy_grail_chart.png")

if __name__ == "__main__":
    HolyGrailAudit(CONFIG_BT).run()
