# --*-- coding:utf-8 --*--
import datetime
import json
import logging
import random
from pathlib import Path
from pprint import pformat
from typing import List

import requests
from bs4 import BeautifulSoup

import Settings
from rpw.DataConnectors import DBConnector, RPCConnector, BTCPayServerConnector, XChainConnector
from rpw.Utils import JSONTool

DB_TABLE_FIELDS = {  # List of fields corresponding to the values from a query result for each table
    'assets': ['id', 'asset', 'asset_longname', 'description', 'divisible', 'issuer', 'owner', 'source', 'locked',
               'supply', 'series', 'rarepepedirectory_url', 'image_file_name', 'real_supply'],
    'dispensers': ['id', 'asset', 'block_index', 'escrow_quantity', 'give_quantity', 'give_remaining', 'satoshirate',
                   'source', 'status', 'tx_index', 'tx_hash'],
    'holdings': ['id', 'address', 'asset', 'address_quantity', 'escrow'],
    'addresses': ['id', 'address'],
    'orders': ['tx_index', 'tx_hash', 'block_index', 'source', 'give_asset', 'give_quantity', 'give_remaining',
               'get_asset', 'get_quantity', 'get_remaining', 'expiration', 'expire_index', 'fee_required',
               'fee_required_remaining', 'fee_provided', 'fee_provided_remaining', 'status']
}


