import MetaTrader5 as mt5
import pandas as pd
import time
import logging
from jarvis_forex_core import JarvisMultiEngine, CONFIG

# Configuração do LOG para o Simulador
logging.basicConfig(level=logging.INFO, format='%(asctime)s | SIMULADOR | %(message)s')
logger = logging.getLogger("STUDY_MODULE")

class JarvisStudyModule(JarvisMultiEngine):
    def __init__(self):
        super().__init__()
        self.simulation_speed = 0.5 # Segundos entre cada candle simulado

    def run_study(self, symbol, days=3):
        if not self.mt5.connect(): return
        
        logger.info(f"--- INICIANDO MÓDULO DE ESTUDO: {symbol} ---")
        logger.info("Pegando dados históricos para reconstrução de cenário...")
        
        # Pega dados de M15 (onde o Gekko e Sniper operam)
        rates = self.mt5.get_rates(symbol, mt5.TIMEFRAME_M15, n=100)
        if rates.empty: 
            logger.error("Falha ao coletar dados.")
            return

        print("\n" + f" SIMULANDO MERCADO REAL EM {symbol} ".center(50, "="))
        
        # Simula a chegada de cada candle
        for i in range(50, len(rates)):
            current_candle = rates.iloc[i]
            timestamp = current_candle['time']
            price = current_candle['close']
            
            # Atualiza o "Cérebro" do Jarvis com o cenário daquele momento
            # Nota: No simulador, o process_symbol vai ler o histórico ATÉ este ponto i
            print(f"---> [HORA SIMULADA: {timestamp}] | PREÇO: {price:.5f}")
            
            strategy = CONFIG["ASSETS"].get(symbol)
            if strategy == "GEKKO":
                self.process_gekko_study(symbol, rates.iloc[:i+1])
            elif strategy == "SNIPER":
                self.process_sniper_study(symbol, rates.iloc[:i+1])
                
            time.sleep(self.simulation_speed)
            
        print("="*50 + "\nEstudo concluído. Verifique os logs acima para ver as decisões do Jarvis.")

    def process_gekko_study(self, symbol, sub_df):
        # Versão do process_gekko adaptada para o simulador
        sub_df = sub_df.copy()
        sub_df['ema200'] = sub_df['close'].ewm(span=200).mean()
        sub_df['ema20'] = sub_df['close'].ewm(span=20).mean()
        
        last = sub_df.iloc[-1]
        prev = sub_df.iloc[-2]
        
        if last['close'] > last['ema200'] and prev['low'] <= prev['ema20'] and last['close'] > last['ema20']:
            logger.info(f"TARGET: BUY SIGNAL DETECTED (Gekko Alpha) @ {last['close']:.5f}")
        elif last['close'] < last['ema200'] and prev['high'] >= prev['ema20'] and last['close'] < last['ema20']:
            logger.info(f"TARGET: SELL SIGNAL DETECTED (Gekko Alpha) @ {last['close']:.5f}")

    def process_sniper_study(self, symbol, sub_df):
        # Versão do sniper adaptada para estudo
        logger.info(f"Analisando Liquidez (SMC)... sem sinais no momento.")

if __name__ == "__main__":
    study = JarvisStudyModule()
    # Vamos rodar o estudo no GBPUSD (nosso par campeão)
    study.run_study("GBPUSD")
