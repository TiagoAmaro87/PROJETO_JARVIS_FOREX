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
    "RISK_PER_TRADE_PCT": 0.01,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
}

class HyperPSTAudit:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_trades = []

    def get_rsi_series(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS HYPER-SELECT PST FINAL AUDIT ($1000 BANK)".center(50, "="))
        
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol)
        
        self.all_trades.sort(key=lambda x: x['t'])
        self.report_and_plot()

    def backtest_symbol(self, symbol):
        df = self.api.get_rates(symbol, mt5.TIMEFRAME_M15, n=5000)
        if df.empty: return
        
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema10'] = df['close'].ewm(span=10).mean()
        rsi = self.get_rsi_series(df)
        atr_series = self.analyzer.calculate_atr_series(df)
        p = mt5.symbol_info(symbol).point
        
        for i in range(200, len(df)-50):
            row = df.iloc[i]
            t = row['time']
            
            # 1. Friday Switch
            if t.weekday() == 4 and t.hour >= 16: continue
            # 2. Peak Hours
            if not (8 <= t.hour <= 16): continue
            # 3. ATR Guard
            curr_atr = atr_series.iloc[i]
            if curr_atr > atr_series.iloc[i-14:i].mean() * 2.0: continue

            side = ""
            if row['close'] > row['ema200'] and row['low'] <= row['ema10'] and rsi.iloc[i] < 35:
                side = "BUY"
            elif row['close'] < row['ema200'] and row['high'] >= row['ema10'] and rsi.iloc[i] > 65:
                side = "SELL"

            if side:
                sl_dist = atr_series.iloc[i] * 1.5
                if sl_dist < 100*p: sl_dist = 100*p
                tp_dist = sl_dist * 4.0
                
                trade = {'t': t, 's': symbol, 'p': row['close'], 'res': 'Open', 'ret': 0, 'end_t': None}
                sl = row['close'] - sl_dist if side == "BUY" else row['close'] + sl_dist
                tp = row['close'] + tp_dist if side == "BUY" else row['close'] - tp_dist
                
                for j in range(i+1, len(df)):
                    b = df.iloc[j]
                    if side == "BUY":
                        if b['low'] <= sl: trade['res'] = 'Loss'; trade['ret'] = -0.01; trade['end_t'] = b['time']; break
                        if b['high'] >= tp: trade['res'] = 'Win'; trade['ret'] = 0.04; trade['end_t'] = b['time']; break
                    else:
                        if b['high'] >= sl: trade['res'] = 'Loss'; trade['ret'] = -0.01; trade['end_t'] = b['time']; break
                        if b['low'] <= tp: trade['res'] = 'Win'; trade['ret'] = 0.04; trade['end_t'] = b['time']; break
                
                if trade['res'] != 'Open':
                    self.all_trades.append(trade)
                    i += 100

    def report_and_plot(self):
        # 4. GLOBAL CORRELATION LOCK
        filtered = []
        last_end = None
        for tr in self.all_trades:
            if last_end is None or tr['t'] > last_end:
                filtered.append(tr)
                last_end = tr['end_t']

        balance = 1000.0
        history = [balance]
        wins = 0
        for tr in filtered:
            balance *= (1 + tr['ret'])
            history.append(balance)
            if tr['res'] == 'Win': wins += 1
            
        print(f"Total Unique Trades: {len(filtered)}")
        print(f"Win Rate:            {wins/len(filtered)*100 if filtered else 0:.1f}%")
        print(f"Final Balance:      ${balance:,.2f}")
        print(f"Total Net PNL:      {((balance-1000)/1000)*100:>+6.2f}%")
        
        plt.figure(figsize=(10, 5))
        plt.plot(history, color='#00ff88', linewidth=2)
        plt.title("Jarvis Hyper-Select PST Performance ($1000 Bank)")
        plt.grid(True, alpha=0.2)
        plt.savefig(r"c:\Users\tiago\OneDrive\Área de Trabalho\PROJETO_JARVIS_FOREX\hyper_pst_final_chart.png")

if __name__ == "__main__":
    HyperPSTAudit(CONFIG_BT).run()
