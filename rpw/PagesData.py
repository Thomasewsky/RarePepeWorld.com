# --*-- coding:utf-8 --*--
from random import randint

from bs4 import BeautifulSoup as bs
from flask import url_for, Markup
from pprint import pformat
import re

import hashlib
import hmac
import logging

import Settings
from rpw.DataConnectors import DBConnector, BTCPayServerConnector
from rpw.QueryTools import PepeData, PriceTool, BTCPayServerData, AdvertisingData
from rpw.Utils import Paginator

pepe_images_url_relative = Settings.Sources['pepe_data']['images_path'].replace(
    Settings.Main['base_path'] + '/rpw/static/', '')

class Formats:
    """ Class for handling the various Counterparty formats and formatting data for the site presentation. """

    def __init__(self):
        pass

    @staticmethod
    def pepe_units_normalize(raw_units: int, divisible: bool = False) -> int or float:
        """
        Process unit amounts according to the type of asset, divisible or non-divisible.
        :param raw_units: raw Counterparty units for the asset
        :param divisible: divisibility characteristic of the asset
        :return: raw Counterparty units as 8 decimal place float, if divisible, raw integer otherwise
        """
        if divisible:
            return raw_units / 10 ** 8
        else:
            return raw_units

    @staticmethod
    def pepe_normalized_supply_str(s: float, divisible: bool = False) -> str:
        """
        Format supply value of pepe asset based on divisibility status
        :param s: supply value
        :param divisible: divisibility of the asset
        :return: string formatted based on divisibility characteristic
        """
        if divisible:
            return f"{s:,.1f}"
        else:
            return f"{s:,}"

    @staticmethod
    def pepe_quantity_str(units: int, divisible: bool = False) -> str:
        """
        Convert quantity to formatted string based on divisibility characteristic of asset
        :param units: value to convert
        :param divisible: divisibility characteristic of asset
        :return: formatted string based on divisibility of asset
        """
        units = Formats.pepe_units_normalize(units, divisible)
        if divisible:
            if units == units // 1:
                return f"{units:,.1f}"
            return f"{units:,.1f}"
        else:
            return f"{units:,}"

    @staticmethod
    def satoshis_to_str(satoshis: float) -> str:
        """
        Format a value in satoshis to a formatted string based on the quantity.  If satoshi amount is above a certain
        value, format as btc, otherwise, as integer
        :param satoshis: value of satoshis
        :return: string formatted
        """
        btc_unit_str = '&#x20BF;'
        sats_unit_str = '&#x26A1;'
        if satoshis >= 1_000_000:
            value_str = f"{satoshis / 10 ** 8:,.8f}"
            price_str = f"{btc_unit_str} {value_str[:6]}"

        else:
            price_str = f"{sats_unit_str} {int(satoshis):,}"
        return Markup(price_str)

    @staticmethod
    def format_base_asset(value: int) -> str:
        """
        Format the string representation of base assets (XCP or PEPECASH), based on whether there is a fractional
        portion to represent.
        :param value: value to format
        :return: string format of value
        """
        if value == value // 1:
            return f"{value:,.1f}"
        else:
            return f"{value:,.8f}".rstrip('0')

    @staticmethod
    def order_book_price_int(base_asset_quantity, pepe_asset_quantity, pepe_asset_divisible=False) -> float:
        """
        Determine the price of an asset to be shown in the order book.
        :param base_asset_quantity: quantity of base asset
        :param pepe_asset_quantity: quantity of pepe asset
        :param pepe_asset_divisible: divisibility characteristic of pepe asset
        :return: calculated price of pepe asset in the base asset
        """
        base_asset_quantity /= 10 ** 8
        if pepe_asset_divisible:
            pepe_asset_quantity /= 10 ** 8
        return base_asset_quantity / pepe_asset_quantity

    @staticmethod
    def holders_table_amount_str(units: int, divisible: bool = False, is_normalized: bool = False) -> str:
        """
        Format units for display in the list of holders of an asset.
        :param units: Number of units
        :param divisible: divisibility characteristic of the asset
        :param is_normalized: are units already normalized
        :return: Formatted string to display in the holders table
        """
        if divisible:
            if is_normalized:
                return f"{units:,.1f}"
            else:
                return f"{units / 10 ** 8:,.1f}"
        else:
            return f"{units:,}"

    @staticmethod
    def holders_table_percentage_str(ratio: float) -> str:
        """
        Format a ratio into a percentage value for display in the holders table
        :param ratio: ratio to convert into percentage
        :return: string value of the ratio in percentage
        """
        return f"{ratio * 100:.1f}"

    @staticmethod
    def get_pepe_image_url(pepe_query_tool: PepeData, pepe_name: str) -> str:
        """
        Get the image url for a particular pepe.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param pepe_name: name of pepe to request image name for
        :return: url string to the image
        """
        return url_for(
            'static',
            filename=pepe_images_url_relative + pepe_query_tool.get_pepe_image_filename(
                pepe_name=pepe_name))

    @staticmethod
    def string_to_int(in_str: str) -> str or bool:
        """
        Safely convert string to integer.
        :param in_str: value to convert
        :return: String value of the integer or False if the value is unconvertable
        """
        try:
            return int(in_str)
        except ValueError:
            return False

    @staticmethod
    def is_address_string(bitcoin_address: str):
        """ Basic check if string matches Bitcoin address pattern.  Used for the search mechanism, not a test
        of a validity of a Bitcoin address.
        :return: True if matches, False if not
        """
        pattern = '([13]|bc1)[A-HJ-NP-Za-km-z1-9]{27,34}'
        return re.match(pattern, bitcoin_address)


