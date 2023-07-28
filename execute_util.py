import main_config as c
import random
from execute import logger, csv_path, lock_data_csv, lock_log_csv
from swap import swap_token
from swap_settings import CHAIN_LIST as SWAP_CHAIN_LIST
from stargate_settings import CHAIN_LIST as STARGATE_CHAIN_LIST
from sushi_swap import sushi_swap_token
from stake_stg import stake_stg 
from testnet import testnet_bridge
from testnet_settings import SETTING_TESTNETBRIDGE_LIST as TESTNET_CHAIN_LIST
from btcbridge import bridge_btc
from traderjoe_swap import trade_avax_to_btc, trade_btc_to_avax
from aptos_bridge import aptos_bridge
from stargate import stargate
from harmony_bridge import harmony_bridge
from web3 import Web3
from decimal import Decimal
import ccxt
import pandas as pd
import datetime
import threading
import time

def form_STARGATE_chains(row)->list:
    chain_list = []
    for chain in c.STARGATE_CHAIN_LIST:
        if int(row[f'{c.STARGATE}_{chain.upper()}']) > 0:
            chain_list.append(chain)
    return chain_list

def save_log(activity, row, from_chain, to_chain, from_token, to_token, result):
    lock_log_csv.acquire()
    time.sleep(1)
    data_log_csv = pd.read_csv('log.csv',keep_default_na=False)
    data_log_csv.loc[len(data_log_csv.index)] = [
        datetime.datetime.now().strftime("%m.%d.%Y"),
        datetime.datetime.now().strftime("%H.%M.%S"),
        row["Name"],
        row["Wallet"],
        activity,
        from_chain,
        to_chain,
        from_token,
        to_token,
        result
        ] 
    data_log_csv.to_csv('log.csv', index=False)
    lock_log_csv.release()

def save_csv(data_csv, index):
    lock_data_csv.acquire()
    time.sleep(1)
    new_data_csv = pd.read_csv(csv_path,keep_default_na=False)
    new_data_csv.loc[index] = data_csv.loc[index]
    new_data_csv.to_csv(csv_path, index=False)
    lock_data_csv.release()

def form_activity_list(row) -> list:
    activity_list = []
    for activity in c.ACTIVITY_LIST:
        if row[activity] != 0:
            activity_list.append(activity)

    if len(form_STARGATE_chains(row)) != 0:
        activity_list.append(c.STARGATE)
    # if int(row[c.STARGATE_BSC]) != 0:
    #     activity_list.append(c.STARGATE_BSC)
    # if int(row[c.STARGATE_ARBITRUM]) != 0:
    #     activity_list.append(c.STARGATE_ARBITRUM)
    # if int(row[c.STARGATE_OPTIMISM]) != 0:
    #     activity_list.append(c.STARGATE_OPTIMISM)

    return activity_list

def generate_activity(row) -> str:
    activity_list = form_activity_list(row)
    if len(activity_list) != 0:
        return random.choice(activity_list)
    else:
        return c.NO_ACTIVITY

def from_prelog(row)->str:
       return f'{row["Name"]} | {row["Wallet"]}'

def get_max_data(activity):
    csv_path = 'max_setting.csv'
    data_csv = pd.read_csv(csv_path,keep_default_na=False)
    for index, row in data_csv.iterrows():
        if row['Activity'] == activity:
            return True, row['MAX_GAS'], row['MAX_VALUE']
    return False, '', ''

def form_max_by_chain(chain, usd):
    usd   = Decimal(float(usd))
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
    return float(usd) / response[0][3]

def generate_STARGATE_single(chain_in, row, proxy='')->dict({'status':bool, 'from_chain':str, 'to_chain':str, 'from_token':str, 'to_token':str}):
    _from_token = ''
    for chain in STARGATE_CHAIN_LIST:
        if chain_in != chain['chain']:
            continue
        RPC_FROM = chain['rpc']
        w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
        if w3_from.is_connected() == True:
            account = w3_from.eth.account.from_key(row['Private_key'])
            address = account.address
            for token in chain['token_list']:
                _from_token = ''
                contractTOKEN    = w3_from.eth.contract(address=w3_from.to_checksum_address(token['address']), abi=token['abi'])
                balance_of_token = contractTOKEN.functions.balanceOf(address).call()
                token_decimals   = contractTOKEN.functions.decimals().call()
                human_balance    = balance_of_token/ 10 ** token_decimals
                human_balance    = round(Decimal(human_balance), 6).real
                if human_balance > c.MIN_STABLE_FOUND:
                    _from_token = token['token']
                    break
        else:
            return {'status':False}
        if _from_token != '':
            _from_chain = chain['chain']
            _to_chain = random.choice(chain['chain_to'])
            for chain_to in STARGATE_CHAIN_LIST:
                if chain_to['chain'] == _to_chain:
                    _to_token = random.choice(chain_to['token_list'])['token']
                    return {
                        'status':True,
                        'from_chain':_from_chain, 
                        'to_chain':_to_chain, 
                        'from_token':_from_token, 
                        'to_token':_to_token}
            else:
                logger.error(f'Ошибка при generate_STARGATE_single - токенов для STARGATE_{chain_in} нет')
    return {'status':False}

