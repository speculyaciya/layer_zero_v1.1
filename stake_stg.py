from web3 import Web3
from loguru import logger as global_logger
import ZBC
import stake_stg_settings as s
import time
from decimal import Decimal
import copy



def stake_stg(name, proxy, private_key, from_chain:str, amount, max_gas=0):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    ROUND = 6
    if amount != 'ALL':
        amount = round(Decimal(amount), ROUND).real
    log_name = f'STAKE STG {amount} {from_chain}'

    # Получаем данные
    _element = 'chain'
    from_data = ZBC.search_setting_data_by_element(element_search = _element, value=from_chain, list=s.CHAIN_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        from_data = from_data[0]

    MAX_GAS              = max_gas

    RPC_FROM             = from_data['rpc']
    STG                  = Web3.to_checksum_address(from_data['STG'])
    STG_ABI              = from_data['STG_ABI']
    VESTG                = Web3.to_checksum_address(from_data['veSTG'])
    VESTG_ABI            = from_data['veSTG_ABI']

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain}, {RPC_FROM}')
    else:
        logger.error(f'{name} | {log_name} |  Ошибка при подключении к {from_chain}, {RPC_FROM}')
        return False
    pass

    try:
        contractSTG = w3_from.eth.contract(address=w3_from.to_checksum_address(STG), abi=STG_ABI)

        token_symbol = contractSTG.functions.symbol().call()
        token_decimals = contractSTG.functions.decimals().call()
        balance_of_token = contractSTG.functions.balanceOf(address).call()
        human_balance = balance_of_token/ 10 ** token_decimals
        if amount == 'ALL':
            amountIn = balance_of_token
        else:
            amountIn = int(amount * 10 ** token_decimals)
        if balance_of_token >= amountIn:
            logger.info(f'{name} | {address} | {log_name} | {token_symbol} = {human_balance}, суммы достаточно')
        else:
            logger.error(f'{name} | {address} | {log_name} | {token_symbol} = {human_balance} суммы НЕ достаточно')
            return False
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке баланса  \n {str(Ex)}')
        return False

    try:
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractSTG.functions.approve(
                VESTG,
                amountIn
                ).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.2
            if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                gas_price = 1500000000
            else:
                gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < MAX_GAS:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}, это больше максимума')
                time.sleep(30)
                continue

        transaction = contractSTG.functions.approve(
            VESTG,
            amountIn
            ).build_transaction({
                'from': address,
                'value': 0,
                'gas': int(gas),
                'gasPrice': int(gas_price),
                'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали APPROVE {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f' APPROVE кол-во {amount} | {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при APPROVE кол-во {amount} | {from_chain}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для APPROVE кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при APPROVE кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
    
    # STAKE 
    contract_VESTG = w3_from.eth.contract(address=VESTG, abi=VESTG_ABI)
    nonce          = w3_from.eth.get_transaction_count(address)
    try:
        while True:
            gas = contract_VESTG.functions.create_lock(
                amountIn, 
                int(time.time() + 94608000)
                ).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.2
            if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                gas_price = 1500000000
            else:
                gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < MAX_GAS:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}, это больше максимума')
                time.sleep(30)
                continue

        transaction = contract_VESTG.functions.create_lock(
            amountIn, 
            int(time.time() + 94608000)
            ).build_transaction({
                'from': address,
                'value': 0,
                'gas': int(gas),
                'gasPrice': int(gas_price),
                'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали CREATE_LOCK {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'CREATE_LOCK кол-во {amount} | {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при CREATE_LOCK кол-во {amount} | {from_chain}')
            return False
        return True
    except Exception as Ex:
        if "Withdraw old tokens first" in str(Ex):
            try:
                logger.warning(f'{name} | {address} | Уже создан STAKE, добавляем к существующему стейку {amount}')
                while True:
                    gas = contract_VESTG.functions.increase_amount(
                        amountIn
                        ).estimate_gas({'from': address, 'nonce': nonce, })
                    gas = gas * 1.2
                    if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                        gas_price = 1500000000
                    else:
                        gas_price = w3_from.eth.gas_price
                    txCost = gas * gas_price
                    txCostInEther = w3_from.from_wei(txCost, "ether").real
                    if txCostInEther < MAX_GAS:
                        logger.info(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}')
                        break
                    else:
                        logger.warning(f'{name} | {address} | {log_name} | Стоимость газа {txCostInEther}, это больше максимума')
                        time.sleep(30)
                        continue
                transaction = contract_VESTG.functions.increase_amount(amountIn).build_transaction({
                    'from': address,
                    'value': 0,
                    'gas': int(gas),
                    'gasPrice': int(gas_price),
                    'nonce': nonce})
                signed_transaction = account.sign_transaction(transaction)
                transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
                logger.success(f'{name} | {address} | {log_name} | Подписали INCREASE_AMOUNT {transaction_hash.hex()}')
                status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'INCREASE_AMOUNT кол-во {amount} | {from_chain}',  logger=logger)
                if status == False:
                    logger.error(f'{name} | {address} | {log_name} | Ошибка при INCREASE_AMOUNT кол-во {amount} | {from_chain}')
                    return False
                return True
            except Exception as Ex:
                if "insufficient funds for gas * price + value" in str(Ex):
                    logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для INCREASE_AMOUNT кол-во {amount} \n {str(Ex)}')
                    return False
                logger.error(f'{name} | {address} | {log_name} | Ошибка при INCREASE_AMOUNT кол-во {amount} \n {str(Ex)}')
                return False
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для CREATE_LOCK кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при CREATE_LOCK кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
