from web3 import Web3
from loguru import logger as global_logger
from os import path
import time
import testnet_settings as s
import ZBC
import eth_abi.packed
from decimal import Decimal
import copy

def testnet_bridge(name, proxy, private_key, from_chain, max_bridge, max_gas, max_value):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    log_name = f'TESTNET BRIDGE {from_chain} to GOERLIETH'
    to_chain = 'GOERLIETH'

    from_data = ZBC.search_setting_data(chain=from_chain, list=s.SETTING_TESTNETBRIDGE_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации from_chain')
        return False
    else:
        from_data = from_data[0]
    to_data = ZBC.search_setting_data(chain=to_chain, list=s.SETTING_TESTNETBRIDGE_LIST)
    if len(to_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации to_chain')
        return False
    else:
        to_data = to_data[0]

    ROUND = 6
    RPC_FROM = from_data['RPC']
    RPC_TO = to_data['RPC']
    BRIDGE = from_data['BRIDGE']
    BRIDGE_ABI = from_data['BRIDGE_ABI']
    OFT = from_data['OFT']
    OFT_ABI = from_data['OFT_ABI']
    SLIPPAGE = from_data['SLIPPAGE']
    DSTCHAINID = to_data['CHAINID']

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
    
    #   Получаем из from
    balance = w3_from.eth.get_balance(address)
    human_balance = round(w3_from.from_wei(balance, "ether").real,ROUND)
    logger.info(f'{name} | {address} | {log_name} | ETH = {human_balance}, {from_chain}')

    # Проверяем, что есть токены
    if human_balance == 0:
        logger.error(f'{name} | {address} | {log_name} | Нет токенов') 
        return False, f'Нет токенов', ''
    if human_balance > max_bridge:
        amountIn = w3_from.to_wei(max_bridge, "ether")
        amount = round(Decimal(max_bridge), ROUND)
    else:
        amountIn = balance
        amount = human_balance
    logger.info(f'{name} | {address} | {log_name} | Будет BRIDGE {amount} из {from_chain} в {to_chain}')
    amountOutMin = amountIn - (amountIn * SLIPPAGE) // 1000
    human_amountOutMin = round(w3_from.from_wei(amountOutMin, "ether").real, ROUND)
    logger.info(f'{name} | {address} | {log_name} | Минимальная ожидаемая сумма от BRIDGE {human_amountOutMin} из {from_chain} в {to_chain}')

    #   Получаем до bridge в to_chain 
    balance_to = w3_to.eth.get_balance(address)
    human_balance_to = round(w3_to.from_wei(balance_to, "ether").real, ROUND)
    logger.info(f'{name} | {address} | {log_name} | ETH = {human_balance_to}, {to_chain}')

    # Делаем BRIDGE 
    try:
        # Полчаем контракт ENDPOINT и BRIDGE
        contractENDPOINT = w3_from.eth.contract(address=w3_from.to_checksum_address(OFT), abi=OFT_ABI)
        contractBRIDGE = w3_from.eth.contract(address=w3_from.to_checksum_address(BRIDGE), abi=BRIDGE_ABI)
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            # Узнаем сначала value
            value = contractENDPOINT.functions.estimateSendFee(
                int(DSTCHAINID),
                w3_from.to_checksum_address(address),
                amountIn,
                False,
                eth_abi.packed.encode_packed([], []),
                ).call()
            value = value[0]
            human_value = round(w3_from.from_wei(value, "ether").real, ROUND)
            if human_value < max_value:
                logger.info(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}')
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue
            
            value_transaction = value + amountIn

            # Узнаем GAS
            gas = contractBRIDGE.functions.swapAndBridge(
                amountIn,
                amountOutMin,
                int(DSTCHAINID),
                address,
                address,
                '0x0000000000000000000000000000000000000000',
                '0x'
                ).estimate_gas({'from': address, 'value':value_transaction , 'nonce': nonce })
            gas = gas * 1.2
            gas_price = w3_from.eth.gas_price
            txCost = gas * gas_price
            txCostInEther = round(w3_from.from_wei(txCost, "ether").real,ROUND)
            if txCostInEther < max_gas:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на BRIDGE {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на BRIDGE {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue

        # Выполняем BRIDGE
        transaction = contractBRIDGE.functions.swapAndBridge(
                    amountIn,
                    amountOutMin,
                    int(DSTCHAINID),
                    address,
                    address,
                    '0x0000000000000000000000000000000000000000',
                    eth_abi.packed.encode_packed(   [],
                                                    [])
            ).build_transaction({
            'from': address,
            'value': value_transaction,
            'gas': int(gas),
            'gasPrice': int(gas_price),
            'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали BRIDGE {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'BRIDGE {from_chain} to {to_chain} кол-во {amount}', logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при BRIDGE {from_chain} to {to_chain} кол-во {amount}')
            return False, f'Ошибка при BRIDGE {from_chain} to {to_chain} кол-во {amount}', ''
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для BRIDGE {from_chain} to {to_chain}, кол-во {amount}')
            return False, f'Недостаточно средств для SWAP кол-во {amount}', str(Ex)
        logger.error(f'{name} | {address} | {log_name} | Ошибка при BRIDGE {from_chain} to {to_chain}, кол-во {amount}')
        return False, f'Ошибка при BRIDGE {from_chain} to {to_chain} кол-во {amount}', str(Ex)
    
    # Проверяем баланс кошелька на который отправили
    try:
        lv_count = 0
        while lv_count <= 360:
            try:
                balance_to2 = w3_to.eth.get_balance(address)
            except Exception as Ex:
                logger.error(f'{name} | {address} | {log_name} | Ошибка при balanceOf, {Ex}')
                time.sleep(60)
                continue
            human_balance_to2 = round(w3_to.from_wei(balance_to2, "ether").real, ROUND)
            logger.info(f'{name} | {address} | {log_name} | ETH = {human_balance_to2}, {to_chain}') 
            if balance_to < balance_to2:
                logger.success(f'{name} | {address} | {log_name} | ETH = {human_balance_to2}, BRIDGE выполнен') 
                return True
            lv_count += 1
            time.sleep(60)
        logger.error(f'{name} | {address} | {log_name} | ETH = {balance_to2}, не получили сумму от BRIDGE') 
        return False, f'Не получили сумму от BRIDGE кол-во {amount}', ''
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке перевода кол-во {amount}')
        return False, f'Ошибка при проверке перевода кол-во {amount}', str(Ex)