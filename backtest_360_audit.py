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
    "SYMBOLS": ["GBPUSD", "USDJPY", "AUDUSD", "USDCHF"], # EURUSD REMOVED
    "TF_H4": mt5.TIMEFRAME_H4, "TF_M15": mt5.TIMEFRAME_M15, "TF_M5": mt5.TIMEFRAME_M5,
    "MT5_PATH": "C:\\Users\\tiago\\Desktop\\MT5_JARVIS_FOREX\\terminal64.exe",
    "MT5_LOGIN": 5047550183, "MT5_PASSWORD": "UiS!6mBq", "MT5_SERVER": "MetaQuotes-Demo",
    "RISK_PER_TRADE_PCT": 0.005,
}

logging.basicConfig(level=logging.ERROR)

class BacktestTotalBlindspot:
    def __init__(self, config):
        self.config = config
        self.api = MT5Interface(config)
        self.analyzer = MarketAnalyzer(config)
        self.all_returns = []
        self.results = []

    def run(self):
        if not self.api.connect(): return
        print("\n" + "JARVIS 360º BLINDSPOT AUDIT".center(50, "="))
        
        # Load DXY for master filtering
        dxy_data = self.api.get_rates("USDX", self.config["TF_M15"], n=4500)
        
        for symbol in self.config["SYMBOLS"]:
            self.backtest_symbol(symbol, dxy_data)
        
        self.report()
        self.monte_carlo_comprehensive()

    def backtest_symbol(self, symbol, dxy_full):
        m15 = self.api.get_rates(symbol, self.config["TF_M15"], n=4000)
        h4 = self.api.get_rates(symbol, self.config["TF_H4"], n=1000)
        m5 = self.api.get_rates(symbol, self.config["TF_M5"], n=6000)
        d1 = self.api.get_rates(symbol, mt5.TIMEFRAME_D1, n=50)
        
        if m15.empty or dxy_full.empty: return

        trades = []
        p = mt5.symbol_info(symbol).point
        buf = 30 * p 

        for i in range(300, len(m15) - 40):
            t = m15['time'].iloc[i]
            
            # ELITE RULE 1: Session Filter
            if not self.analyzer.is_trading_session_logic(t): continue # Static logic helper
            
            price = m15['close'].iloc[i]

            # ELITE RULE 2: ADR Exhaustion
            c_d1 = d1[d1['time'] < t].tail(5)
            if self.analyzer.is_adr_exhausted(c_d1, price): continue

            # NEW: DXY Master Filter
            c_dxy = dxy_full[dxy_full['time'] < t].tail(100)
            dxy_trend = self.analyzer.get_dxy_trend(c_dxy)

            c_h4 = h4[h4['time'] < t].tail(100)
            c_m15 = m15.iloc[i-200:i+1]
            c_m5 = m5[m5['time'] < t].tail(50)
            if c_h4.empty or c_m5.empty: continue

            obs = self.analyzer.find_order_blocks(c_h4)
            last_ob = obs[-1] if obs else None
            z = self.analyzer.get_z_score(c_m15)
            mss = self.analyzer.detect_mss(c_m5)

            if last_ob:
                in_zone = (price <= last_ob['top'] + buf) and (price >= last_ob['bottom'] - buf)
                
                if in_zone and mss == last_ob['type']:
                    # DXY Alignment check
                    is_usd_base = symbol.startswith("USD")
                    dxy_aligned = False
                    if mss == 'bullish':
                        dxy_aligned = (dxy_trend == 'bullish') if is_usd_base else (dxy_trend == 'bearish')
                    else:
                        dxy_aligned = (dxy_trend == 'bearish') if is_usd_base else (dxy_trend == 'bullish')

                    if dxy_aligned and abs(z) > 1.2:
                        atr = self.analyzer.calculate_atr(c_m15)
                        sl_d = atr * 2.0
                        tp1_d = sl_d * 1.5
                        tp2_d = sl_d * 3.0
                        
                        trade = {
                            't': t, 'type': mss, 'p': price, 
                            'sl': price-sl_d if mss=='bullish' else price+sl_d,
                            'tp1': price+tp1_d if mss=='bullish' else price-tp1_d,
                            'tp2': price+tp2_d if mss=='bullish' else price-tp2_d,
                            'res1': 'Open', 'res2': 'Open'
                        }
                        
                        for j in range(i+1, len(m15)):
                            b = m15.iloc[j]
                            if trade['res1'] == 'Open':
                                if trade['type'] == 'bullish':
                                    if b['low'] <= trade['sl']: trade['res1'] = 'Loss'
                                    elif b['high'] >= trade['tp1']: trade['res1'] = 'Win'
                                else:
                                    if b['high'] >= trade['sl']: trade['res1'] = 'Loss'
                                    elif b['low'] <= trade['tp1']: trade['res1'] = 'Win'
                            
                            if trade['res2'] == 'Open':
                                cur_sl = trade['sl']
                                prof_dist = (b['high']-trade['p']) if trade['type']=='bullish' else (trade['p']-b['low'])
                                if prof_dist >= sl_d: cur_sl = trade['p'] # BE

                                if trade['type'] == 'bullish':
                                    if b['low'] <= cur_sl: trade['res2'] = 'Loss'
                                    elif b['high'] >= trade['tp2']: trade['res2'] = 'Win'
                                else:
                                    if b['high'] >= cur_sl: trade['res2'] = 'Loss'
                                    elif b['low'] <= trade['tp2']: trade['res2'] = 'Win'

                            if trade['res1'] != 'Open' and trade['res2'] != 'Open': break

                        ret1 = 0.0075 if trade['res1'] == 'Win' else -0.005 # 50% lot
                        ret2 = 0.015 if trade['res2'] == 'Win' else -0.005
                        if trade['res2'] == 'Loss' and prof_dist >= sl_d: ret2 = 0 # Breakeven hit

                        final_ret = ret1 + ret2
                        trades.append({'res': 'Win' if final_ret > 0 else 'Loss', 'ret': final_ret})
                        self.all_returns.append(final_ret)
                        i += 50

        self.results.append({'s': symbol, 'trades': trades})

    def report(self):
        all_t = []
        for r in self.results:
            wins = len([t for t in r['trades'] if t['res'] == 'Win'])
            pnl = sum([t['ret'] for t in r['trades']]) * 100
            print(f"{r['s'].ljust(10)} | {str(len(r['trades'])).ljust(3)} trades | PNL: {pnl:>+6.2f}%")
            all_t.extend(r['trades'])
        
        tw = len([t for t in all_t if t['res'] == 'Win'])
        gpnl = sum([t['ret'] for t in all_t]) * 100
        print("-" * 50)
        print(f"GLOBAL DXY-SYNCED | Trades: {len(all_t)} | Win Rate: {(tw/len(all_t)*100 if all_t else 0):.1f}% | Net PNL: {gpnl:.2f}%")
        print("=" * 50 + "\n")

    def monte_carlo_comprehensive(self, iterations=2000):
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
        avg_ret = (np.mean(final_balances) - initial) / initial * 100
        print(f"  Probability of Profit:  {prob_prof:.1f}%")
        print(f"  Expectancy (Monthly):   {avg_ret:>+6.2f}%")
        print(f"  Max Possible (Best Case): ${np.max(final_balances):,.2f}")
        print(f"  Min Possible (Worst Case):${np.min(final_balances):,.2f}")
        print("=" * 50 + "\n")

# Patch analyzer for static session check in BT
def is_trading_session_logic(self, t):
    return 7 <= t.hour <= 20
MarketAnalyzer.is_trading_session_logic = is_trading_session_logic

if __name__ == "__main__":
    BacktestTotalBlindspot(CONFIG_BT).run()
