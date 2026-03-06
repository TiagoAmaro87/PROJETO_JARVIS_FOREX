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

class PST_Audit:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_trades = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS PST BLINDSPOT AUDIT ($1000 BANK)".center(50, "="))
        
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol)
        
        # Sort trades by time to simulate global correlation lock accurately
        self.all_trades.sort(key=lambda x: x['t'])
        self.report_and_plot()

    def backtest_symbol(self, symbol):
        df = self.api.get_rates(symbol, mt5.TIMEFRAME_M15, n=5000)
        if df.empty: return
        
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        rsi = self.analyzer.get_rsi_series(df)
        atr_series = self.analyzer.calculate_atr_series(df)

        p = mt5.symbol_info(symbol).point
        
        for i in range(200, len(df)-50):
            row = df.iloc[i]
            t = row['time']
            
            # --- PST RULES ---
            # 1. Friday Kill-Switch
            if t.weekday() == 4 and t.hour >= 16: continue
            
            # 2. Session Peak
            if not (8 <= t.hour <= 16): continue
            
            # 3. ATR Spike Guard
            current_atr = atr_series.iloc[i]
            mean_atr = atr_series.iloc[i-14:i].mean()
            if current_atr > (mean_atr * 2.0): continue

            # --- HOLY GRAIL LOGIC ---
            entered = False
            side = ""
            if row['close'] > row['ema200'] and row['low'] <= row['ema20'] and rsi.iloc[i] < 40:
                side = "BUY"; entered = True
            elif row['close'] < row['ema200'] and row['high'] >= row['ema20'] and rsi.iloc[i] > 60:
                side = "SELL"; entered = True

            if entered:
                sl_dist = abs(row['close'] - row['ema200'])
                if sl_dist < 150*p: sl_dist = 150*p
                tp_dist = sl_dist * 3.0
                
                trade = {'t': t, 's': symbol, 'p': row['close'], 'res': 'Open', 'ret': 0, 'end_t': None}
                sl = row['close'] - sl_dist if side == "BUY" else row['close'] + sl_dist
                tp = row['close'] + tp_dist if side == "BUY" else row['close'] - tp_dist
                
                for j in range(i+1, len(df)):
                    b = df.iloc[j]
                    if side == "BUY":
                        if b['low'] <= sl: trade['res'] = 'Loss'; trade['ret'] = -0.01; trade['end_t'] = b['time']; break
                        if b['high'] >= tp: trade['res'] = 'Win'; trade['ret'] = 0.03; trade['end_t'] = b['time']; break
                    else:
                        if b['high'] >= sl: trade['res'] = 'Loss'; trade['ret'] = -0.01; trade['end_t'] = b['time']; break
                        if b['low'] <= tp: trade['res'] = 'Win'; trade['ret'] = 0.03; trade['end_t'] = b['time']; break
                
                if trade['res'] != 'Open':
                    self.all_trades.append(trade)
                    i += 40

    def report_and_plot(self):
        # Apply Correlation Lock: Only 1 trade active globally
        filtered_trades = []
        last_end_time = None
        
        for tr in self.all_trades:
            if last_end_time is None or tr['t'] > last_end_time:
                filtered_trades.append(tr)
                last_end_time = tr['end_t']

        balance = self.config["INITIAL_BALANCE"]
        history = [balance]
        wins = 0
        for tr in filtered_trades:
            balance *= (1 + tr['ret'])
            history.append(balance)
            if tr['res'] == 'Win': wins += 1
            
        print(f"Total Trades (with PST Lock): {len(filtered_trades)}")
        print(f"Win Rate:     {(wins/len(filtered_trades)*100 if filtered_trades else 0):.1f}%")
        print(f"Final Balance: ${balance:,.2f}")
        print(f"Profit Factor: {(wins*3)/ (len(filtered_trades)-wins) if (len(filtered_trades)-wins) > 0 else 'Inf':.2f}")
        
        plt.figure(figsize=(10, 5))
        plt.plot(history, color='#00ff88', label='Equity Curve')
        plt.title("Jarvis PST Protection Audit ($1000 Bank)")
        plt.grid(True, alpha=0.3)
        plt.savefig(r"c:\Users\tiago\OneDrive\Área de Trabalho\PROJETO_JARVIS_FOREX\pst_final_chart.png")

# Need to add rsi_series helper for cleaner BT
def get_rsi_series(self, df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
MarketAnalyzer.get_rsi_series = get_rsi_series

if __name__ == "__main__":
    PST_Audit(CONFIG_BT).run()
