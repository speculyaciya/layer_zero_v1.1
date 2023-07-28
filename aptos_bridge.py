from web3 import Web3
from loguru import logger as global_logger
import time
import aptos_bridge_settings as s
import ZBC
from eth_abi import abi
import eth_abi.packed
from decimal import Decimal
import copy

def aptos_bridge(name, proxy, private_key, from_chain, wallet, amount, max_gas, max_value):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    log_name = f'APTOS BRIDGE {from_chain} to APTOS'
    to_chain = 'APTOS'

    from_data = ZBC.search_setting_data(chain=from_chain, list=s.CHAIN_LIST)
    if len(from_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации from_chain')
        return False
    else:
        from_data = from_data[0]

    RPC_FROM          = from_data['RPC']
    BRIDGE            = from_data['BRIDGE']
    BRIDGE_ABI        = from_data['BRIDGE_ABI']
    TOKEN_FROM        = from_data['USDC']
    TOKEN_ABI_FROM    = from_data['USDC_ABI']
    WALLET            = wallet

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {from_chain}')
        return False, f'Ошибка при подключении {RPC_FROM}', ''
    
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
            if balance_of_token_from >= amountIn * 0.99:
                amountIn = balance_of_token_from
            else:
                logger.info(f'{name} | {address} | {log_name} | {token_symbol_from} = {human_balance} суммы НЕ достаточно | {from_chain}')
                logger.error(f'{name} | {address} | {log_name} | {token_symbol_from} = {human_balance} суммы НЕ достаточно | {from_chain}')

                return False

    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке баланса | {from_chain} \n {str(Ex)}')
        return False
    
    logger.info(f'{name} | {address} | {log_name} | Будет BRIDGE {amount} из {from_chain} в {to_chain}')

    # Делаем approve суммы
    try:
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            gas = contractTOKEN_from.functions.approve(
                w3_from.to_checksum_address(BRIDGE),
                amountIn
                ).estimate_gas({'from': address, 'nonce': nonce, })
            gas = gas * 1.2
            # дефолтный газ в BSC = 5 gwei, с рпц от анкр можем юзать 1 gwei, но с 1 gwei проблемы периодически, поэтому 1.1 gwei сделал.
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
                w3_from.to_checksum_address(BRIDGE),
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

    # BRIDGE to Aptos
    try: 
        contractBRIDGE = w3_from.eth.contract(address=w3_from.to_checksum_address(BRIDGE), abi=BRIDGE_ABI)
        nonce = w3_from.eth.get_transaction_count(address)
        while True:
            # Узнаем коммисию за bridge  
            value = contractBRIDGE.functions.quoteForSend(
                [address,'0x0000000000000000000000000000000000000000'],
                eth_abi.packed.encode_packed(["uint16", "uint256", "uint256", "address"],
                                             [2, 4000, 0, address]),
            ).call()
            value = value[0]
            human_value = w3_from.from_wei(value, "ether").real
            if human_value < max_value:
                logger.info(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}')
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость value на bridge {human_value}, {from_chain}, это больше максимума')
                time.sleep(30)
                continue

            gas = contractBRIDGE.functions.sendToAptos(
                TOKEN_FROM,
                WALLET,
                amountIn,
                [address,'0x0000000000000000000000000000000000000000'],
                eth_abi.packed.encode_packed(["uint16", "uint256", "uint256", "address"],
                                             [2, 4000, 0, address]),
                ).estimate_gas({'from': address, 'value':value, 'nonce': nonce, })
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

        transaction = contractBRIDGE.functions.sendToAptos(
            TOKEN_FROM,
            WALLET,
            amountIn,
            [address,'0x0000000000000000000000000000000000000000'],
            eth_abi.packed.encode_packed(["uint16", "uint256", "uint256", "address"],
                                            [2, 4000, 0, address]),
            ).build_transaction({
                'from': address,
                'value': value,
                'gas': int(gas),
                'gasPrice': int(gas_price),
                'nonce': nonce})
        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'кол-во {amount} | {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка кол-во {amount} | {from_chain}')
            return False
        return True
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств кол-во {amount} | {from_chain} \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка кол-во {amount} | {from_chain} \n {str(Ex)}')
        return False
    