class CommonPageData:
    """
    Class for constructing data common to all pages
    """

    def __init__(self):
        pass

    @staticmethod
    def create(loggers=None) -> dict:
        """
        Construct data common to all pages
        :param loggers: Logging object
        :return: common data for pages
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        common_data = {
            **Settings.Site
        }
        loggers['data'].info(f"Common page data: {pformat(common_data)}")
        return common_data


class IndexPage:
    """
    Class for constructing the data for representation on the index page.
    """

    def __init__(self):
        pass

    @staticmethod
    def create(loggers=None, show_latest_dispensers: bool = True) -> dict:
        """
        Construct the data to be displayed on the index page
        :param loggers: Logging object
        :param show_latest_dispensers: whether to display the latest dispensers on the page
        :return: data to be displayed on the index page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        featured_pepes_view = FeaturedPepes.create(
            pepe_query_tool=pepe_query_tool,
            loggers=loggers
        )
        if show_latest_dispensers:
            data_view = LatestDispensers.create(
                pepe_query_tool=pepe_query_tool,
                loggers=loggers
            )
        else:
            data_view = RandomPepes.create(
                pepe_query_tool=pepe_query_tool,
                loggers=loggers
            )
        index_data = {
            **general_page_data,
            'display_data': data_view,
            'show_latest_dispensers': show_latest_dispensers,
            'featured_pepes_view_data': featured_pepes_view
        }
        db_connection.close()

        loggers['data'].info(f"Index Page Data: {pformat(index_data)}")
        return index_data


class SubPage:
    """
    Class for constructing the data to be stored in a subpage from the main url
    """

    def __init__(self):
        pass

    @staticmethod
    def create(
            subpage_str: str,
            args: dict = None,
            page_number: int = 1,
            loggers=None
    ) -> [str, dict]:
        """
        Construct the data for a subpage from the main url
        :param subpage_str: string of the subpage in the url
        :param args: parameters provided to the page
        :param page_number: page number to display if pagination is required
        :param loggers: Logging object
        :return: data to be represented on the subpage
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data'), 'root': logging.getLogger('root')}

        if Formats.is_address_string(subpage_str):
            page_number = page_number - 1
            loggers['root'].info(f"\t{subpage_str} identified as address format. Launching address page view.")
            address_page_data = AddressPage.create(subpage_str, page_number=page_number, loggers=loggers)

            loggers['data'].info(f"Address Page data: {pformat(address_page_data)}")
            return 'address', address_page_data

        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        common_page_data = CommonPageData.create()
        subpage_str = subpage_str.upper()
        if subpage_str in pepe_query_tool.pepe_names:
            loggers['root'].info(f"\t{subpage_str} identified as pepe format. Launching Pepe page view.")
            dispenser_number = Formats.string_to_int(args.get('d', 0)) or 0
            try:
                dispenser_number = int(dispenser_number)
            except ValueError:
                dispenser_number = 0
            pepe_page_data = PepePage.create(subpage_str, dispenser_number=dispenser_number, loggers=loggers)
            loggers['data'].info(f"Pepe Page Data: {pformat(pepe_page_data)}")
            return 'pepe', pepe_page_data
        else:
            loggers['root'].info(f"Subpage did not match address or pepe name. Returning error page.")
            return '404', {**common_page_data}


class AddressPage:
    """
    Class for constructing data for subpage that displays an address
    """

    def __init__(self):
        pass

    @staticmethod
    def create(
            address: str,
            page_number: int = 0,
            loggers=None
    ) -> dict:
        """
        Construct the date for presenting data on the subpage that displays and address
        :param address: the address to display
        :param page_number: page number if pagination is active
        :param loggers: Logging object
        :return: data to display an address page
        """

        if loggers is None:
            loggers = {'data': logging.getLogger('data'), 'root': logging.getLogger('root')}
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        collections_list_data = AddressCollection.create(
            pepe_query_tool=pepe_query_tool,
            pepes_per_page=54,
            page_number=page_number,
            address=address
        )
        address_page_data = {
            **general_page_data,
            'address': address,
            'collections_list_data': collections_list_data
        }
        db_connection.close()

        loggers['data'].info(f"address_page_data: {pformat(address_page_data)}")
        return address_page_data


class PepePage:
    """ Class for constructing the data for a page that displays a particular Pepe. """

    def __init__(self):
        pass

    @staticmethod
    def create(pepe_name, dispenser_number: int = 0, loggers=None, fiat_enabled=False) -> dict:
        """
        Construct data to display a particular Pepe.
        :param pepe_name: name of Pepe to display
        :param dispenser_number: number of dispenser to set in the feature section
        :param loggers: Logging object
        :param fiat_enabled: whether or not to show fiat price in feature section
        :return: data to display on the a pepe page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        price_tool = PriceTool(db_connection, loggers=loggers)

        pepe_details = pepe_query_tool.get_pepe_details(pepe_name)

        pepe_dispensers_data = PepeDispensers.create(pepe_name,
                                                     pepe_query_tool=pepe_query_tool,
                                                     price_tool=price_tool,
                                                     pepe_details=pepe_details,
                                                     fiat_enabled=fiat_enabled,
                                                     loggers=loggers)
        if pepe_name != 'XCP':
            pepe_xcp_orders_data = PepeOrders.create(pepe_name,
                                                     base_asset='XCP',
                                                     pepe_query_tool=pepe_query_tool,
                                                     price_tool=price_tool,
                                                     pepe_details=pepe_details,
                                                     fiat_enabled=fiat_enabled,
                                                     loggers=loggers)
        else:
            pepe_xcp_orders_data = []
        if pepe_name != 'PEPECASH':
            pepe_pepecash_orders_data = PepeOrders.create(pepe_name,
                                                          base_asset='PEPECASH',
                                                          pepe_query_tool=pepe_query_tool,
                                                          price_tool=price_tool,
                                                          pepe_details=pepe_details,
                                                          fiat_enabled=fiat_enabled,
                                                          loggers=loggers)
        else:
            pepe_pepecash_orders_data = []
        pepe_holders_data = PepeHolders.create(pepe_name,
                                               pepe_query_tool=pepe_query_tool,
                                               pepe_details=pepe_details,
                                               show_holder_count=10,
                                               loggers=loggers)

        if len(pepe_dispensers_data['rows']) == 0:
            shown_dispenser_price = ''
            shown_dispenser_address = ''
            shown_dispenser_address_truncated = ''
            shown_dispenser_qrcode = ''
            shown_dispenser_price_btc = ''
            shown_dispenser_usd_value = ''
            shown_dispenser_stock = ''
            shown_dispenser_receive = ''
            shown_dispenser_xchain_url = ''
        else:
            shown_dispenser_price = pepe_dispensers_data['rows'][dispenser_number]['pay']
            shown_dispenser_price_btc = pepe_dispensers_data['rows'][dispenser_number]['pay_btc']
            shown_dispenser_address = pepe_dispensers_data['rows'][dispenser_number]['address']
            shown_dispenser_address_truncated = f"{shown_dispenser_address[:5] + '...' + shown_dispenser_address[-5:]}"
            shown_dispenser_qrcode = url_for('static', filename=f"qr/{shown_dispenser_address}.png")
            shown_dispenser_usd_value = pepe_dispensers_data['rows'][dispenser_number]['usd_value']
            shown_dispenser_stock = pepe_dispensers_data['rows'][dispenser_number]['stock']
            shown_dispenser_receive = pepe_dispensers_data['rows'][dispenser_number]['receive']
            shown_dispenser_xchain_url = pepe_dispensers_data['rows'][dispenser_number]['xchain_tx_url']

        pepe_page_data = {
            **general_page_data,
            'pepe_details': pepe_details,
            'pepe_dispensers': pepe_dispensers_data,
            'pepe_xcp_orders': pepe_xcp_orders_data,
            'pepe_pepecash_orders': pepe_pepecash_orders_data,
            'pepe_holders': pepe_holders_data,
            'pepe_name': pepe_name,
            'opengraph_image_url': pepe_dispensers_data['pepe_image_url'],
            'supply': Formats.pepe_normalized_supply_str(pepe_details['supply'], pepe_details['divisible']),
            'series': pepe_details['series'],
            'pepe_rarepepedirectory_url': pepe_details['rarepepedirectory_url'],
            'pepe_xchain_url': f"https://xchain.io/asset/{pepe_name}",
            'pepe_artist': pepe_details['source'],
            'pepe_image_url': pepe_dispensers_data['pepe_image_url'],
            'latest_price': "Under development",
            'pepe_images': pepe_query_tool.pepe_images,
            'dispenser_number': dispenser_number,
            'dispenser_count': len(pepe_dispensers_data['rows']),
            'shown_dispenser_price': shown_dispenser_price,
            'shown_dispenser_price_btc': shown_dispenser_price_btc,
            'shown_dispenser_address': shown_dispenser_address,
            'shown_dispenser_address_truncated': shown_dispenser_address_truncated,
            'shown_dispenser_qrcode': shown_dispenser_qrcode,
            'shown_dispenser_usd_value': shown_dispenser_usd_value,
            'shown_dispenser_receive': shown_dispenser_receive,
            'shown_dispenser_stock': shown_dispenser_stock,
            'shown_dispenser_xchain_url': shown_dispenser_xchain_url,
            'show_xcp_orders': pepe_name != 'XCP',
            'show_pepecash_orders': pepe_name != 'PEPECASH',
            'fiat_enabled': fiat_enabled
        }
        db_connection.close()

        loggers['data'].info(f"Pepe page data: {pformat(pepe_page_data)}")
        return pepe_page_data