class PepeData:
    """ Class for obtaining pepe information and dealing with various data requirements """

    def __init__(self, db_connector: DBConnector, loggers=None):
        """ Initiate the object using the provided database connection tool.
        :param db_connector: DBConnector object for communication with the underlying db.
        """
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        self.db_connection = db_connector  # db source of pepe data
        self.pepe_names = self.get_pepe_names()  # list of tuples: (pepe_name, pepe_id)
        self.pepe_images = self.get_pepe_image_file_names()  # dictionary of image filenames for each Pepe

    def get_pepe_details(self, pepe_name: str) -> dict:
        """ Details for each any pepe stored in the database
        :param pepe_name: The name of the pepe
        :return: tuple representing the pepe record, or None if no match found
        """
        query = f'SELECT * FROM assets WHERE asset=\'{pepe_name}\''
        query_data = self.db_connection.query_and_fetch(query)
        if len(query_data) > 0:
            return query_data[0]
        else:
            return {}

    def get_pepe_dispensers(self, pepe_name: str) -> List[dict]:
        """ List of pepe dispensers for a particular pepe.
        :param pepe_name: Name of the pepe.
        :return: List of dictionary entries representing each dispenser
        """
        query = f'SELECT * FROM dispensers WHERE asset=\'{pepe_name}\' ' \
                f'AND SUBSTRING(source,1,1)<>\'3\' ' \
                f'AND give_remaining>0 ' \
                f'AND status<>10'
        data = self.db_connection.query_and_fetch(query)
        dispensers = []
        if data:
            for dispenser_data in data:
                dispensers.append(dispenser_data)
        else:
            return []
        return dispensers

    def get_latest_pepe_dispensers(self, count: int = 5) -> List[dict]:
        """ Return the latest pepe dispensers in the db
        :param count Number of dispensers to list
        :return: List of dictionary entries representing each dispenser
        """
        query = f'SELECT * FROM dispensers ' \
                f'WHERE give_remaining>0 ' \
                f'AND asset<>\'XCP\' ' \
                f'AND asset<>\'PEPECASH\' ' \
                f'AND status<>10 ' \
                f'ORDER BY block_index DESC LIMIT {count}'
        data = self.db_connection.query_and_fetch(query)
        dispensers = []
        if data:
            for dispenser_data in data:
                dispensers.append(dispenser_data)
        return dispensers

    def get_pepe_holdings(self, pepe_name: str) -> List[dict]:
        """ Return the pepe holdings for a particular pepe.
        :param pepe_name: Name of the pepe.
        :return: List of dictionaries representing each holder and holdings
        """
        query = f'SELECT * FROM holdings WHERE asset=\'{pepe_name}\' ORDER BY address_quantity DESC'
        data = self.db_connection.query_and_fetch(query)
        holdings = []
        if data:
            for holding_data in data:
                holdings.append(holding_data)
        return holdings

    def derive_pepe_real_supply(self, pepe_name: str) -> int:
        """ Calculate holdings of a pepe, taking into consideration quantities known to have been burned and
        the divisibility status of the pepe. """
        pepe_details = self.get_pepe_details(pepe_name)
        real_holdings_quantity = pepe_details['supply']
        pepe_holdings = self.get_pepe_holdings(pepe_name)
        for pepe_holder in pepe_holdings:
            if self.is_burn_address(pepe_holder['address']):
                real_holdings_quantity -= pepe_holder['address_quantity']
        return real_holdings_quantity

    def get_pepes_by_pattern(self, pattern: str) -> List[dict]:
        """ Find all pepe details for each Pepe that contains the given pattern
        :param pattern: String representing the pattern to match in the Pepe name
        :return: List of dictionary entries for each Pepe
        """
        matched_pepes = sorted([pepe_name for pepe_name in self.pepe_names if pattern in pepe_name])
        matched_data = []
        for matched_pepe in matched_pepes:
            matched_data.append(self.get_pepe_details(matched_pepe))
        return matched_data

    def get_address_holdings(self, address: str) -> list:
        """ List of assets for which an address is a holder.
        :param address: The address to lookup.
        :return: A dictionary connecting to a list of dictionaries entries pertaining to the address
        """
        query = f"SELECT * FROM holdings WHERE address=\'{address}\' ORDER BY asset"
        data = self.db_connection.query_and_fetch((query))
        holdings = []
        if data:
            for holding_data in data:
                holdings.append(holding_data)
        return holdings

    def is_burn_address(self, address: str) -> bool:
        """ Determine if a particular address is listed as a burn address.
        :param address the address to be checked.
        :return True if address is as burn address, false otherwise. """
        query = f"SELECT is_burn FROM addresses WHERE address='{address}'"
        results = self.db_connection.query_and_fetch(query)
        if results:
            return bool(results[0].get('is_burn', False))
        return False

    def get_address_artists(self, address: str) -> list:
        """ List of assets for which address is an issuer.
        :param address: The address to lookup.
        :return: A list of issuances and their corresponding data
        """
        query = f"SELECT * FROM assets WHERE source='{address}'"
        data = self.db_connection.query_and_fetch(query)
        issuances = []
        if data:
            for issuances_data in data:
                issuances.append(issuances_data)
        return issuances

    def get_pepe_orders(self, pepe_name: str, status: str = 'open', base_asset: str = '') -> dict:
        """ Get all orders corresponding to a particular pepe.
        :param pepe_name: name of pepe
        :param status: status of the orders to lookup
        :param base_asset: PEPECASH, or XCP base asset, or neither to set as base asset of orders
        :return: a dictionary with 'get' and 'give' keys corresponding to get and give orders for the pepe
        """
        if not base_asset:
            query_get = f'SELECT * FROM orders WHERE get_asset=\'{pepe_name}\' AND status=\'{status}\''
            query_give = f'SELECT * FROM orders WHERE give_asset=\'{pepe_name}\' AND status=\'{status}\''
        else:
            query_get = f'SELECT * FROM orders WHERE get_asset=\'{pepe_name}\' AND status=\'{status}\' ' \
                        f'AND give_asset=\'{base_asset}\''
            query_give = f'SELECT * FROM orders WHERE give_asset=\'{pepe_name}\' AND status=\'{status}\' ' \
                         f'AND get_asset=\'{base_asset}\';'
        orders_data_get = self.db_connection.query_and_fetch(query_get)
        orders_data_give = self.db_connection.query_and_fetch(query_give)
        orders_get, orders_give = [], []
        if orders_data_get:
            for order_data in orders_data_get:
                orders_get.append(order_data)
        if orders_data_give:
            for order_data in orders_data_give:
                orders_give.append(order_data)
        return {
            'get': orders_get,
            'give': orders_give
        }

    def get_random_pepes(self, count: int = 54) -> list:
        """
        Generate a list of random pepe names

        :param count: quantity of pepes to return
        :return: list of pepe names
        """

        random_pepes = set()
        while len(random_pepes) < count:
            random_pepes.add(random.choice(self.get_pepe_names()))
        return list(random_pepes)

    def featured_pepe_random(self, count: int = 54):
        """
        Randomly select a pepe that has a recent dispenser open
        :param count: Number of pepes to select from
        :return: randomly selected pepe name.
        """
        query = f"SELECT * FROM dispensers " \
                f"WHERE asset <> 'XCP' AND asset <> 'PEPECASH' " \
                f"ORDER BY block_index DESC LIMIT {count}"
        db_results = self.db_connection.query_and_fetch(query)
        latest_pepes = sorted(set([result['asset'] for result in db_results]))
        return random.choice(latest_pepes)

    def get_featured_pepes(self) -> list:
        """
        Determine which pepes to show in the featured pepes section from the ad_slots database table.
        :return: list of pepe names to be placed in featured pepes list
        """
        # slot_defaults = ['_RANDOM_', 'PUMPURPEPE', 'PEPETRADERS']
        # featured_pepes = slot_defaults[:]  # set to defaults

        # Get current slot entries
        slots_query = "SELECT asset FROM ad_slots"
        slots_db_results = self.db_connection.query_and_fetch(slots_query)
        current_slots_entries = [slot_entry['asset'] for slot_entry in slots_db_results]

        for i, entry in enumerate(current_slots_entries):
            if entry == '_RANDOM_':
                current_slots_entries[i] = self.featured_pepe_random()
        return current_slots_entries

    @staticmethod
    def load_pepe_names() -> List[str]:
        """ Get the list of pepe names.  Attempt to load it from the local file. If the local file does not exists,
        query the internet for the list.
        :return: List of pepe names.
        """
        logging.info("Getting pepes list.")
        # check pepe list file already exists. If so, load it.
        if Path(Settings.Sources['pepe_data']['list_file']).exists():
            pepe_list = []
            logging.info("Loading pepe list from the cache file.")
            with open(Settings.Sources['pepe_data']['list_file']) as f:
                pepe_lines = f.readlines()
                for pepe_line in pepe_lines:
                    pepe_name = pepe_line.strip()
                    pepe_list.append(pepe_name)
        else:  # not available from file. Get from feed url
            logging.info(f"Pulling data from {Settings.Sources['pepe_data']['list_url']}")
            pepe_data = JSONTool.query_endpoint(Settings.Sources['pepe_data']['list_url'])
            pepe_name_list = [pepe_name for pepe_name in pepe_data.keys()] + ['XCP']
            pepe_list = [(pepe_name, PepeData.get_pepe_id(pepe_name)) for pepe_name in pepe_name_list]
            # for cache purpose, write the acquired list to the list file
            logging.info("Writing pepe list to cache file.")
            with open(Settings.Sources['pepe_data']['list_file'], 'w') as cp_file:
                cp_file.writelines('\n'.join(pepe_name_list) + '\n')
        logging.info("Done.")
        return pepe_list

    def get_pepe_names(self) -> List[str]:
        """ Generates the list pepe names from the database
        :return: list of strings of pepe names
        """
        query = 'SELECT asset FROM assets'
        results = self.db_connection.query_and_fetch(query)
        return [result['asset'] for result in results]

    def get_pepe_image_file_names(self) -> dict:
        """ Generates the list pepe image file names from the database.
        :return: list of strings of pepe image file names
        """
        query = 'SELECT image_file_name FROM assets'
        results = self.db_connection.query_and_fetch(query)
        return {
            result['image_file_name'].split('.')[:-1][0]: result['image_file_name'] for result in results
        }

    @classmethod
    def get_pepe_id(cls, pepe_reference: str or int) -> str:
        """ Convert Pepe name to Pepe Id that is used by the RPC, or convert the pepe_reference to valid form, as
        defined in the Counterparty documentation: https://counterparty.io/docs/protocol_specification/
        :param pepe_reference: Pepe name or pepe id number
        :return: str representing the pepe id number
        """
        if type(pepe_reference) == int:
            pepe_reference = str(pepe_reference)
        if type(pepe_reference) == str and pepe_reference.isnumeric():
            return pepe_reference
        if pepe_reference == 'XCP':
            p_id = 1
        elif pepe_reference[0] == 'A':
            p_id = pepe_reference[1:]
        else:
            n = 0
            charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            for ch in pepe_reference:
                n *= 26
                n += charset.index(ch)
            p_id = n
        return p_id

    def get_pepe_image_filename(self, pepe_name: str):
        """ Return the image file name for a particular pepe.
        :param pepe_name: Pepe name to find the filename for
        :return: Name of the image filename corresponding to a particular pepe asset
        """
        return self.pepe_images[pepe_name]

    @staticmethod
    def load_image_file_names() -> dict:
        """ List of the names of the Pepe image file names
        :return: dictionary with the key as the Pepe name and the value as the filename
        """
        logging.info("Loading list of image files for Pepes.")
        image_path = Path(Settings.Sources['pepe_data']['images_path'])
        pepe_image_file_paths = image_path.iterdir()
        pepe_image_files = {pepe_image_file_path.name.split('.')[0]: pepe_image_file_path.name
                            for pepe_image_file_path in pepe_image_file_paths}
        logging.info("Done.")
        pepe_image_files['XCP'] = 'XCP.png'  # hard code non pepe asset XCP
        return pepe_image_files

    @staticmethod
    def is_valid_pepe_name(asset_name: str):
        """ Check if a given asset_name corresponds to a valid counterparty rules for asset names
        :param asset_name: the asset name to check for validity
        :return: True if a valid name, False otherwise
        """
        if asset_name[0] == 'A':
            if not asset_name[1:].isnumeric():
                return False
            if not 26 ** 12 <= int(asset_name[1:]) <= 256 ** 8:
                return False
        else:
            if not (4 <= len(asset_name) <= 13):
                return False
            if not (asset_name[1:].isalpha() and asset_name.isupper()):
                return False
        return True


