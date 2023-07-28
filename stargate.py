from web3 import Web3
import stargate_settings as s
from loguru import logger as global_logger
import copy
import time
import ZBC

def stargate(name, proxy, private_key, amount, from_chain, to_chain, from_token, to_token, max_gas, max_value, slippage):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    log_name = f'STARGATE {from_token} to {to_token} {amount} {from_chain} to {to_chain} {amount}'

    # Получаем данные
    _element = 'chain'
    from_data = ZBC.search_setting_data_by_element(element_search = _element, value=from_chain, list=s.CHAIN_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        from_data = from_data[0]

    # Получаем данные по токену
    _element = 'token'
    token_data = ZBC.search_setting_data_by_element(element_search = _element, value=from_token, list=from_data['token_list'])
    if len(token_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        token_data_from = token_data[0]

    _element = 'chain'
    to_data = ZBC.search_setting_data_by_element(element_search=_element, value=to_chain, list=s.CHAIN_LIST)
    if len(to_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации to_chain')
        return False
    else:
        to_data = to_data[0]

    # Получаем данные по токену
    _element = 'token'
    token_data = ZBC.search_setting_data_by_element(element_search = _element, value=to_token, list=to_data['token_list'])
    if len(token_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        token_data_to = token_data[0]

    SLIPPAGE        = slippage

    RPC_FROM          = from_data['rpc']
    TOKEN_FROM        = token_data_from['address']
    TOKEN_ABI_FROM    = token_data_from['abi']
    TOKEN_POOLID_FROM = token_data_from['poolid']
    ROUTER_FROM       = from_data['router']
    ROUTER_ABI_FROM   = from_data['router_ABI']

    RPC_TO            = to_data['rpc']
    CHAINID_TO        = to_data['chainId']
    TOKEN_TO          = token_data_to['address']
    TOKEN_ABI_TO      = token_data_to['abi']
    TOKEN_POOLID_TO   = token_data_to['poolid']

    # Сначала коннектимся к нужной RPC
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain} | {RPC_FROM}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {from_chain} | {RPC_FROM}')
        return False
    w3_to = Web3(Web3.HTTPProvider(RPC_TO, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy }, 'timeout': 180}))
    if w3_to.is_connected() == True:
        logger.success(f'{name} | {address} | {log_name} | Подключились к {to_chain} | {RPC_TO}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {to_chain} | {RPC_TO}')
        return False
    
    # Проверяем баланс кошелька from_chain
    try:
        contractTOKEN_from = w3_from.eth.contract(address=w3_from.to_checksum_address(TOKEN_FROM), abi=TOKEN_ABI_FROM)
        
        token_symbol_from     = contractTOKEN_from.functions.symbol().call()
        token_decimals_from   = contractTOKEN_from.functions.decimals().call()
        balance_of_token_from = contractTOKEN_from.functions.balanceOf(address).call()
        human_balance         = balance_of_token_from/ 10 ** token_decimals_from

        if amount == 'ALL':
            amountIn = balance_of_token_from
            amount = human_balance
        else:
            amountIn = int(amount * 10 ** token_decimals_from)
        if balance_of_token_from >= amountIn:
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_from} = {human_balance}, суммы достаточно | {from_chain}')
        else:
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_from} = {human_balance} суммы НЕ достаточно | {from_chain}')
            logger.error(f'{name} | {address} | {log_name} | {token_symbol_from} = {human_balance} суммы НЕ достаточно | {from_chain}')
            return False
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке баланса | {from_chain} \n {str(Ex)}')
        return False
    
    # Проверяем баланс кошелька to_chain
    try:
        contractTOKEN_to     = w3_to.eth.contract(address=w3_to.to_checksum_address(TOKEN_TO), abi=TOKEN_ABI_TO)

        token_symbol_to      = contractTOKEN_to.functions.symbol().call()
        token_decimals_to    = contractTOKEN_to.functions.decimals().call()
        balance_of_token_to1 = contractTOKEN_to.functions.balanceOf(address).call()
        human_balance_to1    = balance_of_token_to1/ 10 ** token_decimals_to
        logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to1}, сумма до перевода | {to_chain}')
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке баланса | {to_chain} \n {str(Ex)}')
        return False
    
    # Делаем approve суммы
    try:
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractTOKEN_from.functions.approve(
                w3_from.to_checksum_address(ROUTER_FROM),
                amountIn
                ).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.1
            if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                gas_price = 1500000000
            else:
                gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)
                
        transaction = contractTOKEN_from.functions.approve(
                w3_from.to_checksum_address(ROUTER_FROM),
                amountIn
                ).build_transaction(
                    {
                    'from': address,
                    'value': 0,
                    'gas': int(gas),
                    'gasPrice': int(gas_price),
                    'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали Approve {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'Approve кол-во {amount} | {from_chain}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount} | {from_chain}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для Approve кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
    
    time.sleep(10)

    # SWAP
    try: 
        contractRouter = w3_from.eth.contract(address=w3_from.to_checksum_address(ROUTER_FROM), abi=ROUTER_ABI_FROM)
        nonce = w3_from.eth.get_transaction_count(address)
        amountOutMin = amountIn - (amountIn * SLIPPAGE) // 1000

        count_ex_gas = 0
        while True:
            # Узнаем коммисию за swap  
            value = contractRouter.functions.quoteLayerZeroFee(
                int(CHAINID_TO),                                              
                1,                                                                    
                address,                                                              
                "0x",                                                                 
                (0, 0, '0x0000000000000000000000000000000000000001')
            ).call()
            value = value[0]
            human_value = w3_from.from_wei(value, "ether").real
            if human_value < max_value:
                logger.info(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}')
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue
            
            try:
                gas = contractRouter.functions.swap(
                    int(CHAINID_TO),                                                      # destination chainId
                    TOKEN_POOLID_FROM,                                                    # source poolId
                    TOKEN_POOLID_TO,                                                      # destination poolId
                    address,                                                              # refund address. extra gas (if any) is returned to this address
                    amountIn ,                                                            # quantity to swap
                    amountOutMin,                                                         # the min qty you would accept on the destination                                                           # 
                    (0, 0, '0x0000000000000000000000000000000000000001'),
                    address,                                                              # the address to send the tokens to on the destination
                    '0x'
                    ).estimate_gas({'from': address, 'value':value, 'nonce': nonce, })
            except Exception as Ex:
                logger.warning(f'{name} | {address} | {log_name} | Ошибка при получении газа \n {str(Ex)}')
                if "LayerZero: not enough native for fees" in str(Ex):
                    count_ex_gas += 1
                    if count_ex_gas > 3:
                        logger.error(f'{name} | {address} | {log_name} | Ошибка 3 раза подряд LayerZero: not enough native for fees при получении газа \n')
                        raise Exception
                    else:
                        continue
                else:
                    raise Exception
            count_ex_gas = 0
            gas = gas * 1.2
            if from_chain == 'BSC' and 'ankr' in RPC_FROM:
                gas_price = 1500000000
            else:
                gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на BRIDGE {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на BRIDGE {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue

        transaction = contractRouter.functions.swap(
            int(CHAINID_TO),                                                      # destination chainId
            TOKEN_POOLID_FROM,                                                    # source poolId
            TOKEN_POOLID_TO,                                                      # destination poolId
            address,                                                              # refund address. extra gas (if any) is returned to this address
            amountIn ,                                                            # quantity to swap
            amountOutMin,                                                         # the min qty you would accept on the destination                                                           # 
            (0, 0, '0x0000000000000000000000000000000000000001'),
            address,                                                              # the address to send the tokens to on the destination
            '0x'
            ).build_transaction({
                'from': address,
                'value': value,
                'gas': int(gas),
                'gasPrice': int(gas_price),
                'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали STARGATE {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'STARGATE кол-во {amount} | {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при STARGATE кол-во {amount} | {from_chain}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для STARGATE кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при STARGATE кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
    
    result = True
    # Проверяем баланс кошелька на который отправили
    try:
        lv_count = 0
        while lv_count <= 360:
            try:
                balance_of_token_to2 = contractTOKEN_to.functions.balanceOf(address).call()
            except Exception as Ex:
                logger.error(f'{name} | {address} | {log_name} | Ошибка при balanceOf, {Ex}')
                time.sleep(60)
                continue
            human_balance_to2 = balance_of_token_to2 / 10 ** token_decimals_to
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to2} | {to_chain}') 
            if balance_of_token_to1 < balance_of_token_to2:
                logger.success(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to2}, STARGATE выполнен | {to_chain}') 
                return True
            lv_count += 1
            time.sleep(60)
        logger.error(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to1}, не получили сумму от STARGATE | {to_chain}') 
        return result
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке перевода кол-во {amount} | {to_chain} \n {str(Ex)}')
        return result