class ArtistPage:
    """ Class for constructing the data to display on the page that shows a Pepe artist. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            address: str,
            page_number: int = 1,
            loggers=None
    ) -> dict:
        """
        Construct the data to display on a sub page that shows a Pepe artist.
        :param address: address of the artist
        :param page_number: page number if pagination is active
        :param loggers: Logging object
        :return: data to display on an artist page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        page_number = page_number - 1
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        collections_list_data = ArtistCollection.create(
            pepe_query_tool=pepe_query_tool,
            pepes_per_page=54,
            page_number=page_number,
            address=address
        )

        db_connection.close()

        artist_page_data = {
            **general_page_data,
            'address': address,
            'collections_list_data': collections_list_data
        }

        loggers['data'].info(f"{pformat(artist_page_data)}")
        return artist_page_data


class SearchPage:
    """ Class for constructing the data for pepe assets or addresses listed in search results. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            search_text: str,
            page_number: int = 1,
            loggers=None
    ) -> tuple[bool, dict | bool]:
        """
        Construct the data to be displayed in the search results page.
        :param search_text: text being search for
        :param page_number: page number, if pagination is being used
        :param loggers: Logging object
        :return: Tuple. first element: True if text is a direct match, False otherwise.
        second element: search page data to be displayed.
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data'), 'root': logging.getLogger('root')}
        search_results_per_page = 54
        page_number = page_number - 1

        if Formats.is_address_string(search_text):
            loggers['root'].info(f"Search text identified as an address string.")
            return True, False  # direct to address subpage

        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        search_text = search_text.upper()

        pepe_matches = [pepe_name for pepe_name in pepe_query_tool.pepe_names
                        if search_text in pepe_name]
        are_matches = False if len(pepe_matches) == 0 else True
        if len(pepe_matches) == 1 and pepe_matches[0] == search_text:
            loggers['root'].info(f"Search text identified as a pepe name.")
            return True, False  # direct to pepe subpage
        else:
            search_results_data = SearchResults.create(
                pepe_query_tool=pepe_query_tool,
                results_per_page=search_results_per_page,
                page_number=page_number,
                search_text=search_text,
            )
        search_page_data = {
            **general_page_data,
            'are_matches': are_matches,
            'search_results_data': search_results_data,
            'search_text': search_text,
        }
        loggers['data'].info(f"Search results data: {pformat(search_page_data)}")
        return False, search_page_data  # load search page with search results