class CPData:
    """ Object to perform data queries to a Counterparty RPC """
    INITIAL_BLOCK = 278270  # first Bitcoin block used by Counterparty

    def __init__(self, rpc_connection: RPCConnector, loggers=None):
        """ Initiate CPData object with the given rpc_connection
        :param rpc_connection: RPCConnector object query tool
        """
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        self.rpc_connection = rpc_connection

    def get_btc_current_block(self) -> str:
        """ Most recent synced block by the running Bitcoin full node.
        :return: the most recent block known by the running Bitcoin node
        """
        return self.rpc_connection.query('get_running_info')['result']['bitcoin_block_count']

    def get_cp_last_block(self) -> str:
        """ Most recent synced block by the running Counterparty node.
        :return: the most recent block known by the running Counterparty node
        """
        return self.rpc_connection.query('get_running_info')['result']['last_block']['block_index']

    def is_db_caught_up(self) -> bool:
        """ Check if Counterparty node's latest known block matches the Bitcoin node's latest known block.
        :return: True if block numbers match, False otherwise
        """
        return self.rpc_connection.query('get_running_info')['result']['db_caught_up']

    def get_pepes_details(self, pepe_name: str) -> dict:
        """ Current details of a pepe asset.
        :param pepe_name:
        :return:
        """
        return self.rpc_connection.query("get_asset_info", params={'assets': [pepe_name]})['result'][0] or {}

    def get_table_for_pepe(self, table_type: str, pepe_name: str) -> dict:
        """ General function for querying any of the options of pattern get_{table}
        :param table_type: the type of get query
        :param pepe_name: name of the pepe to get the particular table for
        :return: cp result
        """
        method = "get_" + table_type
        return self.rpc_connection.query(method, {'filters': {'field': 'asset', 'op': '==', 'value': pepe_name}})

    def get_pepe_holdings(self, pepe_name: str) -> dict:
        """
        Get a the holdings for a particular pepe.
        :param pepe_name: name of pepe
        :return: cp result
        """
        return self.rpc_connection.query('get_holders', params={'asset': pepe_name})['result']

    def get_pepe_dispensers(self, pepe_name: str) -> dict:
        """
        Get dispensers for a particular pepe
        :param pepe_name: name of pepe
        :return: cp result
        """
        # return self.rpc_connection.query('get_dispensers', params={'asset': pepe_name})
        return self.rpc_connection.query('get_dispensers', params={
            'filters': {'field': 'asset', 'op': '==', 'value': pepe_name}})['result']

    def get_pepe_orders(self, pepe_name: str, custom_filters=None) -> dict:
        """ Get orders for a pepe
        :param pepe_name: Pepe for which to find orders
        :param custom_filters: List of filters in CpApi query format
        :return: dictionary with keys, 'give', 'get' showing the list of give and get orders
        """
        if custom_filters is None:
            custom_filters = []
        if pepe_name in ['XCP', 'PEPECASH']:
            filter_xcp_get = [{'field': 'get_asset', 'op': '==', 'value': 'XCP'},
                              {'field': 'give_asset', 'op': '==', 'value': 'PEPECASH'}]
            filter_xcp_give = [{'field': 'get_asset', 'op': '==', 'value': 'PEPECASH'},
                               {'field': 'give_asset', 'op': '==', 'value': 'XCP'}]
            return {
                'give': self.rpc_connection.query(method='get_orders',
                                                  params={'filters': filter_xcp_give + custom_filters})['result'],
                'get': self.rpc_connection.query(method='get_orders',
                                                 params={'filters': filter_xcp_get + custom_filters})['result']}
        else:
            filter_pepe_get = {'field': 'get_asset', 'op': '==', 'value': pepe_name}
            filter_pepe_give = {'field': 'give_asset', 'op': '==', 'value': pepe_name}
            return {'give': self.rpc_connection.query('get_orders',
                                                      {'filters': [filter_pepe_give] + custom_filters})['result'],
                    'get': self.rpc_connection.query('get_orders',
                                                     {'filters': [filter_pepe_get] + custom_filters})['result']}

    def pepe_pepes_in_block(self, block_index: int = 0, pepes_list=None):
        """
        Get a list of pepe names for which events occurred in a particular block of a particular pepe list
        :param block_index: the block index to look for the pepe names
        :param pepes_list: list of pepes to look for block events
        :return: list of pepe names within provided list for which events occurred in the block
        """
        if pepes_list is None:
            pepes_list = []
        block_index = int(block_index)
        if not block_index:
            block_index = int(self.get_cp_last_block())
        logging.info(f"Listing pepes referenced in block {block_index}")
        assets = set()
        messages = self.rpc_connection.query('get_messages', params={'block_index': block_index})['result']
        for message in messages:
            bindings = message.get('bindings', '')
            if bindings:
                bindings_data = JSONTool.parse_json(bindings)
                asset = bindings_data.get('asset', '')
                if asset and asset in pepes_list:
                    assets.add(asset)
        return assets


