from web3 import Web3
from loguru import logger as global_logger
import ZBC
import sushi_swap_settings as s
import time
import requests
from decimal import Decimal
import copy
    
def sushi_swap_token(name, proxy, private_key, from_chain:str, token, amount, max_gas=0):
    NAME = 'SUSHI SWAP'

    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    ROUND = 6
    amount = round(Decimal(amount), ROUND).real
    log_name = f'SUSHI SWAP TOKEN {token} = {amount} {from_chain}'

    # Получаем данные
    _element = 'chain'
    from_data = ZBC.search_setting_data_by_element(element_search = _element, value=from_chain, list=s.CHAIN_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | {NAME} | Ошибка при поиске информации {_element}')
        return False
    else:
        from_data = from_data[0]

    # Получаем данные по токену
    _element = 'token'
    token_data = ZBC.search_setting_data_by_element(element_search = _element, value=token, list=from_data['token_list'])
    if len(token_data) == 0:
        logger.error(f'{name} | {log_name} | {NAME} | Ошибка при поиске информации {_element}')
        return False
    else:
        token_data = token_data[0]


    MAX_GAS              = max_gas
    SLIPPAGE             = 10

    RPC_FROM             = from_data['rpc']
    SUSHI                = from_data['SUSHI']
    SUSHI_ABI            = from_data['SUSHI_ABI']
    TOKEN_FROM           = Web3.to_checksum_address(s.WETH_CONTRACTS[from_chain])
    TOKEN                = Web3.to_checksum_address(token_data['address'])
    TOKEN_ABI            = token_data['abi']

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | {NAME} | Подключились к {from_chain}, {RPC_FROM}')
    else:
        logger.error(f'{name} | {log_name} | {NAME} | Ошибка при подключении к {from_chain}, {RPC_FROM}')
        return False
    pass
    
    # Получаем баланс до и конвректируем amount
    try:
        contractTOKEN_to     = w3_from.eth.contract(address=w3_from.to_checksum_address(TOKEN), abi=TOKEN_ABI)

        token_symbol_to      = contractTOKEN_to.functions.symbol().call()
        token_decimals_to    = contractTOKEN_to.functions.decimals().call()
        balance_of_token_to1 = contractTOKEN_to.functions.balanceOf(address).call()
        human_balance_to1    = balance_of_token_to1/ 10 ** token_decimals_to
        human_balance_to1    = round(Decimal(human_balance_to1), ROUND)
        logger.info(f'{name} | {address} | {log_name} | {NAME} | {token_symbol_to} = {human_balance_to1}, сумма до перевода | {from_chain}')

        if amount == 'ALL':
            amountIn          = balance_of_token_to1
        else:
            amountIn          = int(w3_from.to_wei(amount, "ether"))
        # amountIn             = int(amount * 10 ** token_decimals_to)
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | {NAME} | Ошибка при проверке баланса | {from_chain}, \n {str(Ex)}')
        return False

    # SWAP
    try: 
        contractSushiSwap = w3_from.eth.contract(address=w3_from.to_checksum_address(SUSHI), abi=SUSHI_ABI)
        nonce = w3_from.eth.get_transaction_count(address)
        amountOutMin = amountIn - (amountIn * SLIPPAGE) // 1000
        while True:
            gas = contractSushiSwap.functions.swapExactETHForTokens(
                amountOutMin,
                [TOKEN_FROM, TOKEN],
                address, # receiver
                (int(time.time()) + 10000)  # deadline
                ).estimate_gas({'from': address, 'value':amountIn, 'nonce': nonce, })
            gas = gas * 1.2
            if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                gas_price = 1500000000
            else:
                gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < MAX_GAS:
                logger.info(f'{name} | {address} | {log_name} | {NAME} | Стоимость газа {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | {NAME} | Стоимость газа {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue

        transaction = contractSushiSwap.functions.swapExactETHForTokens(
            amountOutMin,
            [TOKEN_FROM, TOKEN],
            address, 
            (int(time.time()) + 10000) 
            ).build_transaction({
                'from': address,
                'value': amountIn,
                'gas': int(gas),
                'gasPrice': int(gas_price),
                'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | {NAME} | Подписали {NAME} {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f' {NAME} |  кол-во {amount} | {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | {NAME} | Ошибка при {NAME} кол-во {amount} | {from_chain}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | {NAME} | Недостаточно средств для {NAME} кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | {NAME} | Ошибка при {NAME} кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
    
    # Проверяем баланс кошелька на который отправили
    try:
        lv_count = 0
        while lv_count <= 360:
            try:
                balance_of_token_to2 = contractTOKEN_to.functions.balanceOf(address).call()
            except Exception as Ex:
                logger.error(f'{name} | {address} | {log_name} | Ошибка при balanceOf, {Ex}')
                time.sleep(30)
                continue
            human_balance_to2 = balance_of_token_to2 / 10 ** token_decimals_to
            human_balance_to2 = round(Decimal(human_balance_to2), ROUND)
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to2} | {from_chain}') 
            if balance_of_token_to1 < balance_of_token_to2:
                logger.success(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to2}, SWAP выполнен | {from_chain}') 
                return True
            lv_count += 1
            time.sleep(30)
        logger.error(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to1}, не получили сумму от SWAP | {from_chain}') 
        return False
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке перевода кол-во {amount} | {from_chain}, \n {str(Ex)}')
        return False
    
