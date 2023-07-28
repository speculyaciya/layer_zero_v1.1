from web3 import Web3
from loguru import logger as global_logger
import time
import btcbridge_settings as s
import ZBC
from eth_abi import abi
import eth_abi.packed
import copy

def bridge_btc(name, proxy, private_key, from_chain, to_chain, max_bridge, max_gas, max_value):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")

    from_data = ZBC.search_setting_data(chain=from_chain, list=s.SETTING_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации from_chain')
        return False
    else:
        from_data = from_data[0]
    to_data = ZBC.search_setting_data(chain=to_chain, list=s.SETTING_LIST)
    if len(to_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации to_chain')
        return False
    else:
        to_data = to_data[0]

    RPC_FROM = from_data['RPC']
    RPC_TO = to_data['RPC']
    BTC_BRIDGE = from_data['BTC_BRIDGE']
    BTC_BRIDGE_ABI = from_data['BTC_BRIDGE_ABI']
    BTC_FROM = from_data['BTC']
    BTC_ABI_FROM = from_data['BTC_ABI']
    BTC_TO = to_data['BTC']
    BTC_ABI_TO = to_data['BTC_ABI']
    DSTCHAINID = to_data['CHAINID']

    log_name = f'BRIDGE BTC.b {from_chain} to {to_chain}'

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {from_chain}')
        return False, f'Ошибка при подключении {RPC_FROM}', ''
    
    w3_to = Web3(Web3.HTTPProvider(RPC_TO, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_to.is_connected() == True:
        logger.success(f'{name} | {address} | {log_name} | Подключились к {to_chain}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {to_chain}')
        return False, f'Ошибка при подключении {RPC_TO}', ''
    
    #   Получаем BTC из from
    contractBTC_from = w3_from.eth.contract(address=w3_from.to_checksum_address(BTC_FROM), abi=BTC_ABI_FROM)
    token_symbol_BTC_from = contractBTC_from.functions.symbol().call()
    token_decimals_BTC_from = contractBTC_from.functions.decimals().call()
    balance_of_token_BTC_from = contractBTC_from.functions.balanceOf(address).call()
    human_balance_BTC_from = balance_of_token_BTC_from/ 10 ** token_decimals_BTC_from
    logger.info(f'{name} | {address} | {log_name} | {token_symbol_BTC_from} = {human_balance_BTC_from}, {from_chain}')

    if max_bridge == 'ALL':
        amountIn = balance_of_token_BTC_from
        amount = human_balance_BTC_from
    else:
        amountIn = int(max_bridge * 10 ** token_decimals_BTC_from)
    # Проверяем, что есть токены
    if balance_of_token_BTC_from == 0:
        logger.error(f'{name} | {address} | {log_name} | Нет токенов') 
        return False, f'Нет токенов', ''
    logger.info(f'{name} | {address} | {log_name} | Будет BRIDGE {amount} в {to_chain}')

    # APPROVE BTC
    try:
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractBTC_from.functions.approve(w3_from.to_checksum_address(BTC_BRIDGE), amountIn).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.2
            gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на approve {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)

        transaction = contractBTC_from.functions.approve(w3_from.to_checksum_address(BTC_BRIDGE), amountIn).build_transaction({
            'from': address,
            'value': 0,
            'gas': int(gas),
            'gasPrice': int(gas_price),
            'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали Approve {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'Approve кол-во {amount}, {from_chain}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, {from_chain}')
            return False, f'Ошибка при Approve {amount}, {from_chain}', ''
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для Approve кол-во {amount}, {from_chain}')
            return False, f'Недостаточно средств для Approve кол-во {amount}, {from_chain}', str(Ex)
        logger.error(f'{name} | {address} | {log_name} | Ошибка при Approve кол-во {amount}, {from_chain}')
        return False, f'Ошибка при Approve кол-во {amount}, {from_chain}', str(Ex)
    
    time.sleep(2)

    #   Получаем BTC до bridge в to_chain 
    contractBTC_to = w3_to.eth.contract(address=w3_from.to_checksum_address(BTC_TO), abi=BTC_ABI_TO)
    token_symbol_BTC_to = contractBTC_to.functions.symbol().call()
    token_decimals_BTC_to = contractBTC_to.functions.decimals().call()
    balance_of_token_BTC_to = contractBTC_to.functions.balanceOf(address).call()
    human_balance_BTC_to = balance_of_token_BTC_to/ 10 ** token_decimals_BTC_to
    logger.info(f'{name} | {address} | {log_name} | {token_symbol_BTC_to} = {human_balance_BTC_to}, {to_chain}')

    # Делаем BRIDGE 
    try:
        contractBTC_BRIDGE = w3_from.eth.contract(address=w3_from.to_checksum_address(BTC_BRIDGE), abi=BTC_BRIDGE_ABI)
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            # Узнаем сначала value
            value = contractBTC_BRIDGE.functions.estimateSendFee(
                int(DSTCHAINID),
                abi.encode( ["address"],[Web3.to_checksum_address(address)]),
                amountIn,
                True,
                eth_abi.packed.encode_packed( ["uint16", "uint256", "uint256", "address"],
                [2, 250000, 0, Web3.to_checksum_address(address)])
                ).call()
            value = value[0]
            human_value = w3_from.from_wei(value, "ether").real
            if human_value < max_value:
                logger.info(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}')
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue

            gas = contractBTC_BRIDGE.functions.sendFrom(
                Web3.to_checksum_address(address),
                int(DSTCHAINID),
                abi.encode( ["address"],[Web3.to_checksum_address(address)]),
                amountIn,
                amountIn,
                (
                Web3.to_checksum_address(address),
                Web3.to_checksum_address('0x0000000000000000000000000000000000000000'),
                eth_abi.packed.encode_packed( ["uint16", "uint256", "uint256", "address"],
                [2, 250000, 0, Web3.to_checksum_address(address)])
                )
                ).estimate_gas({'from': address, 'value':value, 'nonce': nonce, })
            gas = gas * 1.2
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

        # Выполняем BRIDGE
        transaction = contractBTC_BRIDGE.functions.sendFrom(
            Web3.to_checksum_address(address),
            int(DSTCHAINID),
            abi.encode( ["address"],[Web3.to_checksum_address(address)]),
            amountIn,
            amountIn,
            (
            Web3.to_checksum_address(address),
            '0x0000000000000000000000000000000000000000',
            eth_abi.packed.encode_packed(   ["uint16", "uint256", "uint256", "address"],
                                            [2, 250000, 0, Web3.to_checksum_address(address)])
            )
            ).build_transaction({
            'from': address,
            'value': value,
            'gas': int(gas),
            'gasPrice': int(gas_price),
            'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали BRIDGE {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'BRIDGE BTC.b {from_chain} to {to_chain} кол-во {amount}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при BRIDGE BTC.b {from_chain} to {to_chain} кол-во {amount}')
            return False, f'Ошибка при BRIDGE BTC.b {from_chain} to {to_chain} кол-во {amount}', ''
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для BRIDGE BTC.b {from_chain} to {to_chain}, кол-во {amount}')
            return False, f'Недостаточно средств для SWAP кол-во {amount}', str(Ex)
        logger.error(f'{name} | {address} | {log_name} | Ошибка при BRIDGE BTC.b {from_chain} to {to_chain}, кол-во {amount}')
        return False, f'Ошибка при BRIDGE BTC.b {from_chain} to {to_chain} кол-во {amount}', str(Ex)

    # Проверяем баланс кошелька на который отправили
    try:
        lv_count = 0
        while lv_count <= 360:
            try:
                balance_of_token_BTC_to2 = contractBTC_to.functions.balanceOf(address).call()
            except Exception as Ex:
                logger.error(f'{name} | {address} | {log_name} | Ошибка при balanceOf, {Ex}')
                time.sleep(60)
                continue
            human_balance_BTC_to2 = balance_of_token_BTC_to2/ 10 ** token_decimals_BTC_to
            logger.info(f'{name} | {address} | {log_name} | {token_symbol_BTC_to} = {human_balance_BTC_to2}, {to_chain}') 
            if balance_of_token_BTC_to < balance_of_token_BTC_to2:
                logger.success(f'{name} | {address} | {log_name} | {token_symbol_BTC_from} = {human_balance_BTC_to2}, BRIDGE выполнен') 
                return True
            lv_count += 1
            time.sleep(60)
        logger.error(f'{name} | {address} | {log_name} | {token_symbol_BTC_from} = {human_balance_BTC_to2}, не получили сумму от BRIDGE') 
        return False, f'Не получили сумму от BRIDGE кол-во {amount}', ''
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке перевода кол-во {amount}')
        return False, f'Ошибка при проверке перевода кол-во {amount}', str(Ex)
    