class BTCPayServerData:
    def __init__(self,
                 btcpayserver_connection: BTCPayServerConnector = None,
                 loggers=None):
        if btcpayserver_connection:
            self.btcpayserver_connection = btcpayserver_connection
        else:
            self.btcpayserver_connection = BTCPayServerConnector(loggers=loggers)
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries'),
                       'purchases': logging.getLogger('purchases')}
        self.loggers = loggers
        self.db_connection = DBConnector(loggers=loggers)
        self.client = self.btcpayserver_connection.get_client()

    def get_invoice_data(self, invoice_id: str) -> dict:
        return self.client.get_invoice(invoice_id)

    def get_invoice_status(self):
        pass

    def create_invoice(self, purchase_data: dict) -> str:
        return self.client.create_invoice(purchase_data).get('id', False)

    def enqueue_ad(self, invoice_id: str):
        self.loggers['purchases'].info(f"Calling enqueue_ad({invoice_id})\n")
        invoice_data = self.client.get_invoice(invoice_id=invoice_id)
        self.loggers['data'].info(f"invoice_data: \n{invoice_data}\n")
        self.loggers['purchases'].info(f"invoice_data: \n{invoice_data}\n")

        block_amount = Settings.Ads['block_count']
        self.loggers['purchases'].info(f"block_amount: \n{Settings.Ads['block_count']}\n")

        table = 'ad_queue'
        pepe_name = invoice_data['itemDesc'].split()[6]
        query = f"INSERT INTO {table} (asset,paid_invoice,block_amount) " \
                f"VALUES ('{pepe_name}','{invoice_id}',{block_amount})"
        self.loggers['data'].info(f"db_query: {query}")
        self.loggers['purchases'].info(f"db_query: {query}")

        self.db_connection.execute(query)
        self.db_connection.close()