def get_chain_with_usd(row, in_list, proxy=''):
    return_list = []
    for chain_execute in in_list:
        for chain in STARGATE_CHAIN_LIST:
            if chain_execute != chain['chain']:
                continue
            RPC_FROM = chain['rpc']
            w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
            if w3_from.is_connected() == True:
                account = w3_from.eth.account.from_key(row['Private_key'])
                address = account.address
                for token in chain['token_list']:
                    contractTOKEN    = w3_from.eth.contract(address=w3_from.to_checksum_address(token['address']), abi=token['abi'])
                    balance_of_token = contractTOKEN.functions.balanceOf(address).call()
                    token_decimals   = contractTOKEN.functions.decimals().call()
                    human_balance    = balance_of_token/ 10 ** token_decimals
                    human_balance    = round(Decimal(human_balance), 6).real
                    if human_balance > c.MIN_STABLE_FOUND:
                        return_list.append(chain['chain'])
                        break
    return return_list
            
def generate_STARGATE(row, proxy='')->dict({'status':bool, 'from_chain':str, 'to_chain':str, 'from_token':str, 'to_token':str}):
    prelog = from_prelog(row)
    _from_chain = ''
    _from_token = ''
    chain_list = form_STARGATE_chains(row)
    chain_with_usd = get_chain_with_usd(row, chain_list)
    random.shuffle(chain_with_usd)
    if len(chain_with_usd) == 0:
        logger.warning(f'{prelog} | Ошибка при generate_STARGATE - токенов USD нет в сетях, в которых нужно сделать STARGATE {chain_list}, пробуем найти другие сети')
        for chain_execute in c.STARGATE_CHAIN_LIST:
            for chain in STARGATE_CHAIN_LIST:
                if chain_execute != chain['chain']:
                    continue
                RPC_FROM = chain['rpc']
                w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
                if w3_from.is_connected() == True:
                    account = w3_from.eth.account.from_key(row['Private_key'])
                    address = account.address
                    for token in chain['token_list']:
                        contractTOKEN    = w3_from.eth.contract(address=w3_from.to_checksum_address(token['address']), abi=token['abi'])
                        balance_of_token = contractTOKEN.functions.balanceOf(address).call()
                        token_decimals   = contractTOKEN.functions.decimals().call()
                        human_balance    = balance_of_token/ 10 ** token_decimals
                        human_balance    = round(Decimal(human_balance), 6).real
                        if human_balance > c.MIN_STABLE_FOUND:
                            _from_chain = chain['chain']
                            _from_token = token['token'] 
                            break
                if _from_token != '' and _from_chain != '':
                    break
            if _from_token != '' and _from_chain != '':
                break   
    else:
        for chain_execute in chain_with_usd:
            for chain in STARGATE_CHAIN_LIST:
                if chain_execute != chain['chain']:
                    continue
                RPC_FROM = chain['rpc']
                w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
                if w3_from.is_connected() == True:
                    account = w3_from.eth.account.from_key(row['Private_key'])
                    address = account.address
                    for token in chain['token_list']:
                        _from_token = ''
                        contractTOKEN    = w3_from.eth.contract(address=w3_from.to_checksum_address(token['address']), abi=token['abi'])
                        balance_of_token = contractTOKEN.functions.balanceOf(address).call()
                        token_decimals   = contractTOKEN.functions.decimals().call()
                        human_balance    = balance_of_token/ 10 ** token_decimals
                        human_balance    = round(Decimal(human_balance), 6).real
                        if human_balance > c.MIN_STABLE_FOUND:
                            _from_chain = chain['chain']
                            _from_token = token['token']
                            break
                else:
                    return {'status':False}
                if _from_token != '' and _from_chain != '':
                    break
            if _from_token != '' and _from_chain != '':
                break   
    if _from_token != '' and _from_chain != '':
        while True:
            _to_chain = random.choice(chain_list)
            if (len(chain_list) == 1 and _to_chain == _from_chain ):
                _to_chain = random.choice(c.STARGATE_CHAIN_LIST)
            if _to_chain != _from_chain:
                break
        for chain_to in STARGATE_CHAIN_LIST:
            if chain_to['chain'] == _to_chain:
                _to_token = random.choice(chain_to['token_list'])['token']
                return {
                    'status':True,
                    'from_chain':_from_chain, 
                    'to_chain':_to_chain, 
                    'from_token':_from_token, 
                    'to_token':_to_token}
    else:
        logger.error(f'{prelog} | Ошибка при generate_STARGATE - токенов USD нет в {c.STARGATE_CHAIN_LIST}')
        return {'status':False}


