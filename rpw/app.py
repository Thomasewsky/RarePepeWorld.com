# -*- coding: utf-8 -*-
import logging
import traceback
from pprint import pformat

from flask import Flask, jsonify
from flask import render_template, request, redirect
from werkzeug.exceptions import HTTPException

from rpw.PagesData import IndexPage, ArtistPage, SearchPage, SubPage, AdvertisePage, BTCPayServerHook, PaidPage, \
    FaqPage, CommonPageData, InvoiceData
from rpw.Logging import Logger

# Flask main object
app = Flask(__name__, instance_relative_config=True)
app.config.from_mapping(
    SECRET_KEY='iylIZfwfaTj8'
)

# Various loggers for logging different aspects of the site run
# each key represents a python Logger object
# specific values set in the Settings file
loggers = {
    'root': Logger.setup_logger('root', logging.getLogger('root')),
    'data': Logger.setup_logger('data', logging.getLogger('data')),
    'data_queries': Logger.setup_logger('data_queries', logging.getLogger('data_queries')),
    'errors': Logger.setup_logger('errors', logging.getLogger('errors')),
    'purchases': Logger.setup_logger('purchases', logging.getLogger('purchases'))
}


# Flask app entry point
def create_app():
    @app.route('/')
    def index():
        """ Render template for root of website
         :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route /")
        index_data = IndexPage.create(loggers=loggers, show_latest_dispensers=False)
        loggers['root'].info(f"Rendering template: index.html")
        return render_template('index.html',
                               **index_data)

    @app.route('/<page_name>/', methods=['GET', 'POST'], defaults={'page_number': 1})
    @app.route('/<page_name>/<int:page_number>/', methods=['GET', 'POST'])
    def sub_page(page_name: str, page_number: int):
        """ Given a valid sub-page name, render either a pepe or an address page, or a 404 page.
        :param page_number: page number to show in the rendering
        :param page_name: String of the sub-path
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route /{page_name}/\n"
                             f"page_number: {page_number}")
        subpage_data = SubPage.create(
            page_name,
            args=request.args,
            page_number=page_number,
            loggers=loggers
        )
        if subpage_data[0] == 'pepe':  # page is of a pepe
            loggers['root'].info("Rendering template: pepe.html")
            return render_template('pepe.html', **subpage_data[1])
        elif subpage_data[0] == 'address':  # page is for an address
            loggers['root'].info("Rendering template: address.html")
            return render_template('address.html', **subpage_data[1])
        else:  # invalid page type
            loggers['root'].info("Rendering template: 404.html")
            return render_template('404.html', **subpage_data[1])

    @app.route('/artist/<address_str>/', methods=['GET', 'POST'], defaults={'page_number': 1})
    @app.route('/artist/<address_str>/<int:page_number>/', methods=['GET', 'POST'])
    def artist(address_str, page_number):
        """ Render a page showing all the pepe issuers, represented by an address
        :param address_str:  Address of the issuer
        :param page_number: page number to show in the rendering
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route /artist/{address_str}/\n"
                             f"page_number: {page_number}")
        artist_page_data = ArtistPage.create(
            address_str,
            page_number=page_number,
            loggers=loggers
        )
        loggers['root'].info(f"Rendering template: address.html")
        return render_template('address.html',
                               **artist_page_data)

    @app.route('/search', methods=['POST'])
    @app.route('/search/', methods=['POST'])
    def search_post():
        """ Render a search page showing the results of a query when the search sub-page is used via POST.
        Redirects the post details to the /search/ url for the query. """
        search_text = request.form.get('search_text', '')
        loggers['root'].info(f"Search requested for {search_text}")
        return redirect(f'/search/{search_text}/')

    @app.route('/search/<search_text>/', defaults={'page_number': 1})
    @app.route('/search/<search_text>/<int:page_number>/')
    def search(search_text, page_number):
        """ Render page showing the results of a search query term.
        :param search_text: Text of query
        :param page_number: Page number of paginated results
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route /search with query {search_text}\n"
                             f"Pagination number: {page_number}")
        is_direct_match, render_data = SearchPage.create(
            search_text=search_text,
            page_number=page_number,
            loggers=loggers)
        if is_direct_match:
            loggers['root'].info(f"Address or direct Pepe match. Redirect to /{search_text}")
            return redirect(f"/{search_text}")
        else:
            loggers['root'].info(
                f"No direct match. Rendering template 'search.html' with the search term {search_text}")
            return render_template('search.html',
                                   **render_data)

    @app.route('/advertise')
    @app.route('/advertise/')
    def advertise():
        """ Render template for advertising promo page.
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route: /advertise")
        ad_page_data = AdvertisePage.create(loggers=loggers)
        loggers['root'].info("Rendering template advertise.html")
        return render_template(
            'advertise.html',
            **ad_page_data
        )

    @app.route('/faq/', defaults={'show_number': 0})
    @app.route('/faq/<show_number>/')
    def faq(show_number):
        """ Render template for faq page
        :param show_number: FAQ question to show focussed on the rendered page.
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route: /faq/")
        faq_page_data = FaqPage.create(loggers=loggers, show_number=show_number)
        loggers['root'].info("Rendering template faq.html")
        return render_template(
            'faq.html',
            **faq_page_data
        )

    @app.route('/advertise_testing')
    @app.route('/advertise_testing/')
    def advertise_testing():
        """ Render advertising test page
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route: /advertise_testing")
        ad_page_data = AdvertisePage.create(loggers=loggers)
        loggers['root'].info("Rendering template advertise_testing.html")
        return render_template(
            'advertise_testing.html',
            **ad_page_data
        )

    @app.route('/invoice_result', methods=['POST'])
    @app.route('/invoice_result/', methods=['POST'])
    def successful_payment():
        """ Render template when a successful payment is received
        :return: Flask rendered template
        """
        loggers['root'].info(f"Calling route: /successful_payment/")
        paid_page_data = PaidPage.create(loggers=loggers)
        loggers['root'].info("Rendering template paid.html")
        return render_template(
            'paid.html',
            **paid_page_data
        )

    @app.route('/invoice', methods=['POST'])
    @app.route('/invoice/', methods=['POST'])
    def process_invoice():
        loggers['root'].info(f"Calling route invoice")
        loggers['purchases'].info(f"Buy button clicked.")
        loggers['purchases'].info(pformat(request.form))
        pepe_name = request.form.get('choosen_pepe', '')
        invoice_url = InvoiceData.create_url(pepe_name)
        loggers['root'].info(f"Redirect to {invoice_url}")
        loggers['purchases'].info(f"New invoice url: {invoice_url}")
        return redirect(invoice_url)

    @app.route('/B28vk', methods=['POST'])
    @app.route('/B28vk/', methods=['POST'])
    def btcpayserver_hook():
        loggers['root'].info(f"Calling route btcpayserver_hook")
        loggers['purchases'].info(f"Webhook, Received at B28vk")
        if request.method == 'POST':
            loggers['purchases'].info(f"Webhook, Received data\n {pformat(request.json)}")
            payload_parser = BTCPayServerHook(
                request.data,
                request.headers.get('Btcpay-Sig', ''),
                loggers=loggers
            )
            if payload_parser.verify():
                loggers['purchases'].info(f"Webhook: Signature verified.")
                payload_parser.process_hook(request.json)
                return 'SUCCESS', 202
        else:
            loggers['root'].info(f"Webhook request was attempted and failed.")
            loggers['purchases'].info(f"Webhook request was attempted and failed.")
            return 'POST Method not supported', 405

    @app.errorhandler(Exception)
    def handle_exception(e):
        """ Render error page when site error occurs that is not handled. """
        loggers['errors'].exception(e)
        if isinstance(e, HTTPException):
            return e
        page_data = CommonPageData.create(loggers=loggers)
        return render_template("error.html", e=e, **page_data), 500

    return app