class AdvertisePage:
    """ Class for constructing the data for the advertisement promotion page. """

    def __init__(self):
        pass

    @staticmethod
    def create(form_text='CHOOSEYOURPEPE',
               loggers=None) -> dict:
        """
        Construct the data to be displayed on the advertising promotion page.
        :param form_text: pepe name to show
        :param loggers: Logging object
        :return: data to display on the advertising promotion page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        general_page_data = CommonPageData.create()
        advertise_page_data = {
            'action_url': '/invoice/',
            'ad_price': 50,
            'ad_pepe_name': 'PUMP YOUR PEPE!',
            'ad_image_url': url_for('static',
                                    filename=f"images/PUMPURPEPE.png"),
            'pay_button_image': url_for('static', filename='images/pay.png'),
            'pepe_names_list_str': str(pepe_query_tool.get_pepe_names()),
            'typed_pepe': form_text,
            'successful_payment_url': f"{Settings.Site['domain']}/successful_payment/",
            **general_page_data
        }
        loggers['data'].info(f"Advertise page data: {pformat(advertise_page_data)}")
        return advertise_page_data


class PaidPage:
    """ Class for constructing data for the payment successful page. """

    def __init__(self):
        pass

    @staticmethod
    def create(loggers=None) -> dict:
        """
        Construct the data to be displayed on the payment successful page.
        :param loggers: Logging object
        :return: data to be displayed on the payment successful page.
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        general_page_data = CommonPageData.create()
        paid_page_data = {
            **general_page_data
        }
        return paid_page_data


class FaqPage:
    """ Class for constructing data to be displayed on the FAQ page. """

    def __init__(self):
        pass

    @staticmethod
    def create(loggers=None, show_number: int = 0) -> dict:
        """
        Construct data to be displayed on the FAQ page.
        :param loggers: Logging object
        :param show_number: Faq number to show selected upon load
        :return: data to be displayed on FAQ page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        general_page_data = CommonPageData.create()
        faq_items = FaqItems.create(show_number=show_number)
        faq_page_data = {
            'faq_items': faq_items,
            **general_page_data
        }
        loggers['data'].info(f"Paid page data: {pformat(faq_page_data)}")
        return faq_page_data


class FaqItems:
    """ Class for constructing a list of FAQ page entries. """

    def __init__(self):
        pass

    @staticmethod
    def create(loggers=None, show_number: int = 0) -> list[dict[str, str]]:
        """
        Construct FAQ page data from the Faq page xml file
        :param loggers: Logging object
        :param show_number: Faq number to show selected upon load
        :return: question list of question and answer strings
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        questions = []
        source_file = Settings.Main['faq_file']
        with open(source_file, 'r') as f:
            faq_content = bs(''.join(f.readlines()), 'lxml')
        faq_items = faq_content.find('questions').find_all('faq-item')
        for i, faq_item in enumerate(faq_items, start=1):
            question_contents = ''.join(str(s) for s in faq_item.find('question').children).replace('\n', '')
            answer_contents = ''.join([str(s) for s in faq_item.find('answer').children]).replace('\n', '')
            questions.append({
                'question': question_contents,
                'answer': answer_contents,
                'show_number': 'active' if show_number == i else ''
            })
        return questions