class AdvertisingData:
    def __init__(self, db_connector: DBConnector, loggers=None):
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        self.db_connector = db_connector

    def get_queued_ad(self, invoice_id: str):
        query_ad_slots = f"SELECT * FROM ad_queue WHERE paid_invoice='{invoice_id}'"
        self.loggers['data_queries'].info(query_ad_slots)
        queued_ad = [ad for ad in self.db_connector.query_and_fetch(query_ad_slots)]
        return queued_ad

    def estimate_time_to_listing(self, queue_id):
        query_blocks_ahead = f"SELECT sum(block_amount) FROM ad_queue WHERE id<'{queue_id}'"
        self.loggers['data_queries'].info(query_blocks_ahead)
        blocks_ahead = self.db_connector.query_and_fetch()[0].get('sum(block_amount)', 0) // 3
        query_current_ads = f"SELECT block_remain FROM ad_slots"
        self.loggers['data_queries'].info(query_current_ads)
        current_ads_remain_blocks_max = max(
            [ad['block_remain'] for ad in self.db_connector.query_and_fetch(query_current_ads)])
        estimated_block_wait = current_ads_remain_blocks_max + blocks_ahead
        estimated_days = estimated_block_wait / 144
        if estimated_days < 1:
            time_str = "about " + str(int(estimated_days * 60)) + " hours"
        else:
            time_value = datetime.datetime.now() + datetime.timedelta(days=int(estimated_days))
            time_str = "on " + "{:%B %d, %Y}".format(time_value)
        return time_str

    @staticmethod
    def estimate_block_time(block_count: int, current_time: int):
        return 10 * 60 * block_count + current_time

    def get_ad_slots_entries(self):
        pass

    def get_next_ad_spot(self):
        pass

    def check_payment_status(self):
        pass

    def db_mark_ad_spotmark(self, ad_details):
        pass

    def get_current_running_pepe(self, slot_number: int):
        pass