def execute_STARGATE_single_chain(chain, data_csv, row, index, proxy=''):
    prelog = from_prelog(row)

    if row[f'{c.STARGATE}_{chain.upper()}_FIRST_SWAP'] != 'DONE':
        from_chain = chain
        if from_chain == 'BSC':
            token = 'USDT'
        elif (from_chain == 'Optimism' or from_chain == 'Arbitrum'):
            token = 'USDC'
        logger.info(f'{prelog} | Первый раз {c.STARGATE}_{chain.upper()}, будет SWAP {from_chain} для получения {token}')
        try:
            amount_range      = str(row[f'{c.STARGATE}_{chain.upper()}_RANGE']).split(',')
            amount_range_from = float(str(amount_range[0]).replace(' ', ''))
            amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
            amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
            amount            = form_max_by_chain(chain=from_chain, usd=amount)
        except:
            logger.error(f'{prelog} | Ошибка при поиске суммы {c.STARGATE}_{chain.upper()} для сети {from_chain}')
            return False 
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
            return False 
        max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
        result = swap_token(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            from_chain  = from_chain,
            token       = token,
            amount      = amount,
            max_gas     = max_gas,
            )
        if result == False:
            logger.error(f'{prelog} | Ошибка при {c.SWAP_TOKEN}_{from_chain.upper()}')
            save_log(
                activity   = c.SWAP_TOKEN,
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = '',
                to_token   = token, 
                result     = False,
            )    
            return False
        else:
            logger.success(f'{prelog} | Успешный {c.SWAP_TOKEN}_{from_chain.upper()}, {from_chain} {token} {amount}')
            data_csv.loc[index,f'{c.STARGATE}_{chain.upper()}_FIRST_SWAP'] = 'DONE'
            save_csv(data_csv, index)
            save_log(
                activity   = c.SWAP_TOKEN,
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = '',
                to_token   = token, 
                result     = True,
            )    

    generate_data = generate_STARGATE_single(chain_in=chain, row=row)
    if generate_data['status'] == False:
        logger.error(f'{prelog} | Ошибка при генерации пути {c.STARGATE}')
        return False  
    from_chain = generate_data['from_chain']
    to_chain   = generate_data['to_chain']
    from_token = generate_data['from_token']
    to_token   = generate_data['to_token']
    result_max_data, max_gas, max_value = get_max_data(activity=f'{c.STARGATE}_{from_chain.upper()}_{to_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.STARGATE}_{from_chain.upper()}_{to_chain.upper()}')
        return False 
    max_gas    = form_max_by_chain(chain=from_chain, usd=max_gas)
    max_value  = form_max_by_chain(chain=from_chain, usd=max_value)
    logger.info(f'{prelog} | {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
    
    for chain_execute in STARGATE_CHAIN_LIST:
        if chain != chain_execute['chain']:
            continue
        RPC_FROM = chain_execute['rpc']
        w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
        if w3_from.is_connected() == True:
            account = w3_from.eth.account.from_key(row['Private_key'])
            address = account.address
            for token in chain_execute['token_list']:
                if from_token == token['token']:
                    contractTOKEN    = w3_from.eth.contract(address=w3_from.to_checksum_address(token['address']), abi=token['abi'])
                    balance_of_token = contractTOKEN.functions.balanceOf(address).call()
                    token_decimals   = contractTOKEN.functions.decimals().call()
                    amount_stargate  = int(balance_of_token * c.RATIO_STARGATE_SINGLE)
                    amount_stargate  = amount_stargate/ 10 ** token_decimals
                    amount_stargate  = round(Decimal(amount_stargate), 6).real
                    break

    result = stargate(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        amount      = amount_stargate,
        from_chain  = from_chain, 
        to_chain    = to_chain, 
        from_token  = from_token,
        to_token    = to_token, 
        max_gas     = max_gas,
        max_value   = max_value,
        slippage    = 50,
    )
    if result == True:
        logger.success(f'{prelog} | Успешно {c.STARGATE}_{from_chain.upper()} {from_chain} to {to_chain} {from_token} to {to_token}')
        data_csv.loc[index,f'{c.STARGATE}'] = int(data_csv.loc[index,f'{c.STARGATE}']) + 1
        data_csv.loc[index,f'{c.STARGATE}_{from_chain.upper()}'] = int(data_csv.loc[index,f'{c.STARGATE}_{from_chain.upper()}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity   = c.STARGATE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = to_chain, 
            from_token = from_token,
            to_token   = to_token, 
            result     = True,
        )    
        return True
    else:
        logger.error(f'{prelog} | Ошибка {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
        save_log(
            activity   = c.STARGATE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = to_chain, 
            from_token = from_token,
            to_token   = to_token, 
            result     = False,
        )    
        return False
    
def execute_STARGATE(data_csv, row, index):
    prelog = from_prelog(row)

    if row[f'{c.STARGATE}_FIRST_SWAP'] != 'DONE':
        from_chain = random.choice(form_STARGATE_chains(row))
        if (from_chain == 'Avalanche' or from_chain == 'Polygon'):
            token = 'USDT'
        elif (from_chain == 'Fantom' or from_chain == 'Oprimism' or from_chain == 'Arbitrum'):
            token = 'USDC'
        logger.info(f'{prelog} | Первый раз {c.STARGATE}, будет SWAP {from_chain} для получения {token}')
        try:
            amount_range      = str(row[f'{c.STARGATE}_RANGE']).split(',')
            amount_range_from = float(str(amount_range[0]).replace(' ', ''))
            amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
            amount            = round(random.uniform(amount_range_from, amount_range_to), 3)
            amount            = form_max_by_chain(chain=from_chain, usd=amount)
        except:
            logger.error(f'{prelog} | Ошибка при поиске суммы {c.STARGATE} для сети {from_chain}')
            return False 
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
            return False 
        max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
        result = swap_token(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            from_chain  = from_chain,
            token       = token,
            amount      = amount,
            max_gas     = max_gas,
            )
        if result == False:
            logger.error(f'{prelog} | Ошибка при {c.SWAP_TOKEN}_{from_chain.upper()}')
            save_log(
                activity = c.SWAP_TOKEN,
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = '',
                to_token   = token, 
                result     = False,
            )   
            return False
        else:
            logger.success(f'{prelog} | Успешный {c.SWAP_TOKEN}_{from_chain.upper()}, {from_chain} {token} {amount}')
            data_csv.loc[index,f'{c.STARGATE}_FIRST_SWAP'] = 'DONE'
            save_csv(data_csv, index)
            save_log(
                activity = c.SWAP_TOKEN,
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = '',
                to_token   = token, 
                result     = True,
            )   

    generate_data = generate_STARGATE(row=row)
    if generate_data['status'] == False:
        logger.error(f'{prelog} | Ошибка при генерации пути {c.STARGATE}')
        return False  
    from_chain = generate_data['from_chain']
    to_chain   = generate_data['to_chain']
    from_token = generate_data['from_token']
    to_token   = generate_data['to_token']
    logger.info(f'{prelog} | Запланировано {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
    result_max_data, max_gas, max_value = get_max_data(activity=f'{c.STARGATE}_{from_chain.upper()}_{to_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.STARGATE}_{from_chain.upper()}_{to_chain.upper()}')
        return False 
    max_gas    = form_max_by_chain(chain=from_chain, usd=max_gas)
    max_value  = form_max_by_chain(chain=from_chain, usd=max_value)
    logger.info(f'{prelog} | {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
    result = stargate(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        amount      = 'ALL',
        from_chain  = from_chain, 
        to_chain    = to_chain, 
        from_token  = from_token,
        to_token    = to_token, 
        max_gas     = max_gas,
        max_value   = max_value,
        slippage    = 50,
    )
    if result == True:
        logger.success(f'{prelog} | Успешно {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
        data_csv.loc[index,f'{c.STARGATE}'] = int(data_csv.loc[index,f'{c.STARGATE}']) + 1
        data_csv.loc[index,f'{c.STARGATE}_{from_chain.upper()}'] = int(data_csv.loc[index,f'{c.STARGATE}_{from_chain.upper()}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity   = c.STARGATE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = to_chain, 
            from_token = from_token,
            to_token   = to_token, 
            result     = True,
        )    
        return True
    else:
        logger.error(f'{prelog} | Ошибка {c.STARGATE} {from_chain} to {to_chain} {from_token} to {to_token}')
        save_log(
            activity   = c.STARGATE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = to_chain, 
            from_token = from_token,
            to_token   = to_token, 
            result     = False,
        )    
        return False
    
def execute_SWAP_TOKEN(data_csv, row, index):
    prelog = from_prelog(row)
    chain_list = str(row[f'{c.SWAP_TOKEN}_CHAINS']).split(',')
    from_chain = str(random.choice(chain_list)).replace(' ', '')
    logger.info(f'{prelog} | {c.SWAP_TOKEN} выбрана сеть {from_chain}')
    for chain in SWAP_CHAIN_LIST:
        if from_chain != chain['chain']:
            continue
        token = random.choice(chain['token_list'])['token']
        break
    if token == '':
        logger.error(f'{prelog} | Ошибка при поиске токена {c.SWAP_TOKEN} для сети {from_chain}')
        return False 
    logger.info(f'{prelog} | {c.SWAP_TOKEN}, будет SWAP {from_chain} для получения {token}')
    try:
        amount_range      = str(row[f'{c.SWAP_TOKEN}_RANGE']).split(',')
        amount_range_from = float(str(amount_range[0]).replace(' ', ''))
        amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
        amount            = round(random.uniform(amount_range_from, amount_range_to), 3)
        amount            = form_max_by_chain(chain=from_chain, usd=amount)
    except:
        logger.error(f'{prelog} | Ошибка при поиске суммы {c.SWAP_TOKEN} для сети {from_chain}')
        return False 
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    logger.info(f'{prelog} | {c.SWAP_TOKEN} {from_chain} {token} {amount}')
    result = swap_token(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        token       = token,
        amount      = amount,
        max_gas     = max_gas,
        )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.SWAP_TOKEN}_{from_chain.upper()}')
        save_log(
            activity   = c.SWAP_TOKEN,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = result,
        )    
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.SWAP_TOKEN}_{from_chain.upper()}, {from_chain} {token} {amount}')
        data_csv.loc[index,f'{c.SWAP_TOKEN}'] = int(data_csv.loc[index,f'{c.SWAP_TOKEN}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity   = c.SWAP_TOKEN,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = result,
        ) 

        return result

def execute_TESTNET_BRIDGE(data_csv, row, index):
    prelog = from_prelog(row)
    chain_list = str(row[f'{c.TESTNET_BRIDGE}_CHAINS']).split(',')
    from_chain = str(random.choice(chain_list)).replace(' ', '')
    logger.info(f'{prelog} | {c.TESTNET_BRIDGE} выбрана сеть {from_chain}')
    try:
        amount_range      = str(row[f'{c.TESTNET_BRIDGE}_RANGE']).split(',')
        amount_range_from = float(str(amount_range[0]).replace(' ', ''))
        amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
        amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
        amount            = form_max_by_chain(chain=from_chain, usd=amount)
    except:
        logger.error(f'{prelog} | Ошибка при поиске суммы {c.TESTNET_BRIDGE} для сети {from_chain}')
        return False 
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.TESTNET_BRIDGE}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.TESTNET_BRIDGE}_{from_chain.upper()}')
        return False 
    max_gas   = form_max_by_chain(chain=from_chain, usd=max_gas)
    max_value = form_max_by_chain(chain=from_chain, usd=max_value)
    logger.info(f'{prelog} | {c.TESTNET_BRIDGE} {from_chain} {amount}')
    result = testnet_bridge(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        max_bridge  = amount,
        max_value   = max_value,
        max_gas     = max_gas,
    )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.TESTNET_BRIDGE} {from_chain}')
        save_log(
            activity   = c.TESTNET_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = 'ETH',
            to_token   = 'GOERLIETH ETH', 
            result     = result,
        )    
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.TESTNET_BRIDGE} {from_chain}, {from_chain} {amount}')
        data_csv.loc[index,f'{c.TESTNET_BRIDGE}'] = int(data_csv.loc[index,f'{c.TESTNET_BRIDGE}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity   = c.TESTNET_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = 'ETH',
            to_token   = 'GOERLIETH ETH', 
            result     = result,
        ) 
        return result

def execute_BTC_BRIDGE(data_csv, row, index):
    prelog = from_prelog(row)

    if str(row[f'{c.BTC_BRIDGE}_STEP']) == '':
        from_chain = 'Avalanche'
        logger.info(f'{prelog} | {c.BTC_BRIDGE} 1 шаг, свап AVAX на BTC.b в TRADERJOE')
        try:
            amount_range      = str(row[f'{c.BTC_BRIDGE}_RANGE']).split(',')
            amount_range_from = float(str(amount_range[0]).replace(' ', ''))
            amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
            amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
            amount            = form_max_by_chain(chain=from_chain, usd=amount)
        except:
            logger.error(f'{prelog} | Ошибка при поиске суммы {c.BTC_BRIDGE} для сети {from_chain}')
            return False 
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.BTC_BRIDGE}_TRADERJOE_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.BTC_BRIDGE}_TRADERJOE_{from_chain.upper()}')
            return False 
        max_gas   = form_max_by_chain(chain=from_chain, usd=max_gas)

        result = trade_avax_to_btc(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            value       = amount,
            max_gas     = max_gas
        )
        if result == True:
            logger.success(f'{prelog} | Успешный TRADERJOE {from_chain} {amount}')
            data_csv.loc[index,f'{c.BTC_BRIDGE}_STEP'] = 'X'
            save_csv(data_csv, index)
            save_log(
                activity   = 'TRADERJOE',
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = 'AVAX',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        else:
            logger.error(f'{prelog} | Ошибка при TRADERJOE {from_chain} {amount}')
            save_log(
                activity   = 'TRADERJOE',
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = 'AVAX',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        return result
    if str(row[f'{c.BTC_BRIDGE}_STEP']) == 'X':
        from_chain = 'Avalanche'
        to_chain   = 'Polygon'
        logger.info(f'{prelog} | {c.BTC_BRIDGE} 2 шаг, BTC BRIDGE {from_chain} to {to_chain}')
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.BTC_BRIDGE}_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.BTC_BRIDGE}_{from_chain.upper()}')
            return False 
        max_gas   = form_max_by_chain(chain=from_chain, usd=max_gas)
        max_value = form_max_by_chain(chain=from_chain, usd=max_value)
        result = bridge_btc(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            from_chain  = from_chain,
            to_chain    = to_chain,
            max_bridge  = 'ALL',
            max_gas     = max_gas,
            max_value   = max_value,
        )
        if result == True:
            logger.success(f'{prelog} | Успешный {c.BTC_BRIDGE} {from_chain} to {to_chain}')
            data_csv.loc[index,f'{c.BTC_BRIDGE}_STEP'] = 'XX'
            save_csv(data_csv, index)
            save_log(
                activity   = c.BTC_BRIDGE,
                row        = row, 
                from_chain = from_chain,
                to_chain   = to_chain, 
                from_token = 'BTC.b',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        else:
            logger.error(f'{prelog} | Ошибка при {c.BTC_BRIDGE} {from_chain} to {to_chain}')
            save_log(
                activity   = c.BTC_BRIDGE,
                row        = row, 
                from_chain = from_chain,
                to_chain   = to_chain, 
                from_token = 'BTC.b',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        return result
    
    if str(row[f'{c.BTC_BRIDGE}_STEP']) == 'XX':
        from_chain = 'Polygon'
        to_chain   = 'Avalanche'
        logger.info(f'{prelog} | {c.BTC_BRIDGE} 3 шаг, BTC BRIDGE {from_chain} to {to_chain}')
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.BTC_BRIDGE}_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.BTC_BRIDGE}_{from_chain.upper()}')
            return False 
        max_gas   = form_max_by_chain(chain=from_chain, usd=max_gas)
        max_value = form_max_by_chain(chain=from_chain, usd=max_value)
        result = bridge_btc(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            from_chain  = from_chain,
            to_chain    = to_chain,
            max_bridge  = 'ALL',
            max_gas     = max_gas,
            max_value   = max_value,
        )
        if result == True:
            logger.success(f'{prelog} | Успешный {c.BTC_BRIDGE} {from_chain} to {to_chain}')
            data_csv.loc[index,f'{c.BTC_BRIDGE}_STEP'] = 'XXX'
            save_csv(data_csv, index)
            save_log(
                activity   = c.BTC_BRIDGE,
                row        = row, 
                from_chain = from_chain,
                to_chain   = to_chain, 
                from_token = 'BTC.b',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        else:
            logger.error(f'{prelog} | Ошибка при {c.BTC_BRIDGE} {from_chain} to {to_chain}')
            save_log(
                activity   = c.BTC_BRIDGE,
                row        = row, 
                from_chain = from_chain,
                to_chain   = to_chain, 
                from_token = 'BTC.b',
                to_token   = 'BTC.b', 
                result     = result,
            ) 
        return result
    
    if str(row[f'{c.BTC_BRIDGE}_STEP']) == 'XXX':
        from_chain = 'Polygon'
        logger.info(f'{prelog} | {c.BTC_BRIDGE} 4 шаг, свап BTC.b на AVAX в TRADERJOE')
        result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.BTC_BRIDGE}_TRADERJOE_{from_chain.upper()}')
        if result_max_data == False:
            logger.error(f'{prelog} | Ошибка при получении max_data {c.BTC_BRIDGE}_TRADERJOE_{from_chain.upper()}')
            return False 
        max_gas   = form_max_by_chain(chain=from_chain, usd=max_gas)

        result = trade_btc_to_avax(
            name        = row['Name'],
            proxy       = row['Proxy'],
            private_key = row['Private_key'],
            max_btc     = 100,
            max_gas     = max_gas
        )
        if result == True:
            logger.success(f'{prelog} | Успешный TRADERJOE {from_chain}')
            data_csv.loc[index,f'{c.BTC_BRIDGE}_STEP'] = ''
            data_csv.loc[index,f'{c.BTC_BRIDGE}'] = int(data_csv.loc[index,f'{c.BTC_BRIDGE}']) - 1
            save_csv(data_csv, index)
            save_log(
                activity   = 'TRADERJOE',
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = 'BTC.b',
                to_token   = 'AVAX', 
                result     = result,
            ) 
        else:
            logger.error(f'{prelog} | Ошибка при TRADERJOE {from_chain}')
            save_log(
                activity   = 'TRADERJOE',
                row        = row, 
                from_chain = from_chain,
                to_chain   = '', 
                from_token = 'BTC.b',
                to_token   = 'AVAX', 
                result     = result,
            ) 
        return result

def execute_APTOS_BRIDGE(data_csv, row, index): 
    prelog = from_prelog(row)

    from_chain = 'BSC'
    logger.info(f'{prelog} | {c.APTOS_BRIDGE} выбрана сеть {from_chain}')
    token = 'USDT'
    try:
        amount_range      = str(row[f'{c.APTOS_BRIDGE}_RANGE']).split(',')
        amount_range_from = float(str(amount_range[0]).replace(' ', ''))
        amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
        amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
        amount_swap       = form_max_by_chain(chain=from_chain, usd=(amount * 1.01))
    except:
        logger.error(f'{prelog} | Ошибка при поиске суммы {c.APTOS_BRIDGE} для сети {from_chain}')
        return False 
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    result = swap_token(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        token       = token,
        amount      = amount_swap,
        max_gas     = max_gas,
        )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.APTOS_BRIDGE}_{from_chain.upper()}')
        save_log(
            activity = c.APTOS_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.APTOS_BRIDGE}_{from_chain.upper()}, {from_chain} {token} {amount}')
        save_log(
            activity = c.APTOS_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = True,
        )   
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.APTOS_BRIDGE}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.APTOS_BRIDGE}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    max_value = form_max_by_chain(chain=from_chain, usd=max_value)
    result = aptos_bridge(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        wallet      = row[f'{c.APTOS_BRIDGE}_WALLET'],
        amount      = amount,
        max_gas     = max_gas,
        max_value   = max_value,
    )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.APTOS_BRIDGE}_{from_chain.upper()}')
        save_log(
            activity = c.APTOS_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.APTOS_BRIDGE}_{from_chain.upper()}, {from_chain} {token} {amount}')
        data_csv.loc[index,f'{c.APTOS_BRIDGE}'] = int(data_csv.loc[index,f'{c.APTOS_BRIDGE}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity = c.APTOS_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = True,
        )
        return True
 
def execute_HARMONY_BRIDGE(data_csv, row, index): 
    prelog = from_prelog(row)

    from_chain = 'BSC'
    logger.info(f'{prelog} | {c.HARMONY_BRIDGE} выбрана сеть {from_chain}')
    token = 'USDT'
    try:
        amount_range      = str(row[f'{c.HARMONY_BRIDGE}_RANGE']).split(',')
        amount_range_from = float(str(amount_range[0]).replace(' ', ''))
        amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
        amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
        amount_swap       = form_max_by_chain(chain=from_chain, usd=(amount * 1.01))
    except:
        logger.error(f'{prelog} | Ошибка при поиске суммы {c.HARMONY_BRIDGE} для сети {from_chain}')
        return False 
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    result = swap_token(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        token       = token,
        amount      = amount_swap,
        max_gas     = max_gas,
        )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.SWAP_TOKEN}_{from_chain.upper()}')
        save_log(
            activity = c.SWAP_TOKEN,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.SWAP_TOKEN}_{from_chain.upper()}, {from_chain} {token} {amount}')
        save_log(
            activity = c.SWAP_TOKEN,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = True,
        )   
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.HARMONY_BRIDGE}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.HARMONY_BRIDGE}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    max_value = form_max_by_chain(chain=from_chain, usd=max_value)
    result = harmony_bridge(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        amount      = amount,
        max_gas     = max_gas,
        max_value   = max_value,
    )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.HARMONY_BRIDGE}_{from_chain.upper()}')
        save_log(
            activity = c.HARMONY_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = token,
            to_token   = '', 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.HARMONY_BRIDGE}_{from_chain.upper()}, {from_chain} {token} {amount}')
        data_csv.loc[index,f'{c.HARMONY_BRIDGE}'] = int(data_csv.loc[index,f'{c.HARMONY_BRIDGE}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity = c.HARMONY_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = token,
            to_token   = '', 
            result     = True,
        )
        return True   

def execute_STARGATE_STG(data_csv, row, index):
    prelog = from_prelog(row)

    from_chain = 'Polygon'
    logger.info(f'{prelog} | {c.STARGATE_STG} выбрана сеть {from_chain}')
    token = 'STG'
    try:
        amount_range      = str(row[f'{c.STARGATE_STG}_RANGE']).split(',')
        amount_range_from = float(str(amount_range[0]).replace(' ', ''))
        amount_range_to   = float(str(amount_range[1]).replace(' ', ''))
        amount            = round(random.uniform(amount_range_from, amount_range_to), 2)
        amount_swap       = form_max_by_chain(chain=from_chain, usd=(amount * 1.01))
    except:
        logger.error(f'{prelog} | Ошибка при поиске суммы {c.STARGATE_STG} для сети {from_chain}')
        return False 
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.SWAP_TOKEN}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.SWAP_TOKEN}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    result = sushi_swap_token(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        token       = token,
        amount      = amount_swap,
        max_gas     = max_gas,
        )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.SWAP_TOKEN}_{from_chain.upper()}')
        save_log(
            activity = c.SWAP_TOKEN,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.SWAP_TOKEN}_{from_chain.upper()}, {from_chain} {token} {amount}')
        save_log(
            activity = c.HARMONY_BRIDGE,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = '',
            to_token   = token, 
            result     = True,
        )   
    result_max_data, max_gas, max_value  = get_max_data(activity=f'{c.STARGATE_STG}_{from_chain.upper()}')
    if result_max_data == False:
        logger.error(f'{prelog} | Ошибка при получении max_data {c.STARGATE_STG}_{from_chain.upper()}')
        return False 
    max_gas = form_max_by_chain(chain=from_chain, usd=max_gas)
    result = stake_stg(
        name        = row['Name'],
        proxy       = row['Proxy'],
        private_key = row['Private_key'],
        from_chain  = from_chain,
        amount      = 'ALL',
        max_gas     = max_gas,
    )
    if result == False:
        logger.error(f'{prelog} | Ошибка при {c.STARGATE_STG}_{from_chain.upper()}')
        save_log(
            activity = c.STARGATE_STG,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = token,
            to_token   = '', 
            result     = False,
        )   
        return False
    else:
        logger.success(f'{prelog} | Успешный {c.STARGATE_STG}_{from_chain.upper()}, {from_chain} {token} {amount}')
        data_csv.loc[index,f'{c.STARGATE_STG}'] = int(data_csv.loc[index,f'{c.STARGATE_STG}']) - 1
        save_csv(data_csv, index)
        save_log(
            activity = c.STARGATE_STG,
            row        = row, 
            from_chain = from_chain,
            to_chain   = '', 
            from_token = token,
            to_token   = '', 
            result     = True,
        )
        return True   
    
