# --*-- coding:utf-8 --*--
import json
import logging
from pathlib import Path

import qrcode
import requests
from math import ceil


class JSONTool:
    """ Class for storing queries for caching.  For reducing internet queries in cases where data is static. """
    JSON_PRETTY_KWARGS = {
        'sort_keys': True, 'indent': 2
    }

    @classmethod
    def parse_json(cls, raw_data: str, *args, **kwargs) -> dict | bool:
        """ Parse a string representing json data. Parse into a dictionary object
        :param raw_data: Raw json string
        :param args: additional positional arguments to pass json.loads
        :param kwargs: additional keyword arguments to pass json.loads
        :return: dictionary object corresponding to the json raw string
        """
        data = ""
        try:
            data = json.loads(raw_data, *args, **kwargs)
        except json.JSONDecodeError:
            logging.debug(f"parse_json - raw_data: {raw_data}, data: {data}")
            return False
        return data

    @classmethod
    def parse_dict(cls, data: dict, *args, **kwargs):
        """ Convert a dictionary object into a json representation
        :param data: the dictionary object to convert
        :param args: additional positional arguments to pass json.loads
        :param kwargs: additional keyword arguments to pass json.loads
        :return: json string object corresponding to the provided dictionary
        """
        data_str = json.dumps(data, *args, **kwargs)
        return data_str

    @classmethod
    def read_json_file(cls, in_file: str or Path) -> dict | bool:
        """ Read json data stored in a file
        :param in_file: Path to the stored file
        :return: dictionary representing the json object or None if reading failed
        """
        try:
            with open(in_file) as f:
                raw_json = f.read()
            data = cls.parse_json(raw_json)
        except json.JSONDecodeError:
            return False
        return data

    @classmethod
    def store_json_file(cls, target_path: str, data: dict, *args, **kwargs):
        """ Write a dictionary object to a file as json
        :param target_path The path to the file where the json will be stored
        :param data The dictionary object that will be stored in the file
        :return: None
        """
        cp_str = cls.parse_dict(data, *args, **kwargs)
        with open(target_path, 'w') as cp_file:
            cp_file.write(cp_str)

    @classmethod
    def query_endpoint(cls, query_url) -> dict | bool:
        """ Request data from an api that returns json formulated data
        :param query_url: The full url of the query
        :return: dictionary object representing the response from the api or None if an decoding error occurred
        """
        logging.info(f"Querying endpoint: {query_url}")
        response = requests.get(query_url)
        data = ""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logging.debug(f"query endpoint -  query_url: {query_url}, data: {data}")
            return False
        return data


class QRCodeTool:
    """ Class for working with QR Code images. """

    @staticmethod
    def make(img_path: str = "", data: str = ""):
        """ Create an image file of a qr code representing the provided string.
        :param img_path: File to write the QR code image
        :param data: Data to encode into the QR code image
        :return: None
        """
        if not img_path or data:
            return False
        img = qrcode.make(data)
        img.save(img_path)


class Paginator:
    @staticmethod
    def paginate(data_set: list, items_per_page: int):
        c = items_per_page
        p = ceil(len(data_set) / c)  # number of pages
        return [data_set[i * c:i * c + c] for i in range(p)]