class PriceTool:
    """ Lookup the current prices, stored in the database"""

    def __init__(self, db_connection: DBConnector, loggers=None):
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        self.db_connection = db_connection

    def get_btc_rate(self) -> float:
        query = 'SELECT usd_rate FROM prices WHERE currency=\'BTC\''
        return self.db_connection.query_and_fetch(query)[0].get('usd_rate', 0)

    def get_xcp_rate(self) -> float:
        query = 'SELECT usd_rate FROM prices WHERE currency=\'XCP\''
        return self.db_connection.query_and_fetch(query)[0].get('usd_rate', 0)

    def get_pepecash_rate(self) -> float:
        query = 'SELECT usd_rate FROM prices WHERE currency=\'PEPECASH\''
        return self.db_connection.query_and_fetch(query)[0].get('usd_rate', 0)

    def convert_satoshis_to_usd(self, units: int, convert_from: str = 'BTC'):
        if convert_from == 'PEPECASH':
            return f"${units / 10 ** 8 * self.get_pepecash_rate():,.2f}"
        elif convert_from == 'XCP':
            return f"${units / 10 ** 8 * self.get_xcp_rate():,.2f}"
        else:
            return f"${units / 10 ** 8 * self.get_btc_rate():,.2f}"

    def convert_xcp_to_btc(self, units: int):
        return units * self.get_xcp_rate()

    def convert_pepecash_to_btc(self, units: int):
        return units * self.get_pepecash_rate()

    @classmethod
    def display_price(cls, satoshi_rate: int, give_quantity: int):
        return satoshi_rate / give_quantity


