#!../venv/bin/python

import set_paths
from pprint import pprint
from pycoingecko import CoinGeckoAPI
from db_updater import MysqlUpdater

BASE_CURRENCY = 'USD'
FIAT_LIST = {
    'USD': 'US Dollar',
    'IDR': 'Indonesian Rupiah',
    'TWD': 'New Taiwan Dollar',
    'EUR': 'Euro',
    'KRW': 'South Korean Won',
    'JPY': 'Japanese Yen',
    'RUB': 'Russian Ruble',
    'CNY': 'Chinese Yuan',
    'AED': 'United Arab Emirates Dirham',
    'ARS': 'Argentine Peso',
    'AUD': 'Australian Dollar',
    'BDT': 'Bangladeshi Taka',
    'BHD': 'Bahraini Dinar',
    'BMD': 'Bermudian Dollar',
    'BRL': 'Brazil Real',
    'CAD': 'Canadian Dollar',
    'CHF': 'Swiss Franc',
    'CLP': 'Chilean Peso',
    'CZK': 'Czech Koruna',
    'DKK': 'Danish Krone',
    'GBP': 'British Pound Sterling',
    'HKD': 'Hong Kong Dollar',
    'HUF': 'Hungarian Forint',
    'ILS': 'Israeli New Shekel',
    'INR': 'Indian Rupee',
    'KWD': 'Kuwaiti Dinar',
    'LKR': 'Sri Lankan Rupee',
    'MMK': 'Burmese Kyat',
    'MXN': 'Mexican Peso',
    'MYR': 'Malaysian Ringgit',
    'NGN': 'Nigerian Naira',
    'NOK': 'Norwegian Krone',
    'NZD': 'New Zealand Dollar',
    'PHP': 'Philippine Peso',
    'PKR': 'Pakistani Rupee',
    'PLN': 'Polish Zloty',
    'SAR': 'Saudi Riyal',
    'SEK': 'Swedish Krona',
    'SGD': 'Singapore Dollar',
    'THB': 'Thai Baht',
    'TRY': 'Turkish Lira',
    'UAH': 'Ukrainian hryvnia',
    'VEF': 'Venezuelan bolívar fuerte',
    'VND': 'Vietnamese đồng',
    'ZAR': 'South African Rand',
    'XDR': 'IMF Special Drawing Rights'
}
CRYPTO_LIST = {'bitcoin': 'BTC', 'counterparty': 'XCP', 'pepecash': 'PEPECASH'}
DB_TABLE = 'prices'


def run():
    cg = CoinGeckoAPI()
    m = MysqlUpdater(pepe_populator_mode=False)

    def get_price(from_currency: str, to_currency: str) -> dict:
        return cg.get_price(ids=from_currency, vs_currencies=to_currency)

    crypto_prices_list = get_price(','.join(CRYPTO_LIST.keys()), 'USD')
    pprint(f"crypto_prices_list: {crypto_prices_list}")

    for crypto_name in crypto_prices_list.keys():
        print(f"crypto_name: {crypto_name}")
        match_conditions = [{'field': 'currency', 'value': CRYPTO_LIST[crypto_name]}]
        updates = {
            'usd_rate': crypto_prices_list[crypto_name]['usd']
        }
        print(f"match_conditions: {match_conditions}\nupdates: {updates}")
        m.db_update(table=DB_TABLE, data=updates, match_conditions=match_conditions)


if __name__ == "__main__":
    run()
