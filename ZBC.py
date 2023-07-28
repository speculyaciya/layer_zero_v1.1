from web3 import Web3
from loguru import logger
import json
from os import path
import sys
from dateutil.relativedelta import relativedelta
from datetime import datetime
import time
import random
import stargate_settings as s
import datetime

def search_setting_data_by_element(element_search, value, list):
    return [element for element in list if element[element_search] == value]

def search_setting_data(chain, list):
    return [element for element in list if element['CHAIN'] == chain]

def transaction_verification(name, transaction_hash, w3:Web3, log_name, text, logger):
    time.sleep(60)
    try:
        transaction_data = w3.eth.wait_for_transaction_receipt(transaction_hash, timeout=600)
        if transaction_data.get('status') != None and transaction_data.get('status') == 1:
            logger.success(f'{name} | {transaction_data.get("from")} | {log_name} | Успешная транзакция: {transaction_hash.hex()} | {text}')
            return True
        else:
            logger.error(f'{name} | {transaction_data.get("from")} | {log_name} | Ошибка транзакции: {transaction_data.get("transactionHash").hex()} | {text}')
            return False
    except Exception as e:
        logger.error(f'{name} | {transaction_hash.hex()} | {log_name} | Ошибка транзакции: {e} | {text}')
        return False