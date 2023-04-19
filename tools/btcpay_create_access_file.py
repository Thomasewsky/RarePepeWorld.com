import sys
import pickle
from pathlib import Path
from pprint import pprint
import hashlib
import hmac

from btcpay import BTCPayClient


def display_syntax():
    print(f"{Path(__file__).name} <pairing_code> <client_store_file>")


def create_pairing_object(pairing_code: str, client_store_file: str):
    with open(client_store_file, 'wb') as out_file:
        client = BTCPayClient.create_client(host='https://pay.rarepepeworld.com', code=pairing_code)
        pickle.dump(client, out_file)
        print(f"Wrote: {client_store_file}")


if len(sys.argv) != 3:
    display_syntax()

pairing_code = sys.argv[1]
client_store_file = sys.argv[2]
create_pairing_object(pairing_code,client_store_file)
