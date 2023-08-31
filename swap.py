from web3 import Web3
from loguru import logger as global_logger
import ZBC
import swap_settings as s
from main_config import headers
import time
import requests
from decimal import Decimal
import copy

def get_api_call_data(chain_id, from_token_address, to_token_address, amount_to_swap, wallet, slippage, logger, proxy='',):
    url = f'https://api.1inch.dev/swap/v5.2/{chain_id}/swap?fromTokenAddress={from_token_address}&toTokenAddress={to_token_address}&amount={amount_to_swap}&fromAddress={wallet}&slippage={slippage}'
    try:
        try:
            if proxy != '':
                proxies = {
                    'http': proxy,
                    'https': proxy,
                }
                call_data = requests.get(url, proxies=proxies, headers=headers)
            else:
                call_data = requests.get(url, headers=headers)
        except:
            call_data = requests.get(url, headers=headers)

        if call_data.status_code == 200:
            api_data = call_data.json()
            return api_data
        else:
            print(call_data.text)
            logger.info('1inch get_api_call_data() try again')
            time.sleep(30)
            api_data = get_api_call_data(
                chain_id           = chain_id,
                from_token_address = from_token_address,
                to_token_address   = to_token_address,
                amount_to_swap     = amount_to_swap,
                wallet             = wallet,
                slippage           = slippage,
                proxy              = proxy,
                logger             = logger)
            return api_data

    except Exception as error:
        logger.info(error)
        time.sleep(3)
        api_data = get_api_call_data(
            chain_id           = chain_id,
            from_token_address = from_token_address,
            to_token_address   = to_token_address,
            amount_to_swap     = amount_to_swap,
            wallet             = wallet,
            slippage           = slippage,
            proxy              = proxy,
            logger             = logger)
        return api_data
    
def swap_token(name, proxy, private_key, from_chain:str, token, amount, max_gas=0):
    global_logger.remove()
    logger = copy.deepcopy(global_logger)
    logger.add(
        fr'log_wallet\log_{name}.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
    
    ROUND = 6
    amount = round(Decimal(amount), ROUND).real
    log_name = f'SWAP TOKEN {token} = {amount} {from_chain}'

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
    token_data = ZBC.search_setting_data_by_element(element_search = _element, value=token, list=from_data['token_list'])
    if len(token_data) == 0:
        logger.error(f'{name} | {log_name} | Ошибка при поиске информации {_element}')
        return False
    else:
        token_data = token_data[0]

    if max_gas == 0:
        MAX_GAS = from_data['max_gas']
    else:
        MAX_GAS = max_gas
    SLIPPAGE             = 5

    RPC_FROM             = from_data['rpc']
    CHAIN_ID_FROM        = from_data['chain_id']
    TOKEN_FROM           = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
    TOKEN                = Web3.to_checksum_address(token_data['address'])
    TOKEN_ABI            = token_data['abi']

    # Подключаемся и проверяем
    w3_from = Web3(Web3.HTTPProvider(RPC_FROM, request_kwargs={"proxies":{'https' : proxy, 'http' : proxy },"timeout":120}))
    if w3_from.is_connected() == True:
        account = w3_from.eth.account.from_key(private_key)
        address = account.address
        logger.success(f'{name} | {address} | {log_name} | Подключились к {from_chain}, {RPC_FROM}')
    else:
        logger.error(f'{name} | {log_name} | Ошибка при подключении к {from_chain}, {RPC_FROM}')
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
        logger.info(f'{name} | {address} | {log_name} | {token_symbol_to} = {human_balance_to1}, сумма до перевода | {from_chain}')

        amountIn             = int(w3_from.to_wei(amount, "ether"))
        # amountIn             = int(amount * 10 ** token_decimals_to)
    except Exception as Ex:
        logger.error(f'{name} | {address} | {log_name} | Ошибка при проверке баланса | {from_chain}, \n {str(Ex)}')
        return False

    try:
        while True:
            transaction = get_api_call_data(
                chain_id           = CHAIN_ID_FROM,
                from_token_address = TOKEN_FROM,
                to_token_address   = TOKEN,
                amount_to_swap     = amountIn,
                wallet             = address,
                slippage           = SLIPPAGE,
                logger             = logger,
                proxy              = proxy)['tx']
            if transaction == False:
                return False
            gas = int(transaction['gas'])
            gas_price = int(transaction['gasPrice'])
            txCost = gas * gas_price
            txCostInEther = w3_from.from_wei(txCost, "ether").real
            if txCostInEther < MAX_GAS:
                logger.info(f'{name} | {address} | {log_name} | Стоимость газа на SWAP {txCostInEther}, {from_chain}')
                break
            else:
                logger.warning(f'{name} | {address} | {log_name} | Стоимость газа на SWAP {txCostInEther}, {from_chain}, это больше максимума')
                time.sleep(60)

        transaction['chainId']   = int(CHAIN_ID_FROM)
        transaction['nonce']     = w3_from.eth.get_transaction_count(address)
        transaction['to']        = Web3.to_checksum_address(transaction['to'])
        transaction['gasPrice']  = int(transaction['gasPrice'])
        transaction['gas']       = int(int(transaction['gas']))
        transaction['value']     = int(transaction['value'])

        signed_transaction = account.sign_transaction(transaction)
        transaction_hash = w3_from.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logger.success(f'{name} | {address} | {log_name} | Подписали SWAP {transaction_hash.hex()}')
        status = ZBC.transaction_verification(name, transaction_hash, w3_from, log_name=log_name, text=f'SWAP кол-во {amount}, {from_chain}',  logger=logger)
        if status == False:
            logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP кол-во {amount}, {from_chain}, \n {str(Ex)}')
            return False
    except Exception as Ex:
        if "insufficient funds for gas * price + value" in str(Ex):
            logger.error(f'{name} | {address} | {log_name} | Недостаточно средств для SWAP кол-во {amount}, {from_chain}, \n {str(Ex)}')
            return False
        logger.error(f'{name} | {address} | {log_name} | Ошибка при SWAP кол-во {amount}, {from_chain}, \n {str(Ex)}')
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