def execute_activity(activity:str, data_csv, row, index)->bool:
    try:
        if activity == c.STARGATE:
            result = execute_STARGATE(data_csv, row=row, index=index)
        
        # if activity == c.STARGATE_BSC:
        #     result = execute_STARGATE_single_chain(data_csv=data_csv, row=row, index=index, chain='BSC')
        
        # if activity == c.STARGATE_ARBITRUM:
        #     result = execute_STARGATE_single_chain(data_csv=data_csv, row=row, index=index, chain='Arbitrum')

        # if activity == c.STARGATE_OPTIMISM:
        #     result = execute_STARGATE_single_chain(data_csv=data_csv, row=row, index=index, chain='Optimism')
        
        if activity == c.SWAP_TOKEN:
            result = execute_SWAP_TOKEN(data_csv=data_csv, row=row, index=index)
        
        if activity == c.TESTNET_BRIDGE:
            result = execute_TESTNET_BRIDGE(data_csv=data_csv, row=row, index=index)

        if activity == c.BTC_BRIDGE:
            result = execute_BTC_BRIDGE(data_csv=data_csv, row=row, index=index)

        if activity == c.APTOS_BRIDGE:
            result = execute_APTOS_BRIDGE(data_csv=data_csv, row=row, index=index)
        
        if activity == c.HARMONY_BRIDGE:
            result = execute_HARMONY_BRIDGE(data_csv=data_csv, row=row, index=index)

        if activity == c.STARGATE_STG:
            result = execute_STARGATE_STG(data_csv=data_csv, row=row, index=index)

    
        return result
    except Exception as Ex:
        print(str(Ex))
        return False