class SearchResults:
    """ Class for constructing search results data. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            search_text: str = '',
            pepe_query_tool: PepeData = None,
            results_per_page: int = 0,
            page_number: int = 0,
            loggers=None
    ) -> dict:
        """
        Construct the data for the search results page.
        :param search_text: text being searched
        :param pepe_query_tool: PepeData object for querying pepe data
        :param results_per_page: number of results to show on the page
        :param page_number: page number, if pagination is being used
        :param loggers: Logging object
        :return: data to be displayed on search results page
        """
        search_results_data = {
            **Settings.Site,
            'display_title': f"{search_text}",
            'search_text': search_text,
            'cards': [],
        }
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}

        search_results = pepe_query_tool.get_pepes_by_pattern(search_text)
        CardList.setup(pepe_query_tool=pepe_query_tool,
                       card_results=search_results,
                       card_results_output_data=search_results_data,
                       cards_per_page=results_per_page,
                       page_number=page_number,
                       page_url_base='/search',
                       list_type='search',
                       search_text=search_text)
        loggers['data'].info(f"Search results data: {pformat(search_results_data)}")
        return search_results_data


class ArtistCollection:
    """ Class for constructing data for the artist collection page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            address: str,
            pepe_query_tool: PepeData = None,
            pepes_per_page: int = 0,
            page_number: int = 0,
            loggers=None
    ) -> dict:
        """
        Construct the data for an artist collecton page
        :param address: address of the artist
        :param pepe_query_tool: PepeData object for querying pepe data
        :param pepes_per_page: how many pepes to show
        :param page_number: page number, if pagination is used
        :param loggers: Logging object
        :return: data to be displayed on the artist collection page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        collection_list_data = {
            'display_title': f"Artist: {address}",
            'address': address,
            'cards': [],
        }
        artist_collection = pepe_query_tool.get_address_artists(address)
        CardList.setup(
            pepe_query_tool=pepe_query_tool,
            card_results=artist_collection,
            card_results_output_data=collection_list_data,
            cards_per_page=pepes_per_page,
            page_number=page_number,
            page_url_base=f'/artist/{address}',
            list_type='artist'
        )

        loggers['data'].info(f"Search results data: {pformat(artist_collection)}")
        return collection_list_data


class AddressCollection:
    """ Class for constructing data to be shown on an address' pepe collection page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            address: str,
            pepe_query_tool: PepeData = None,
            pepes_per_page: int = 0,
            page_number: int = 0,
            loggers=None
    ) -> dict:
        """
        Construct the data for an address pepe collection page.
        :param address: address of the collection
        :param pepe_query_tool: PepeData object for querying pepe data
        :param pepes_per_page: number of pepes to show per page, if pagination used
        :param page_number: page number, if pagination used
        :param loggers: Logging object
        :return: address collection data to display
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        collection_list_data = {
            'display_title': f"{address}",
            'address': address,
            'cards': [],
        }
        address_collection = pepe_query_tool.get_address_holdings(address)
        CardList.setup(
            pepe_query_tool=pepe_query_tool,
            card_results=address_collection,
            card_results_output_data=collection_list_data,
            cards_per_page=pepes_per_page,
            page_number=page_number,
            page_url_base=f'/{address}',
            list_type='address'
        )
        loggers['data'].info(f"Search results data: {pformat(address_collection)}")
        return collection_list_data


class FeaturedPepes:
    """ Class for constructing data to be shown the featured pepes section. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_query_tool: PepeData = None,
            loggers=None
    ) -> dict:
        """
        Construct data for pepes shown in the featured pepes section.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param loggers: Logging object
        :return: data to be displayed in the featured pepes section
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        featured_pepes_list = pepe_query_tool.get_featured_pepes()
        loggers['data'].info(f"featured_pepes_list: {pformat(featured_pepes_list)}")
        featured_pepes = {}
        for featured_pepe in featured_pepes_list:
            if featured_pepe == 'PUMPURPEPE':
                pepe_url = url_for('advertise')
                pepe_image_url = url_for('static',
                                         filename=f"images/PUMPURPEPE.png")
            else:
                pepe_url = f"/{featured_pepe}"
                pepe_image_url = url_for('static',
                                         filename=pepe_images_url_relative + pepe_query_tool.
                                         get_pepe_image_filename(featured_pepe))
            featured = {
                'pepe_url': pepe_url,
                'pepe_image_url': pepe_image_url
            }
            featured_pepes[featured_pepe] = featured
        loggers['data'].info(f"Featured pepes data: {pformat(featured_pepes)}")
        return featured_pepes


class LatestDispensers:
    """ Class for constructing data to display the latest dispensers on a pepe page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_query_tool: PepeData = None,
            loggers=None
    ) -> dict:
        """
        Construct the list of dispensers for a pepe.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param loggers: Logging object
        :return: data to display the dispensers for a pepe page.
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        data_output = {
            'grid_title': "Latest Dispensers",
            'cards': []
        }
        cards_data = pepe_query_tool.get_latest_pepe_dispensers(count=54)
        loggers['data'].info(f"cards_data:\n{pformat(cards_data)}")
        for i, card_data in enumerate(cards_data):
            pepe_details = pepe_query_tool.get_pepe_details(card_data['asset'])
            pepe_image_url = url_for(
                'static',
                filename=pepe_images_url_relative + pepe_query_tool.get_pepe_image_filename(
                    pepe_name=card_data['asset']))
            # pepe_real_supply = pepe_query_tool.derive_pepe_real_supply(card_data['asset'])
            card_values = {
                'pepe_name': card_data['asset'],
                'pepe_url': f"/{card_data['asset']}",
                'pepe_image_url': pepe_image_url,
                'stock': Formats.pepe_quantity_str(
                    card_data['give_remaining'], pepe_details['divisible']),
                'supply': Formats.pepe_normalized_supply_str(pepe_details['real_supply'], pepe_details['divisible']),
                'pay': Formats.satoshis_to_str(card_data['satoshirate'])
            }
            data_output['cards'].append(card_values)
        loggers['data'].info(f"Search results data: {pformat(data_output)}")
        return data_output


class RandomPepes:
    """ Class for generating a random set of pepes """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_query_tool: PepeData = None,
            loggers=None
    ) -> dict:
        """
        Construct the data for displaying a random set of pepes on a page.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param loggers: Logging object
        :return: data including title of the list section and a list of the random pepe names
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        data_output = {
            'display_title': "Random Pepes",
            'cards': []
        }
        random_pepes = pepe_query_tool.get_random_pepes(count=54)
        loggers['data'].info(f"random_pepes:{pformat(random_pepes)}")
        for i, pepe_name in enumerate(random_pepes):
            pepe_details = pepe_query_tool.get_pepe_details(pepe_name)
            pepe_image_url = url_for(
                'static',
                filename=pepe_images_url_relative + pepe_query_tool.get_pepe_image_filename(
                                                             pepe_name=pepe_details['asset']))
            real_supply_str = Formats.pepe_quantity_str(pepe_details['real_supply'], pepe_details['divisible'])
            card_details = {
                'pepe_name': pepe_details['asset'],
                'pepe_url': f"/{pepe_details['asset']}",
                'pepe_image_url': pepe_image_url,
                'line_1': f"Series: {pepe_details['series']}",
                'line_2': f"Supply: {real_supply_str}"
            }
            data_output['cards'].append(card_details)
            loggers['data'].info(f"Card details: {pformat(card_details)}")
        loggers['data'].info(f"Search results data: {pformat(data_output)}")
        return data_output


class PepeDispensers:
    """ Class for constructing data for displaying pepe dispensers on a pepe page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_name: str,
            pepe_query_tool: PepeData = None,
            price_tool: PriceTool = None,
            pepe_details=None,
            fiat_enabled=False,
            loggers=None
    ) -> dict:
        """
        Construct the data to display dispensers on a pepe page.
        :param pepe_name: name of pepe being displayed
        :param pepe_query_tool: PepeData object for querying pepe data
        :param price_tool: price lookup tool
        :param pepe_details: data for the pepe
        :param fiat_enabled: whether to show usd value
        :param loggers: Logging object
        :return: dispenser data to be displayed
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_dispensers_data = pepe_query_tool.get_pepe_dispensers(pepe_name)
        pepe_dispensers_data = sorted(pepe_dispensers_data, key=lambda x: x['satoshirate'] / x['give_quantity'])

        pepe_image_url = url_for(
            'static',
            filename=pepe_images_url_relative + pepe_query_tool.pepe_images[pepe_name])
        table_headers = ['Pepe', 'Stock', 'Pay', 'Receive'] if not fiat_enabled \
            else ['Pepe', 'Stock', 'USD', 'Pay', 'Receive']
        data_output = {
            'table_title': "BTC Dispensers",
            'table_headers': table_headers,
            'pepe_image_url': pepe_image_url,
            'rows': []
        }
        for i, pepe_dispenser_data in enumerate(pepe_dispensers_data):
            row_values = {
                'pepe_url': f"/{pepe_name}" + f"?d={i}",
                'pepe_image_url': pepe_image_url,
                'address': pepe_dispenser_data['source'],
                'address_truncated': pepe_dispenser_data['source'][:6] + '...',
                'stock': Formats.pepe_quantity_str(
                    pepe_dispenser_data['give_remaining'], pepe_details['divisible']
                ),
                'usd_value': price_tool.convert_satoshis_to_usd(pepe_dispenser_data['satoshirate']),
                'pay': Formats.satoshis_to_str(pepe_dispenser_data['satoshirate']),
                'pay_btc': f"{pepe_dispenser_data['satoshirate'] / 10 ** 8:.8f}",
                'receive': Formats.pepe_quantity_str(pepe_dispenser_data['give_quantity'], pepe_details['divisible']),
                'fiat_enabled': fiat_enabled,
                'xchain_tx_url': f"https://xchain.io/tx/{pepe_dispenser_data['tx_hash']}"
            }
            data_output['rows'].append(row_values)
        loggers['data'].info(f"Search results data: {pformat(data_output)}")
        return data_output


