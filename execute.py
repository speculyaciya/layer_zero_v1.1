from loguru import logger  as global_logger
import sys
import random
import pandas as pd
import execute_util
import main_config as c
import datetime
import time
import copy
from swap_settings import text
from threading import Thread, Lock, RLock
from termcolor import cprint

global_logger.remove()
logger = copy.deepcopy(global_logger)
logger.add(sys.stderr,
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")
logger.add('main.log',
        format="<white>{time: MM/DD/YYYY HH:mm:ss}</white> | <level>"
        "{level: <8}</level> | <cyan>"
        "</cyan> <white>{message}</white>")


csv_path = 'data.csv'
lock_data_csv = RLock()
lock_log_csv = RLock()

def pre_csv():
    data_csv = pd.read_csv(csv_path,keep_default_na=False)
    for index, row in data_csv.iterrows():
        if row[c.STARGATE] == '':
            data_csv.loc[index,f'{c.STARGATE}'] = 0
        # if row[c.STARGATE_BSC] == '':
        #     data_csv.loc[index,f'{c.STARGATE_BSC}'] = 0
        # if row[c.STARGATE_ARBITRUM] == '':
        #     data_csv.loc[index,f'{c.STARGATE_ARBITRUM}'] = 0
        # if row[c.STARGATE_OPTIMISM] == '':
        #     data_csv.loc[index,f'{c.STARGATE_OPTIMISM}'] = 0
        if row[c.STARGATE_LIQ] == '':
            data_csv.loc[index,f'{c.STARGATE_LIQ}'] = 0
        if row[c.STARGATE_STG] == '':
            data_csv.loc[index,f'{c.STARGATE_STG}'] = 0
        if row[c.BTC_BRIDGE] == '':
            data_csv.loc[index,f'{c.BTC_BRIDGE}'] = 0
        if row[c.TESTNET_BRIDGE] == '':
            data_csv.loc[index,f'{c.TESTNET_BRIDGE}'] = 0
        if row[c.APTOS_BRIDGE] == '':
            data_csv.loc[index,f'{c.APTOS_BRIDGE}'] = 0
        if row[c.HARMONY_BRIDGE] == '':
            data_csv.loc[index,f'{c.HARMONY_BRIDGE}'] = 0
        if row[c.SWAP_TOKEN] == '':
            data_csv.loc[index,f'{c.SWAP_TOKEN}'] = 0
    data_csv.to_csv(csv_path, index=False)



def execute(data_csv, index):
    row = data_csv.loc[index]
    prelog = f'{row["Name"]} | {row["Wallet"]}'
    logger.info(f'Выполеняется {prelog}')
    activity = execute_util.generate_activity(row=row)
    if activity == c.NO_ACTIVITY:
        data_csv.loc[index,'DO'] = 'DONE'
        execute_util.save_csv(data_csv, index)
        logger.warning(f'{prelog} | Активностей больше нет')
        return data_csv
    time.sleep(2)
    logger.info(f'{prelog} | Выбрано {activity}')

    wait_time = random.sample(c.WAIT_TIME,1)[0]
    nextTime = datetime.datetime.now() + datetime.timedelta(minutes=wait_time)
    time.sleep(2)
    logger.info(f'{prelog} | Следующий запуск в {nextTime}')
    while True:
        if datetime.datetime.now() > nextTime:
            break
        time.sleep(30)
    logger.info(f'{prelog} | Выполняем запуск')
    result = execute_util.execute_activity(activity=activity, data_csv=data_csv, row=row, index=index)

    if result == True:
        logger.success(f'{prelog} | Выполнено {activity}')
    else:
        logger.error(f'{prelog} | Ошибка {activity}')

def get_do_wallet(not_except: list):
    do_index_list = []
    lock_data_csv.acquire()
    time.sleep(1)
    data_csv = pd.read_csv(csv_path,keep_default_na=False)
    lock_data_csv.release()
    for index, row in data_csv.iterrows():
        if row['DO'] == 'X':
            do_index_list.append(index)
    if len(do_index_list) == 0:
        return 'FINISH', None, None
    do_index_list = list(set(do_index_list) - set(not_except))
    if len(do_index_list) == 0:
        return 'WAIT', None, None
    return 'DO', random.choice(do_index_list), data_csv

if __name__ == '__main__':

    cprint(text, 'yellow')
    cprint('\n                         -------     subscribe to us : https://t.me/spekulyantcrypto     -------', 'yellow')

    cprint('                         -------                         coders                          -------')
    cprint('                         --------------  Crypto-Selkie: https://t.me/tawer_crypt  --------------', 'green')
    cprint('                         --------------  Gefest_forge:  https://t.me/gefest_forge --------------', 'green')
    cprint('                         -------    donate:  0x9d9D67FAF623a2D78A1eaa07579b7128fCD79dd9  -------', 'white')

    pre_csv()

    count_threads = int(input('Кол-во потоков: '))
    threads       = []
    for i in range(count_threads):
        threads.append({'tread': None, 'index': None })

    execute_indexes = []
    end             = False

    while end == False:
        for i in range(len(threads)):
            if threads[i]['index'] == None:
                time.sleep(10)
                result, new_execute_index, data_csv = get_do_wallet(execute_indexes)
                if result   == 'FINISH':
                    end = True
                    break
                elif result == 'WAIT':
                    continue
                elif result == 'DO':
                    threads[i]['index'] = new_execute_index
                    execute_indexes.append(new_execute_index)
                    threads[i]['tread'] = Thread(target=execute, args=(data_csv, new_execute_index))
                    threads[i]['tread'].start()
                    continue
            else:
                if threads[i]['tread'].is_alive():
                    continue
                else:
                    execute_indexes.remove(threads[i]['index'])
                    threads[i]['index'] = None
                    break
        time.sleep(30)
        