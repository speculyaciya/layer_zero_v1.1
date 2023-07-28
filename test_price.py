import ccxt
from pprint import pprint

print('CCXT Version:', ccxt.__version__)

max_gas = 0.5

def form_max_by_chain(chain, _in):
    chain = chain.upper()
    if (chain == 'ARBITRUM' or
        chain == 'OPTIMISM' or 
        chain == 'ETHEREUM' ):
       symbol = 'ETH/USDT'
    elif chain == 'BSC':
        symbol = 'BNB/USDT'
    elif chain == 'POLYGON':
        symbol = 'MATIC/USDT'
    elif chain == 'AVALANCHE':
        symbol = 'AVAX/USDT'
    elif chain == 'FANTOM':
        symbol = 'FTM/USDT'
    else:
        raise Exception
    
    exchange = ccxt.binance()
    response = exchange.fetch_ohlcv(symbol,limit=1)
    return _in / response[0][3]


t= form_max_by_chain(
    chain = 'BSC',
    _in   = max_gas,
)
print(t)

t= form_max_by_chain(
    chain = 'Arbitrum',
    _in   = max_gas,
)
print(t)

chain = 'Polygon'
t= form_max_by_chain(
    chain = chain,
    _in   = max_gas,
)
print(t)

t= form_max_by_chain(
    chain = 'Avalanche',
    _in   = max_gas,
)
print(t)

t= form_max_by_chain(
    chain = 'Fantom',
    _in   = max_gas,
)
print(t)
