from web3 import Web3
from loguru import logger as global_logger
import json
from os import path
import sys
from dateutil.relativedelta import relativedelta
from datetime import datetime
import time
import random
import btcbridge_settings as s
import datetime
import ZBC
import copy
    
def trade_avax_to_btc(name, proxy, private_key, value, max_gas):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")

    avalanche_data = ZBC.search_setting_data(chain='Avalanche', list=s.SETTING_LIST)
    if len(avalanche_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации avalanche_data')
        return False
    else:
        avalanche_data = avalanche_data[0]
    
    log_name = f'TRADERJOE AVAX to BTC.b'

    RPC = avalanche_data['RPC']
    TRADERJOE = s.TRADERJOE
    TRADERJOE_ABI = s.TRADERJOE_ABI
    BTC = avalanche_data['BTC']
    BTC_ABI = avalanche_data['BTC_ABI']

    # Подключаемся и проверяем
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy},"timeout":120}))
    if w3.is_connected() == True:
        account = w3.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к Avalanche')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении {RPC}')
        return False

    # Проверим баланс до перевода
    contractBTC = w3.eth.contract(address=w3.to_checksum_address(BTC), abi=BTC_ABI)
    token_symbol_to = contractBTC.functions.symbol().call()
    token_decimals_to = contractBTC.functions.decimals().call()
    balance_of_token_to1 = contractBTC.functions.balanceOf(address).call()
    human_balance_to = balance_of_token_to1/ 10 ** token_decimals_to
    logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to}, сумма до перевода')

    # Делаем SWAP
    deadline = datetime.datetime.now() + datetime.timedelta(minutes = 30)
    deadline = int(deadline.timestamp())

    amountOutMin = int(value - (value * 50) // 1000)
    try:
        contractTRADERJOE = w3.eth.contract(address=w3.to_checksum_address(TRADERJOE), abi=TRADERJOE_ABI)
        nonce = w3.eth.get_transaction_count(address)
        while True:
            gas = contractTRADERJOE.functions.swapExactNATIVEForTokens(
                amountOutMin,
                (
                [0],
                [0],
                ['0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7','0x152b9d0FdC40C096757F570A51E494bd4b943E50']
                ),
                address,
                deadline
                ).estimate_gas({'from': address, 'value': w3.to_wei(value, "ether") , 'nonce': nonce, })
            gas = gas * 1.2
            gas_price = w3.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа SWAP {txCostInEther} AVAX')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа SWAP {txCostInEther} AVAX, это больше максимума')


        transaction = contractTRADERJOE.functions.swapExactNATIVEForTokens(
            amountOutMin,
            (
            [0],
            [0],
            ['0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7','0x152b9d0FdC40C096757F570A51E494bd4b943E50']
            ),
            address,
            deadline
            ).build_transaction({
            'from': address,
            'value': w3.to_wei(value, "ether"),
            'gas': int(gas),
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce})
        
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали SWAP {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3, log_name=log_name, text=f'SWAP AVAX to BTC.t {value}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP AVAX to BTC.t {value}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для SWAP AVAX to BTC.t {value} \n {str(Ex)}')
        logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP AVAX to BTC.t {value} \n {str(Ex)}')
        return False

    # Проверяем баланс кошелька на который отправили
    try:
        lv_count = 0
        while lv_count <= 360:
            try:
                balance_of_token_to2 = contractBTC.functions.balanceOf(address).call()
            except Exception as Ex:
                logger.error(f'{name} | {address} | {log_name} | Ошибка при balanceOf, {Ex}')
                time.sleep(30)
                continue
            human_balance_to = balance_of_token_to2 / 10 ** token_decimals_to
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to}') 
            if balance_of_token_to1 < balance_of_token_to2:
                logger.success(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to}, SWAP выполнен') 
                return True
            lv_count += 1
            time.sleep(30)
        logger.error(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to}, не получили сумму от SWAP') 
        return False
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке перевода кол-во {value} \n {str(Ex)}')
        return False
    

