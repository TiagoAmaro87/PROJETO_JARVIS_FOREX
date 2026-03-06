import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
import time
from datetime import datetime

logger = logging.getLogger("JARVIS_MT5")

class MT5Interface:
    def __init__(self, config):
        self.config = config

    def connect(self):
        if not mt5.initialize(path=self.config['MT5_PATH']):
            logger.error(f"MT5 Init Failed: {mt5.last_error()}")
            return False
        
        authorized = mt5.login(
            self.config['MT5_LOGIN'], 
            password=self.config['MT5_PASSWORD'], 
            server=self.config['MT5_SERVER']
        )
        if authorized:
            logger.info("MT5 Interface Connected & Authenticated.")
            return True
        return False

    def get_rates(self, symbol, timeframe, n=500):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def send_order(self, symbol, order_type, volume, price, sl, tp, comment="Jarvis SMC"):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 987654,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order Failed: {result.comment} ({result.retcode})")
            return None
        return result

    def get_positions(self):
        return mt5.positions_get()

    def modify_position(self, ticket, sl, tp):
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        return mt5.order_send(request)
