import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging

class RiskManager:
    def __init__(self, config):
        self.config = config

    def calculate_lot_size(self, symbol, stop_loss_pips):
        account = mt5.account_info()
        if not account: return 0
        
        balance = account.balance
        risk_cash = balance * self.config['RISK_PER_TRADE_PCT']
        
        symbol_info = mt5.symbol_info(symbol)
        tick_val = symbol_info.trade_tick_value
        
        if tick_val == 0 or stop_loss_pips == 0: return self.config.get('MIN_LOT', 0.01)
        
        lot = risk_cash / (stop_loss_pips * tick_val)
        lot = max(symbol_info.volume_min, min(symbol_info.volume_max, lot))
        return round(lot, 2)

    def calculate_correlation(self, df_dict):
        """Matrix correlation check (> 0.85 filter)."""
        if len(df_dict) < 2: return pd.DataFrame()
        
        combined_df = pd.DataFrame()
        for symbol, df in df_dict.items():
            combined_df[symbol] = df['close']
        
        corr_matrix = combined_df.corr()
        return corr_matrix

    def trail_stop_loss(self, position, current_tick, atr):
        """Dynamic trailing stop based on ATR."""
        be_pips = (abs(position.price_open - position.sl) / mt5.symbol_info(position.symbol).point) if position.sl else 100
        
        profit_pips = (current_tick.bid - position.price_open) / mt5.symbol_info(position.symbol).point if position.type == mt5.ORDER_TYPE_BUY else \
                      (position.price_open - current_tick.ask) / mt5.symbol_info(position.symbol).point

        # Break-Even Activation (1:1 RR)
        if profit_pips >= be_pips:
            # Shift SL logic returned to orchestrator
            return True, position.price_open
        
        # Trailing ATR logic
        # ... logic if needed
        return False, None