def trade_btc_to_avax(name, proxy, private_key, max_btc, max_gas ):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    avalanche_data = ZBC.search_setting_data(chain='Avalanche', list=s.SETTING_LIST)
    if len(avalanche_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации avalanche_data')
        return False
    else:
        avalanche_data = avalanche_data[0]
    
    log_name = f'TRADERJOE BTC.b to AVAX'

    RPC = avalanche_data['RPC']
    TRADERJOE = s.TRADERJOE
    TRADERJOE_ABI = s.TRADERJOE_ABI
    BTC_FROM = avalanche_data['BTC']
    BTC_ABI_FROM = avalanche_data['BTC_ABI']

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy},"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к Avalanche')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении {RPC}')
        return False
  
    #   Получаем BTC из from
    contractBTC_from = w3_from.eth.contract(address=w3_from.to_checksum_address(BTC_FROM), abi=BTC_ABI_FROM)
    token_symbol_BTC_from = contractBTC_from.functions.symbol().call()
    token_decimals_BTC_from = contractBTC_from.functions.decimals().call()
    balance_of_token_BTC_from = contractBTC_from.functions.balanceOf(address).call()
    human_balance_BTC_from = balance_of_token_BTC_from/ 10 ** token_decimals_BTC_from
    logger.info(f'{name} | {address} | {log_name} | {token_symbol_BTC_from} = {human_balance_BTC_from}, Avalanche')

    # Проверяем, что есть токены
    if human_balance_BTC_from == 0:
        logger.error(f'{name} | {address} | {log_name} | Нет токенов') 
        return False
    if human_balance_BTC_from > max_btc:
        amountIn = int(max_btc * 10 ** token_decimals_BTC_from)
        amount = max_btc
    else:
        amountIn = balance_of_token_BTC_from
        amount = balance_of_token_BTC_from/ 10 ** token_decimals_BTC_from
    logger.info(f'{name} | {address} | {log_name} | Будет SWAP {amount}')

    # APPROVE BTC
    try:
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractBTC_from.functions.approve(w3_from.to_checksum_address(TRADERJOE), amountIn).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.2
            gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, Avalanche')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, Avalanche, это больше максимума')
                time.sleep(30)

        transaction = contractBTC_from.functions.approve(w3_from.to_checksum_address(TRADERJOE), amountIn).build_transaction({
            'from': address,
            'value': 0,
            'gas': int(gas),
            'gasPrice': w3_from.eth.gas_price,
            'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали Approve {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'Approve кол-во {amount}, Avalanche', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, Avalanche')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для Approve кол-во {amount}, Avalanche \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, Avalanche \n {str(Ex)}')
        return False
    
    time.sleep(2)

    # Делаем SWAP
    deadline = datetime.datetime.now() + datetime.timedelta(minutes = 30)
    deadline = int(deadline.timestamp())
    try:
        contractTRADERJOE = w3_from.eth.contract(address=w3_from.to_checksum_address(TRADERJOE), abi=TRADERJOE_ABI)
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractTRADERJOE.functions.swapExactTokensForNATIVE(
                amountIn,
                1,
                (
                [10],
                [1],
                ['0x152b9d0FdC40C096757F570A51E494bd4b943E50','0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7']
                ),
                address,
                deadline
                ).estimate_gas({'from': address, 'value': 0 , 'nonce': nonce, })
            gas = gas * 1.2
            gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа SWAP {txCostInEther} AVAX')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа SWAP {txCostInEther} AVAX, это больше максимума')


        transaction = contractTRADERJOE.functions.swapExactTokensForNATIVE(
            amountIn,
            1,
            (
            [10],
            [1],
            ['0x152b9d0FdC40C096757F570A51E494bd4b943E50','0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7']
            ),
            address,
            deadline
            ).build_transaction({
            'from': address,
            'value': 0,
            'gas': int(gas),
            'gasPrice': w3_from.eth.gas_price,
            'nonce': nonce})
        
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали SWAP {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'SWAP AVAX to BTC.t {amount}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP BTC.b to AVAX {amount}')
            return False
        return True
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для SWAP BTC.b to AVAX {amount} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP BTC.b to AVAX {amount} \n {str(Ex)}')
        return False