class XChainData:
    def __init__(self, xchain_connection: XChainConnector, loggers=None):
        """ Initiate XChainData object with the given xchain connection
        :param xchain_connection: RPCConnector object query tool
        """
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        self.xchain_connection = xchain_connection
        self.db_connection = DBConnector()
        self.pepe_query_tool = PepeData(db_connector=self.db_connection)

    def get_btc_current_block(self) -> int:
        """ XChain block level
        :return: current block level on XChain
        """
        return int(self.xchain_connection.query('network')['network_info']['mainnet']['block_height'])

    def get_pepe_details(self, pepe_name: str) -> dict:
        """ Current details of a pepe asset.
        :param pepe_name: name of pepe
        :return: dictionary of the pepe data
        """
        pepe_data_raw = self.xchain_connection.query('asset', [pepe_name])
        pepe_data = {
            'asset': pepe_data_raw['asset'],
            'asset_longname': pepe_data_raw['asset_longname'],
            'description': pepe_data_raw['description'],
            'divisible': pepe_data_raw['divisible'],
            'issuer': pepe_data_raw['issuer'],
            'locked': pepe_data_raw['locked'],
            'owner': pepe_data_raw['owner'],
        }
        if pepe_data_raw['divisible']:
            pepe_data['supply'] = int(float(pepe_data_raw['supply']) * 100_000_000)
        else:
            pepe_data['supply'] = pepe_data_raw['supply']
        if pepe_data_raw['divisible']:
            pepe_data['supply'] = int(float(pepe_data_raw['supply']) * 100_000_000)
        pepe_data['source'] = self.get_pepe_artist(pepe_name)
        return pepe_data

    def get_pepe_artist(self, pepe_name: str) -> str:
        """
        Get originating issuer address of the pepe.
        :param pepe_name: name of pepe
        :return address string
        """
        return self.xchain_connection.query('issuances', [pepe_name])['data'][-1]['issuer']

    def get_pepe_holdings(self, pepe_name: str) -> dict:
        """
        Get list of holdings for a pepe
        :param pepe_name: name of pepe
        :return: Dictionary listing holdings for pepe
        """
        pepe_holdings = self.xchain_connection.query('holders', [pepe_name]).get('data', [])
        pepe_details = self.pepe_query_tool.get_pepe_details(pepe_name)
        for pepe_holding in pepe_holdings:
            pepe_holding.pop('estimated_value')
            pepe_holding.pop('percentage')
            if pepe_details['divisible']:
                pepe_holding['address_quantity'] = int(float(pepe_holding.pop('quantity')) * 100_000_000)
            else:
                pepe_holding['address_quantity'] = int(pepe_holding.pop('quantity'))
        return pepe_holdings

    def get_pepe_dispensers(self, pepe_name: str):
        pepe_dispensers = self.xchain_connection.query('dispensers', [pepe_name]).get('data', [])
        pepe_details = self.pepe_query_tool.get_pepe_details(pepe_name)
        for pepe_dispenser in pepe_dispensers:
            pepe_dispenser.pop('asset_longname')
            pepe_dispenser.pop('timestamp')
            pepe_dispenser['satoshirate'] = int(float(pepe_dispenser['satoshirate']) * 100_000_000)
            if pepe_details['divisible']:
                pepe_dispenser['escrow_quantity'] = int(float(pepe_dispenser['escrow_quantity']) * 100_000_000)
                pepe_dispenser['give_quantity'] = int(float(pepe_dispenser['give_quantity']) * 100_000_000)
                pepe_dispenser['give_remaining'] = int(float(pepe_dispenser['give_remaining']) * 100_000_000)
            else:
                pepe_dispenser['escrow_quantity'] = int(pepe_dispenser['escrow_quantity'])
                pepe_dispenser['give_quantity'] = int(pepe_dispenser['give_quantity'])
                pepe_dispenser['give_remaining'] = int(pepe_dispenser['give_remaining'])
        return pepe_dispensers

    def get_pepe_orders(self, pepe_name: str) -> dict:
        """ Get orders for a pepe
        :param pepe_name: Pepe for which to find orders
        :return: dictionary with keys, 'give', 'get' showing the list of give and get orders
        """
        pepe_orders_raw = self.xchain_connection.query('orders', [pepe_name]).get('data', [])
        pepe_orders_all = []
        for pepe_order in pepe_orders_raw:
            get_asset_details = self.pepe_query_tool.get_pepe_details(pepe_order['get_asset'])
            give_asset_details = self.pepe_query_tool.get_pepe_details(pepe_order['give_asset'])
            if get_asset_details and give_asset_details:
                pepe_orders_all.append(pepe_order)
        for pepe_order in pepe_orders_all:
            get_asset_details = self.pepe_query_tool.get_pepe_details(pepe_order['get_asset'])
            give_asset_details = self.pepe_query_tool.get_pepe_details(pepe_order['give_asset'])
            pepe_order.pop('get_asset_longname', '')
            pepe_order.pop('give_asset_longname', '')
            pepe_order.pop('timestamp', '')
            pepe_order['fee_provided'] = int(float(pepe_order['fee_provided']) * 100_000_000)
            pepe_order['fee_provided_remaining'] = int(float(pepe_order['fee_provided_remaining']) * 100_000_000)
            pepe_order['fee_required'] = int(float(pepe_order['fee_required']) * 100_000_000)
            pepe_order['fee_required_remaining'] = int(float(pepe_order['fee_required_remaining']) * 100_000_000)
            if get_asset_details['divisible']:
                if '-' in pepe_order['get_remaining'][1:]:  # Fix for xchain sending 0.0-500000 instead of -0.0050000
                    pepe_order['get_remaining'] = '-' + str(pepe_order['get_remaining']).replace('-', '0')
                pepe_order['get_quantity'] = float(pepe_order['get_quantity']) * 100_000_000
                pepe_order['get_remaining'] = float(pepe_order['get_remaining']) * 100_000_000
            if give_asset_details['divisible']:
                if '-' in pepe_order['give_remaining'][1:]:  # Fix for xchain sending 0.0-500000 instead of -0.0050000
                    pepe_order['give_remaining'] = '-' + str(pepe_order['give_remaining']).replace('-', '0')
                pepe_order['give_quantity'] = float(pepe_order['give_quantity']) * 100_000_000
                pepe_order['give_remaining'] = float(pepe_order['give_remaining']) * 100_000_000

            pepe_order['get_quantity'] = int(pepe_order['get_quantity'])
            pepe_order['get_remaining'] = int(pepe_order['get_remaining'])
            pepe_order['give_quantity'] = int(pepe_order['give_quantity'])
            pepe_order['give_remaining'] = int(pepe_order['give_remaining'])

        pepe_orders = {}
        if pepe_name in ['XCP', 'PEPECASH']:
            pepe_orders['get'] = [pepe_order for pepe_order in pepe_orders_all
                                  if pepe_order['get_asset'] == 'XCP' and pepe_order['give_asset'] == 'PEPECASH']
            pepe_orders['give'] = [pepe_order for pepe_order in pepe_orders_all
                                   if pepe_order['get_asset'] == 'PEPECASH' and pepe_order['give_asset'] == 'XCP']
        else:
            pepe_orders['get'] = [pepe_order for pepe_order in pepe_orders_all
                                  if pepe_order['get_asset'] == pepe_name]
            pepe_orders['give'] = [pepe_order for pepe_order in pepe_orders_all
                                   if pepe_order['give_asset'] == pepe_name]
        return pepe_orders

    def pepe_pepes_in_block(self, block_index: int = 0, pepes_list=None) -> set:
        """
        Get list of pepes for which events occurred in a block, from amount a list of pepes
        :param block_index: block number to search
        :param pepes_list: list of pepes to look for
        :return: set of pepes for which events occurred in the block
        """
        if pepes_list is None:
            pepes_list = []
        block_index = str(block_index)
        if not block_index:
            block_index = str(self.get_btc_current_block())
        logging.info(f"Listing pepes referenced in block {block_index}")
        message_types = ['burns', 'credits', 'debits', 'destructions', 'dispensers', 'dispenses', 'dividends', 'orders',
                         'order_matches', 'sends']
        pepes_in_block = set()
        for message_type in message_types:
            result = self.xchain_connection.query(message_type, [block_index])
            if result and result['data']:
                for item in result['data']:
                    asset = item.get('asset', '')
                    if asset in pepes_list:
                        pepes_in_block.add(asset)
        return pepes_in_block


