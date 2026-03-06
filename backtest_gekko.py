import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from mt5_interface import MT5Interface

CONFIG_BT = {
    "SYMBOLS": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"], 
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
}

class TrendGekko:
    def __init__(self, config):
        self.api = MT5Interface(config)
        self.results = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS TREND-GEKKO AUDIT (EMA 200 + 20 Pullback)".center(50, "="))
        for symbol in ["EURUSD", "GBPUSD", "AUDUSD"]:
            self.backtest(symbol)
        
    def backtest(self, symbol):
        df = self.api.get_rates(symbol, mt5.TIMEFRAME_M15, n=5000)
        if df.empty: return
        
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        
        trades = []
        for i in range(200, len(df)-20):
            row = df.iloc[i]
            # Bullish Trend
            if row['close'] > row['ema200'] and row['low'] <= row['ema20'] and row['close'] > row['ema20']:
                # Pullback to EMA20 reached
                sl = row['low'] - 10 * mt5.symbol_info(symbol).point
                tp = row['close'] + (row['close'] - sl) * 2.5
                trades.append(self.simulate(df, i, "BUY", sl, tp))
            # Bearish Trend
            elif row['close'] < row['ema200'] and row['high'] >= row['ema20'] and row['close'] < row['ema20']:
                sl = row['high'] + 10 * mt5.symbol_info(symbol).point
                tp = row['close'] - (sl - row['close']) * 2.5
                trades.append(self.simulate(df, i, "SELL", sl, tp))
                
        wins = [t for t in trades if t == 1]
        wr = (len(wins)/len(trades)*100) if trades else 0
        # Net result using 1% risk per trade
        pnl = sum([0.025 if t == 1 else -0.01 for t in trades]) * 100
        print(f"{symbol.ljust(10)} | Trades: {len(trades):>3} | WR: {wr:>5.1f}% | PNL: {pnl:>+6.2f}%")

    def simulate(self, df, start_idx, side, sl, tp):
        for j in range(start_idx+1, len(df)):
            b = df.iloc[j]
            if side == "BUY":
                if b['low'] <= sl: return 0
                if b['high'] >= tp: return 1
            else:
                if b['high'] >= sl: return 0
                if b['low'] <= tp: return 1
        return 0

if __name__ == "__main__":
    TrendGekko(CONFIG_BT).run()