class PepeOrders:
    """ Class for constructing data for displaying pepe pepe orders on a pepe page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_name: str,
            base_asset: str = "XCP",
            pepe_query_tool: PepeData = None,
            price_tool: PriceTool = None,
            pepe_details=None,
            fiat_enabled=False,
            loggers=None
    ) -> dict:
        """
        Construct the data to display pepe orders on a pepe page.
        :param pepe_name: name of pepe
        :param base_asset: base asset to base orders on.  'XCP' or 'PEPECASH'
        :param pepe_query_tool: PepeData object for querying pepe data
        :param price_tool: Price lookup tool
        :param pepe_details: Data for the pepe
        :param fiat_enabled: whether to include fiat pricing in the pepe info box
        :param loggers: Logging object
        :return: data to be displayed on the pepe orders list for a pepe page
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_sell_orders_data = sorted(
            pepe_query_tool.get_pepe_orders(pepe_name, status='open', base_asset=base_asset)['give'],
            key=lambda x: x['give_quantity'] / x['get_quantity'], reverse=True
        )
        pepe_buy_orders_data = sorted(
            pepe_query_tool.get_pepe_orders(pepe_name, status='open', base_asset=base_asset)['get'],
            key=lambda x: x['get_quantity'] / x['give_quantity']
        )
        output_order_type = {
            'get': 'buy',
            'give': 'sell'
        }
        pepe_image_url = url_for(
            'static',
            filename=pepe_images_url_relative + pepe_query_tool.pepe_images[pepe_name])
        pepe_thumbnail_url = url_for(
            'static', filename='pepes/images_thumbnails/') + pepe_query_tool.pepe_images[pepe_name]
        base_asset_image_url = url_for(
            'static', filename='pepes/images_thumbnails/') + pepe_query_tool.pepe_images[base_asset]
        table_headers = ['BTC', 'Price', 'Stock'] if not fiat_enabled else ['USD', 'BTC', 'Price', 'Stock']
        data_output = {
            'table_title': f'{base_asset} DEX',
            'buy_header': 'Buy Orders',
            'sell_header': 'Sell Orders',
            'table_headers': table_headers,
            'base_asset_header': 'Price',
            'pepe_asset_header': 'Stock',
            'pepe_url': f"/{pepe_name}",
            'pepe_image_url': pepe_image_url,
            'pepe_thumbnail_url': pepe_thumbnail_url,
            'base_asset_url': f"/{base_asset}",
            'base_asset_image_url': base_asset_image_url,
            'btc_image_url': url_for('static', filename='images/btc.png'),
            'buy_orders': [],
            'sell_orders': [],
            'fiat_enabled': fiat_enabled,
            'buy': {
                'header': 'Buy Orders',
                'orders': []
            },
            'sell': {
                'header': 'Sell Orders',
                'orders': []
            }
        }
        for db_order_type in ['get', 'give']:
            if db_order_type == 'get':
                order_data_set = pepe_buy_orders_data
                base_asset_type = 'give'
            else:
                order_data_set = pepe_sell_orders_data
                base_asset_type = 'get'
            for i, order_data in enumerate(order_data_set):
                pepe_units = Formats.pepe_units_normalize(
                    order_data[f'{db_order_type}_quantity'],
                    divisible=pepe_details['divisible'])
                base_units = Formats.pepe_units_normalize(
                    order_data[f'{base_asset_type}_quantity'],
                    divisible=True)
                pepe_stock = Formats.pepe_quantity_str(
                    order_data[f'{db_order_type}_remaining'], divisible=pepe_details['divisible'])
                pepe_price_int = base_units / pepe_units
                pepe_price_str = Formats.format_base_asset(pepe_price_int)
                convert_rate = price_tool.get_xcp_rate() if base_asset == 'XCP' else price_tool.get_pepecash_rate()
                price_in_btc = Formats.satoshis_to_str(
                    convert_rate * pepe_price_int / price_tool.get_btc_rate() * 10 ** 8)
                usd_value = f"${pepe_price_int * convert_rate:,.2f}"
                order_values = {
                    'pepe_amount': pepe_stock,
                    'base_asset_url': f"/{base_asset}",
                    'pepe_price': pepe_price_str,
                    'pepe_price_btc': price_in_btc,
                    'usd_value': usd_value,
                    'xchain_tx_url': f"https://xchain.io/tx/{order_data['tx_index']}"
                }
                data_output[output_order_type[db_order_type]]['orders'].append(order_values)

        loggers['data'].info(f"Search results data: {pformat(data_output)}")
        return data_output


