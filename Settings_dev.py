"""Untracked local development settings; credentials come only from the environment."""
import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get('RPW_LOG_PATH', str(BASE_DIR / 'logs')))
STATIC_DIR = BASE_DIR / 'rpw' / 'static'

Main = {
    'base_path': str(BASE_DIR),
    'log_path': str(LOG_DIR),
    'log_level': os.environ.get('RPW_LOG_LEVEL', 'INFO'),
    'log_formatter': logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'),
    'faq_file': str(STATIC_DIR / 'data' / 'faq.xml'),
}
Site = {
    'title': 'RARE PEPE WORLD',
    'title_alt': 'RarePepeWorld.com',
    'subtitle': 'The Rare Vault',
    'domain': 'http://127.0.0.1:55000',
    'email': 'rarepepeworld@pm.me',
    'google_analytics': False,
}
Sources = {
    'rpc': {
        'url': 'http://127.0.0.1:4000/api/', 'user': '', 'password': '',
        'version': '2.0', 'headers': {'content-type': 'application/json'},
    },
    'mysql': {
        'host': os.environ.get('RPW_DB_HOST', '127.0.0.1'),
        'user': os.environ.get('RPW_DB_USER', 'rpw_dev'),
        'password': os.environ.get('RPW_DB_PASSWORD', ''),
        'database_name': os.environ.get('RPW_DB_NAME', 'CounterpartyPepes'),
    },
    'xchain': {
        'api_base_url': 'https://xchain.io/api',
        'methods_available': [
            'address', 'asset', 'balances', 'bets', 'block', 'broadcasts', 'burns', 'credits', 'debits',
            'destructions', 'dispensers', 'dispenses', 'dividends', 'history', 'holders', 'issuances',
            'market', 'markets', 'mempool', 'network', 'order_matches', 'orders', 'sends', 'send_tx', 'tx', 'utxos',
        ],
    },
    'btcpayserver': {
        'client_store_file': str(STATIC_DIR / 'data' / 'btcpay_client_local'),
        'secret': os.environ.get('RPW_BTCPAY_WEBHOOK_SECRET', ''),
        'pay_url': 'http://127.0.0.1:55001',
    },
    'pepe_data': {
        'list_url': 'https://rarepepewallet.com/feed',
        'list_file': str(STATIC_DIR / 'data' / 'pepe-list.txt'),
        'images_path': str(STATIC_DIR / 'pepe_images') + os.sep,
        'rarepepedirectory_urls': str(STATIC_DIR / 'data' / 'RarePepeDirectory_Links.json'),
        'pepe_series_file': str(STATIC_DIR / 'data' / 'RarePepeDirectory_Series_Data.json'),
        'addresses': str(STATIC_DIR / 'data' / 'addresses.txt'),
        'qr_codes': str(STATIC_DIR / 'qr'),
        'artists': str(STATIC_DIR / 'data' / 'pepe-artists.txt'),
        'burn_addresses': str(STATIC_DIR / 'data' / 'burn_addresses.txt'),
        'db_state_file': str(STATIC_DIR / 'data' / 'db_latest_block'),
    },
}
Ads = {
    'default_ads': {'_RANDOM_': (0, '_RANDOM_', 0, '__default__'),
                    'PUMPURPEPE': (0, 'PUMPURPEPE', 0, '__default__'),
                    'PEPETRADERS': (0, 'PEPETRADERS', 0, '__default__')},
    'block_count': 720, 'currency': 'USD', 'price': '0.50',
    'notificationUrl': 'http://127.0.0.1:55000/B28vk',
    'redirectURL': 'http://127.0.0.1:55000/',
}
_LOGGERS = ('defaults', 'root', 'data', 'data_queries', 'errors', 'db_updater', 'ad_sequencer', 'purchases')
Logs = {
    'base_path': str(LOG_DIR),
    'formatter': Main['log_formatter'],
    'log_level': Main['log_level'],
    'loggers': {
        name: {
            'log_level': Main['log_level'],
            'log_file': LOG_DIR / ('run.log' if name in ('defaults', 'root') else f'{name}.log'),
            'log_formatter': Main['log_formatter'],
        } for name in _LOGGERS
    },
}
