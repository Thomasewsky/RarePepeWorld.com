# --*-- coding:utf-8 --*--
import logging
from datetime import date, timedelta, datetime
from decimal import Decimal
from typing import List, Tuple, Set

import mysql.connector
import pickle
import requests

from btcpay import BTCPayClient
from mysql.connector.connection import MySQLConverter
from requests.auth import HTTPBasicAuth

import Settings
from rpw.Utils import JSONTool


class XChainConnector:
    """ Connector to the xchain website api
    """

    def __init__(self, loggers=None):
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers

    def query(self, method: str = "", params=None) -> dict:
        """ Query the XChain API
        :param method: one of the available api methods on XChain
        :param params: a list of strings representing the comma seperated list of parameters to the api method
        :return: dictionary object representing the response from XChain
        """
        if params is None:
            params = []
        if method not in Settings.Sources['xchain']['methods_available']:
            self.loggers['data_queries'].debug(
                f"XChain: invalid method provided. Must be one of {Settings.Sources['xchain']['methods_available']}")
            return {}
        query_url = f"{Settings.Sources['xchain']['api_base_url']}/{method}"
        if params:
            query_url += f"/{','.join(params)}"
        self.loggers['data_queries'].info(query_url)
        return JSONTool.query_endpoint(query_url)


class RPCConnector:
    """ Connector for communicating with a Counterparty RPC service """

    def __init__(self, rpc_settings: dict = Settings.Sources['rpc'], loggers=None):
        """ Initiate a connector object
        :param rpc_settings: dictionary representing the RPC connection settings
        """
        self.rpc_url = rpc_settings['url']
        self.rpc_user = rpc_settings['user']
        self.rpc_password = rpc_settings['password']
        self.rpc_headers = rpc_settings['headers']
        self.rpc_version = rpc_settings['version']
        self.rpc_auth = HTTPBasicAuth(self.rpc_user, self.rpc_password)
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers

    def query(self, method: str = "", params: dict = None) -> dict:
        """
        :param method: one of the available methods to query
        :param params: dictionary representing query parameters
        :return: dictionary representing the response from the RPC
        """
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": self.rpc_version,
            "id": 0
        }

        payload_json = JSONTool.parse_dict(payload)
        self.loggers['data_queries'].info(f"RPC: Query: \'{method}\', Paramaters: {params}.")
        response = requests.post(self.rpc_url, data=payload_json, headers=self.rpc_headers, auth=self.rpc_auth)
        return JSONTool.parse_json(response.text)


class DBConnector:
    """ Connector to communicate with a mysql database """

    class ConnectError(Exception):
        pass

    def __init__(self, mysql_settings: dict = Settings.Sources['mysql'], loggers=None):
        """ Initiate a connection to a MySQL server and database
        :param mysql_settings: Dictionary representing the settings required to connect.
        Keys: host, user, password, database_name
        """
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries'),
                       'errors': logging.getLogger('errors')}
        self.loggers = loggers
        db_host = mysql_settings['host']
        db_user = mysql_settings['user']
        db_password = mysql_settings['password']
        db_database = mysql_settings['database_name']

        try:
            self.loggers['data_queries'].info(
                f"\nMysql - connecting\nDatabase: {db_database}\nUser: {db_user}\nHost: {db_host}\n")
            self.db_connection = mysql.connector.connect(
                host=db_host, user=db_user, password=db_password, database=db_database)
            self.cursor = self.db_connection.cursor(buffered=True, dictionary=True)
            self.converter = MySQLConverter()
            self.loggers['data_queries'].info("Success.")
        except mysql.connector.Error as e:
            self.loggers['errors'].debug(e.msg)
            self.loggers['errors'].debug(f"Mysql: connection failed\n")

    def reconnect(self):
        """ Reconnected to the database to prevent the event of timeout of the rpc. """
        self.loggers['data_queries'].info("Attempting to reconnect to the database.")
        try:
            self.reconnect()
            return True
        except mysql.connector.Error as e:
            self.loggers['errors'].debug(f"Mysql execute error occurred\n\t"
                                         f"Error code: {e.errno}\n\t"
                                         f"SQL State: {e.sqlstate}\n\t"
                                         f"Message: {e.msg}\n")
        return False

    def _execute(self, command: str):
        """ Execute a command string in the database. """
        try:
            self.cursor.execute(command)
        except mysql.connector.Error as e:
            self.loggers['errors'].debug(f"Mysql execute error occurred\n\t"
                                         f"Error code: {e.errno}\n\t"
                                         f"SQL State: {e.sqlstate}\n\t"
                                         f"Message: {e.msg}\n")
            return False
        return True

    def execute(self, command_tokens: list or str = ""):
        """ Prep a set of command parts to be sent to the database
        :param command_tokens: list of values in the query or string representing the entire query
        :return: List of returned values from the query.
        """
        if not self.db_connection.is_connected():
            self.reconnect()
        if type(command_tokens) == list:
            command = ' '.join(command_tokens)
        else:
            command = command_tokens
        self.loggers['data_queries'].info(f"Executing query: {command}")
        self._execute(command)

    def get_result(self):
        """ Fetch the results from a command executed to the database. """
        return self.cursor.fetchall()

    def query_and_fetch(self, query) -> list[tuple]:
        """ Execute query and fetch results
        :param query: the string representing the query
        :return: a list of tuple representing the records returned by the database
        """
        self.execute(query)
        return self.get_result()

    def execute_and_commit(self, query):
        """ Execute query and commit the change
        :param query: the string representing the query
        """
        self.execute(query)
        self.commit()

    def commit(self):
        """ Commit any current changes to the database. """
        self.db_connection.commit()

    def close(self):
        """ Close the database connection.
        :return: None
        """
        self.loggers['data_queries'].info("Shutting down db connection.")
        self.db_connection.close()

    def escape(self, value: str):
        """ Ensure valid properly escaped strings are sent to the database.
        :param value: The string to be escaped
        :return: the properly escaped string
        """
        return self.converter.escape(value)


class BTCPayServerConnector:
    def __init__(self, client_store_file: str = '', loggers=None):
        if loggers is None:
            loggers = {'data_queries': logging.getLogger('data_queries')}
        self.loggers = loggers
        if not client_store_file:
            self.client_store_file = Settings.Sources['btcpayserver']['client_store_file']
        self.client = self.load_client_object()

    def load_client_object(self):
        with open(self.client_store_file, 'rb') as in_file:
            client = pickle.load(in_file)
        return client

    def get_client(self):
        return self.client

    @staticmethod
    def create_pairing_object(pairing_code: str, client_store_file: str):
        out_file = open(client_store_file, 'wb')
        client = BTCPayClient.create_client(host='https://pay.rarepepeworld.com', code=pairing_code)
        pickle.dump(client, out_file)
        out_file.close()