class PepeHolders:
    """ Class for constructing data for displaying pepe pepe holders on a pepe page. """

    def __init__(self):
        pass

    @staticmethod
    def create(
            pepe_name: str,
            pepe_query_tool: PepeData = None,
            pepe_details: dict = None,
            show_holder_count: int = 0,
            loggers=None
    ) -> dict:
        """
        Construct the data for listing the holders of a pepe on a pepe page.
        :param pepe_name: name of pepe
        :param pepe_query_tool: PepeData object for querying pepe data
        :param pepe_details: dictionary data object of the pepe
        :param show_holder_count: how many holders to show in the list
        :param loggers: Logging object
        :return:
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_holders_data = pepe_query_tool.get_pepe_holdings(pepe_name)
        data_output = {
            'table_headings': ['Holder', 'Amount'],
            'holders_count': len(pepe_holders_data),
            'rows': []
        }
        total_real_holdings = Formats.pepe_units_normalize(pepe_details['supply'], pepe_details['divisible'])
        known_burns = []
        real_holders = []

        for pepe_holder in pepe_holders_data:
            if pepe_query_tool.is_burn_address(pepe_holder['address']):
                known_burns.append(pepe_holder)
                total_real_holdings -= Formats.pepe_units_normalize(pepe_holder['address_quantity'],
                                                                    pepe_details['divisible'])
            else:
                real_holders.append(pepe_holder)

        shown_quantities = 0
        for pepe_holder in real_holders[:show_holder_count]:
            holder_quantity_str = Formats.holders_table_amount_str(pepe_holder['address_quantity'],
                                                                   pepe_details['divisible'])
            holder_quantity_normalized = Formats.pepe_units_normalize(pepe_holder['address_quantity'],
                                                                      divisible=pepe_details['divisible'])
            supply_ratio = holder_quantity_normalized / total_real_holdings
            shown_quantities += holder_quantity_normalized
            row = {
                'address': pepe_holder['address'],
                'quantity': holder_quantity_str,
                'address_truncated': f"{pepe_holder['address'][:6]}...",
                'supply_percentage': Formats.holders_table_percentage_str(supply_ratio)
            }
            data_output['rows'].append(row)

        remain_supply = total_real_holdings - shown_quantities
        accumulated_ratio = remain_supply / total_real_holdings
        data_output['remaining_percentage'] = Formats.holders_table_percentage_str(accumulated_ratio)
        data_output['remaining_quantity'] = Formats.holders_table_amount_str(remain_supply,
                                                                             pepe_details['divisible'],
                                                                             is_normalized=True)
        data_output['remaining_holders_count'] = len(real_holders) - show_holder_count
        data_output['real_supply'] = Formats.pepe_normalized_supply_str(total_real_holdings, pepe_details['divisible'])

        return data_output


class CardList:
    """ Class for constructing data for displaying a card list of pepes on a search, artist, or address page. """

    def __init__(self):
        pass

    @staticmethod
    def setup(
            pepe_query_tool: PepeData = None,
            card_results=None,
            card_results_output_data=None,
            cards_per_page: int = 0,
            page_number: int = 0,
            page_url_base: str = '',
            list_type: str = '',
            search_text=''
    ):
        """
        Set up the data for a card list of pepes.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param card_results: list of card data dictionaries to be displayed
        :param card_results_output_data: dictionary to store the general display data
        :param cards_per_page: number of cards to be shown per page, if pagination is used
        :param page_number: page number to show data for, if pagination is used
        :param page_url_base: base url for the page
        :param list_type: address or search listing
        :param search_text: text being searched for
        :return: None
        """
        if card_results_output_data is None:
            card_results_output_data = {}
        if card_results is None:
            card_results = [{}]
        all_cards = []
        for card_data in card_results:
            if list_type == 'search':
                card = SearchResultCard.create(pepe_query_tool, card_data)
            elif list_type == 'address':
                card = AddressCollectionCard.create(pepe_query_tool, card_data)
            else:
                card = ArtistCollectionCard.create(pepe_query_tool, card_data)
            all_cards.append(card)

        if len(all_cards) > 0:
            cards_paginated = Paginator.paginate(all_cards, cards_per_page)  # create pagination of the current cards
            card_results_output_data['cards'] = cards_paginated[
                page_number]  # set the list of cards to the current page
            page_count = len(cards_paginated)
        else:
            page_count = 0
        card_results_output_data['page_number'] = page_number
        card_results_output_data['is_paginated'] = page_count > 1  # pagination only needed if more than 1 page
        card_results_output_data['total_pages'] = page_count
        card_results_output_data['page_url_base'] = page_url_base
        card_results_output_data['search_text'] = search_text


class SearchResultCard:
    """ Class for constructing data for displaying a pepe card on the search results page. """

    def __init__(self):
        pass

    @staticmethod
    def create(pepe_query_tool: PepeData, card_data: dict, loggers=None) -> dict:
        """
        Construct the data to display a pepe card on the search results page
        :param pepe_query_tool: PepeData object for querying pepe data
        :param card_data: data pertaining to the pepe card
        :param loggers: Logging object
        :return: data to be displayed for the search result card
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_details = pepe_query_tool.get_pepe_details(card_data['asset'])
        real_supply_str = Formats.pepe_quantity_str(pepe_details['real_supply'], pepe_details['divisible'])
        search_result_card = {
            'pepe_name': card_data['asset'],
            'pepe_url': f"/{card_data['asset']}",
            'pepe_image_url': Formats.get_pepe_image_url(pepe_query_tool, card_data['asset']),
            'line_1': f"Series: {card_data['series']}",
            'line_2': f"Supply: {real_supply_str}"
        }
        loggers['data'].info(f"Search results data: {pformat(search_result_card)}")
        return search_result_card