class RarePepeDirectory:
    @staticmethod
    def parse_urls_file():
        """ Load urls for each Pepe at the RarePepeDirectory, stored in the local file. """
        return JSONTool.read_json_file(Settings.Sources['pepe_data']['rarepepedirectory_urls'])

    @staticmethod
    def parse_series_data_file() -> dict[str, int]:
        """ Load series data for each Pepe at the RarePepeDirectory, stored in the local file. Returns a
        dictionary with Pepe names as keys and their series numbers as values. """
        pepe_series_map = {}
        series_data = JSONTool.read_json_file('../rpw/static/data/RarePepeDirectory_Series_Data.json')
        for key in series_data:
            for pepe_name in series_data[key]:
                pepe_series_map[pepe_name] = int(key)
        return pepe_series_map

    @staticmethod
    def parse_rarepepedirectory(pepe_names: list[str]):
        """ Method will attempt to parse the RarePepeDirectory urls for each specified Pepe name. The
        result can be used to create the list file as configured in the Settings. Due to inconsistencies in
        the RarePepeDirectory web pages, some the *misses* value.  Those may need be added manually.
         param pepename: list of pepe names to lookup """
        rarepepedirectory_list_file = Settings.Sources['pepe_data']['rarepepedirectory_urls']
        found = JSONTool.read_json_file(rarepepedirectory_list_file)
        search_base = "http://rarepepedirectory.com/?s="
        skipped = []
        i = 0
        while i < len(pepe_names):
            pepe_name = pepe_names[i]
            if pepe_name not in found.keys():
                print(f"Searching for {pepe_name} url")
                url = f"{search_base}{pepe_name}"
                page_content = requests.get(url).text
                soup = BeautifulSoup(page_content, 'html.parser')
                try:
                    pepe_url = soup.findAll('a', {'title': pepe_name})[0]['href']
                    print(f"Found at {pepe_url}")
                    # f.writelines(f"{pepe_name} : {pepe_url}\n")
                    JSONTool.store_json_file(rarepepedirectory_list_file, found, sort_keys=True, indent=2)
                    found[pepe_name] = pepe_url
                except IndexError:
                    print(f"Could not find link for {pepe_name}. Skipping")
                    skipped.append(pepe_name)
            else:
                print(f"Already in list: {pepe_name}, value {found[pepe_name]}")
                found[pepe_name] = found[pepe_name]
            i += 1
        return {'urls': found, 'misses': skipped}

    @staticmethod
    def parse_rarepepedirectory_series_data():
        """ Method will attempt to parse the RarePepeDirectory to determine the series for each Pepe. The result can
        be used to create the series data file as configured in the Settings. """

        url = 'http://rarepepedirectory.com'
        response = requests.get(url)
        content = response.content
        soup = BeautifulSoup(content, 'html5lib')

        li_elements = soup.find_all('li')
        url_dict = {}

        for li in li_elements:
            a_tag = li.find('a')
            if a_tag:
                href = a_tag['href']
                print(f"Series url: {href}")
                text = a_tag.text
                number = text.split(' ')[-1]
                try:
                    number = int(number)
                    url_dict[number] = href
                except ValueError:
                    continue

        h2_dict = {}
        for number, url in url_dict.items():
            url_next = url
            print(f"Looking up url: {url_next}")
            while True:
                done_series = False
                response = requests.get(url_next)
                content = response.content
                soup = BeautifulSoup(content, 'html5lib')

                main_div = soup.find('div', {'id': 'main'})
                h2_elements = main_div.find_all('h2', {'class': 'entry-title'})

                h2_list = [h2.text for h2 in h2_elements]
                print(f"Pepe names in page: {h2_list}")
                if number in h2_dict:
                    h2_dict[number] += h2_list
                else:
                    h2_dict.setdefault(number, h2_list)
                print(f"Pepes in series: {h2_dict[number]}")

                nav_prev = soup.find("div", class_="nav-previous")
                if nav_prev:
                    a_tag = nav_prev.find("a", href=True)
                    if a_tag:
                        url_next = a_tag['href']
                        print(f"Next page in series: {url_next}")
                    else:
                        done_series = True
                else:
                    done_series = True
                if done_series:
                    print(f"No more pages in series")
                    break

        return h2_dict
