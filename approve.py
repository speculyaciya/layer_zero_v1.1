from web3 import Web3
from loguru import logger as global_logger
import approve_settings as s
import time
import ZBC
import copy

def approve(name, proxy, private_key, amount, from_chain, token, max_gas):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    log_name = f'{token} APPROVE {amount} {from_chain}'

    # Получаем данные по сети
    _element = 'chain'
    from_data = ZBC.search_setting_data_by_element(element_search = _element, value=from_chain, list=s.CHAIN_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        from_data = from_data[0]

    # Получаем данные по токену
    _element = 'token'
    token_data = ZBC.search_setting_data_by_element(element_search = _element, value=token, list=from_data['token_list'])
    if len(token_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        token_data = token_data[0]

    RPC_FROM  = from_data['rpc']
    TOKEN     = token_data['address']
    TOKEN_ABI = token_data['abi']

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {from_chain}')
        return False, f'Ошибка при подключении {RPC_FROM}', ''

    APPROVE_ADDRESS = address

    # Подключаемся к контракту токена
    contractTOKEN = w3_from.eth.contract(address=w3_from.to_checksum_address(TOKEN), abi=TOKEN_ABI)
    token_decimals_from = contractTOKEN.functions.decimals().call()
    amountIn = int(amount * 10 ** token_decimals_from)
    
    try:
        nonce = w3_from.eth.get_transaction_count(address)
        # Тут мы крутим и ждем, пока газ будет меньше нашего максимума
        while True:
            gas = contractTOKEN.functions.approve(
                APPROVE_ADDRESS,
                amountIn
                ).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas
            gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)

        transaction = contractTOKEN.functions.approve(
                    APPROVE_ADDRESS,
                    amountIn
                    ).build_transaction({
                        'from': address,
                        'value': 0,
                        'gas': int(gas),
                        'gasPrice': w3_from.eth.gas_price,
                        'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали Approve {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'Approve кол-во {amount}, {from_chain}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, {from_chain}')
            return False, f'Ошибка при Approve {amount}, {from_chain}', ''
        return True
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для Approve кол-во {amount}, {from_chain}')
            return False, f'Недостаточно средств для Approve кол-во {amount}, {from_chain}', str(Ex)
        logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, {from_chain}')
        return False, f'Ошибка при Approve кол-во {amount}, {from_chain}', str(Ex)