class ArtistCollectionCard:
    """ Class for constructing data for displaying pepe card on the artist collection page. """

    def __init__(self):
        pass

    @staticmethod
    def create(pepe_query_tool: PepeData, card_data: dict, loggers=None) -> dict:
        """
        Construct the data for a pepe card on the artist collection page.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param card_data: data pertaining to the pepe card
        :param loggers: Logging object
        :return: data for displaying a pepe card on the artist collection page.
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_details = pepe_query_tool.get_pepe_details(card_data['asset'])
        real_supply_str = Formats.pepe_quantity_str(pepe_details['real_supply'], pepe_details['divisible'])
        artist_collection_card = {
            'pepe_name': card_data['asset'],
            'pepe_url': f"/{card_data['asset']}",
            'pepe_image_url': url_for(
                'static',
                filename=pepe_images_url_relative + pepe_query_tool.get_pepe_image_filename(
                pepe_name=card_data['asset'])),
            'line_1': f"Series: {card_data['series']}",
            'line_2': f"Supply: {real_supply_str}"
        }
        loggers['data'].info(f"Search results data: {pformat(artist_collection_card)}")
        return artist_collection_card


class AddressCollectionCard:
    """ Class for constructing data for displaying pepe card on an address collection page. """

    def __init__(self):
        pass

    @staticmethod
    def create(pepe_query_tool: PepeData, card_data: dict, loggers=None) -> dict:
        """
        Construct the data for displaying a pepe card on the address collection page.
        :param pepe_query_tool: PepeData object for querying pepe data
        :param card_data: ata pertaining to the pepe card
        :param loggers: Logging object
        :return: data to be displayed for a pepe card on an address collection page.
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        pepe_details = pepe_query_tool.get_pepe_details(card_data['asset'])
        own = Formats.pepe_quantity_str(
            card_data['address_quantity'], pepe_details['divisible'])
        real_supply_str = Formats.pepe_quantity_str(pepe_details['real_supply'], pepe_details['divisible'])
        address_collection_card = {
            'pepe_name': card_data['asset'],
            'pepe_url': f"/{card_data['asset']}",
            'pepe_image_url':
                url_for(
                    'static',
                    filename=pepe_images_url_relative + pepe_query_tool.get_pepe_image_filename(
                        pepe_name=card_data['asset'])),
            'line_1': f"Owns {own} of {real_supply_str}"
        }
        loggers['data'].info(f"Search results data: {pformat(address_collection_card)}")
        return address_collection_card


class BTCPayServerHook:
    """ Class for processing the hook message triggered when an action occurs in BTCPayServer"""

    def __init__(self, payload: bytes = b'',
                 signature: str = '',
                 loggers=None):
        """
        Instantiate object
        :param payload: message sent from BTCPayServer
        :param signature: signature for verifying the payload
        :param loggers: Logging object
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data'),
                       'purchases': logging.getLogger('purchases')}
        self.loggers = loggers
        self.payload = payload
        self.signature = signature
        self.secret = Settings.Sources['btcpayserver']['secret']

    def verify(self):
        """
        Verifies the payload using the signature
        :return: True if verification successful, False otherwise
        """
        hmac256 = hmac.new(self.secret.encode(),
                           self.payload,
                           hashlib.sha256).hexdigest()
        return self.signature == f"sha256={hmac256}"

    def process_hook(self, payload_json: str):
        """
        Process the data received from BTCPayServer
        :param payload_json: json formatted payload data received
        :return: None
        """
        btcpayserver_connection = BTCPayServerConnector(loggers=self.loggers)
        self.loggers['data'].info(pformat(payload_json))
        self.loggers['purchases'].info(f"process_hook(\n{pformat(payload_json)}\n)")
        btcpayserver_query_tool = BTCPayServerData(btcpayserver_connection, loggers=self.loggers)
        if '__test__' not in payload_json['invoiceId']:
            invoice_data = btcpayserver_query_tool.get_invoice_data(payload_json['invoiceId'])
            self.loggers['purchases'].info(f"process_hook(\n{pformat(invoice_data)}\n)")
            if invoice_data.get('status', '') == 'paid' and payload_json['type'] == 'InvoiceProcessing':
                btcpayserver_query_tool.enqueue_ad(payload_json['invoiceId'])


class PaymentQuery:
    """ Class for handling a request on the advertising promotion page. """

    def __init__(self):
        pass

    @staticmethod
    def verify_pepe_name(pepe_name, loggers=None) -> bool:
        """
        Check to ensure a searched for pepe is a valid pepe name
        :param pepe_name: name of pepe to search
        :param loggers: Logging object
        :return: True if pepe name valid, False otherwise
        """
        if loggers is None:
            loggers = {'data': logging.getLogger('data')}
        db_connection = DBConnector(loggers=loggers)
        pepe_query_tool = PepeData(db_connection, loggers=loggers)
        return pepe_name in pepe_query_tool.get_pepe_names()


class InvoiceData:
    """Class for handling BTCPayServer invoice data."""

    def __init__(self):
        pass

    @staticmethod
    def create_url(pepe_name) -> str:
        """
        Create a url corresponding to an invoice created in BTCPayServer
        :param pepe_name: pepe name of ad purchased in the invoice
        :return: Url pointing to the invoice
        """
        btcpay_query_tool = BTCPayServerData()

        block_count = Settings.Ads['block_count']
        currency = Settings.Ads['currency']
        notification_url = Settings.Ads['notificationUrl']
        price = Settings.Ads['price']
        redirect_url = Settings.Ads['redirectURL']

        order_id = f"__test__{randint(100_000, 999_999)}"
        item_code = f"AD_{block_count}"
        item_description = f"5 Days worth of advertising for {pepe_name} at RarePepeWorld. First come, first serve."
        post_data = {
            'order_id': order_id,
            'pepe_name': pepe_name,
            'block_count': block_count
        }
        invoice_creation_data = {"orderId": order_id,
                                 "currency": currency,
                                 "itemCode": item_code,
                                 "itemDesc": item_description,
                                 "notificationUrl": notification_url,
                                 "redirectURL": redirect_url,
                                 "posData": str(post_data),
                                 "price": price}
        invoice_id = btcpay_query_tool.create_invoice(invoice_creation_data)
        return f"{Settings.Sources['btcpayserver']['pay_url']}/i/{invoice_id}"
