#!/usr/bin/env python
import set_paths
import logging
import sys
from pprint import pformat
from random import choice, randint

from rpw.DataConnectors import RPCConnector, DBConnector
from rpw.QueryTools import CPData, PepeData
from Settings import Ads

logging.basicConfig(filename='../logs/ad_sequencer.log',
                    level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')


class AdSequencer:
    def __init__(self):
        self.LAST_BLOCK_FILE = "../rpw/static/data/ad_latest_block_check"
        self.default_ads = Ads['default_ads']
        self.cp_connection = RPCConnector()
        self.cp_data = CPData(self.cp_connection)
        self.db_connection = DBConnector()
        self.current_block = self.cp_data.get_cp_last_block()
        self.last_block_checked = self.get_last_block_checked()

    def get_current_block(self):
        # Get current block
        current_block = self.cp_data.get_cp_last_block()
        print(f"Current block: {current_block}")
        return current_block

    def get_last_block_checked(self):
        with open(self.LAST_BLOCK_FILE) as f:
            result = f.readline().strip()
        last_block_checked = int(result)
        print(f"Last check block: {last_block_checked}")
        return last_block_checked

    def decrement_blocks_remaining(self):
        for i in range(1, 4):
            query_decrement = f'UPDATE ad_slots SET ' \
                              f'block_remain=IF(block_remain=0, 0, block_remain-1) WHERE slot_number={i}'
            print(f"Query: {query_decrement}")
            self.db_connection.execute(query_decrement)

    def get_current_ads(self):
        # ads history, Just informational, not part of the algorithm
        query_ad_slots = 'SELECT * FROM ad_slots'
        ad_slots = [ad for ad in self.db_connection.query_and_fetch(query_ad_slots)]
        print(f"Current ad slots:\n{pformat(ad_slots)}\n")
        return ad_slots

    def get_active_ads_count(self):
        query_active = 'SELECT COUNT(*) FROM ad_slots WHERE block_remain>0'
        active_ads = [ad for ad in self.db_connection.query_and_fetch(query_active)]
        print(f"Active ads:\n{pformat(active_ads)}\n")
        return active_ads[0][0]

    def get_finished_ads_count(self):
        query_finished = 'SELECT COUNT(*) FROM ad_slots WHERE block_remain=0'
        finished_ads = [ad for ad in self.db_connection.query_and_fetch(query_finished)]
        print(f"Finished ads:\n{pformat(finished_ads)}\n")
        return finished_ads[0][0]

    def get_ready_ads(self, count: int):
        query_ad_queue = f'SELECT * FROM ad_queue ORDER BY id LIMIT {count}'
        queued_ads = [ad for ad in self.db_connection.query_and_fetch(query_ad_queue)]
        print(f"Query: {query_ad_queue}")
        return queued_ads

    def display_ad_slots(self):
        # ads history, Just informational, not part of the algorithm
        query_ad_slots = 'SELECT * FROM ad_slots'
        ad_slots = [ad for ad in self.db_connection.query_and_fetch(query_ad_slots)]
        print(f"Running:\n{pformat(ad_slots)}\n")

    def display_ad_queue(self):
        # ads history, Just informational, not part of the algorithm
        query_ad_queue = 'SELECT * FROM ad_queue'
        ad_queue = [ad for ad in self.db_connection.query_and_fetch(query_ad_queue)]
        print(f"Queue:\n{pformat(ad_queue)}\n")

    def display_ad_history(self):
        # ads history, Just informational, not part of the algorithm
        query_ad_history = 'SELECT * FROM ad_history'
        historical_ads = [ad for ad in self.db_connection.query_and_fetch(query_ad_history)]
        print(f"History:\n{pformat(historical_ads)}\n")

    def display_ad_slot_history(self):
        # ads history, Just informational, not part of the algorithm
        query_ad_history = 'SELECT * FROM ad_slot_history'
        print(f"Slot history query: {query_ad_history}")
        slot_ads_history = [ad for ad in self.db_connection.query_and_fetch(query_ad_history)]
        print(f"History:\n{pformat(slot_ads_history)}\n")

    def move_to_history(self, ad_queue_entry: dict):
        # insert queued ad into ad_history
        print(f"Move to history...")
        query_insert_to_history = f'INSERT INTO ad_history ' \
                                  f'(asset,block_amount,paid_invoice) ' \
                                  f'VALUES (\'{ad_queue_entry[1]}\',\'{ad_queue_entry[2]}\',\'{ad_queue_entry[3]}\')'
        print(f"Query: {query_insert_to_history}")
        self.db_connection.execute(query_insert_to_history)

        # purge queued ad from the queue
        print(f"Delete from ad queue...")
        query_delete = f"DELETE FROM ad_queue WHERE id={ad_queue_entry[0]}"
        print(f"Query: {query_delete}")
        self.db_connection.execute(query_delete)

    def update_slot(self, slot_number: int, new_ad: tuple or list):
        query_update = f"UPDATE ad_slots SET " \
                       f"asset='{new_ad[1]}',block_remain={new_ad[2]},paid_invoice='{new_ad[3]}' " \
                       f"WHERE slot_number={slot_number}"
        print(f"Query: {query_update}")
        self.db_connection.execute(query_update)

    def add_queued_ad(self, data_set: tuple or list):
        query_insert = f"INSERT INTO ad_queue " \
                       f"(asset,paid_invoice,block_amount) " \
                       f"VALUES {str(tuple(data_set))}"
        print(f"Query: {query_insert}")
        self.db_connection.execute(query_insert)

    def random_ad_queue(self, count: int):
        def random_block_amount():
            return randint(1, 4)

        def random_pepe():
            return choice(pepe_data.get_pepe_names())

        pepe_data = PepeData(db_connector=self.db_connection)
        random_ads = [(random_pepe(), '__testing__', random_block_amount()) for _ in range(count)]

        return random_ads

    def display_state(self):
        self.display_ad_slots()
        self.display_ad_queue()
        self.display_ad_history()
        self.display_ad_slot_history()

    def update_slot_history(self, current_block: int, entries: list):
        query = f"INSERT INTO ad_slot_history (block_level,slot1,slot2,slot3) " \
                f"VALUES ('{current_block}','{entries[0]}','{entries[1]}','{entries[2]}')"
        print(query)
        self.db_connection.execute(query)

    @classmethod
    def insert_random_ads(cls, count: int, db_connection: None):
        ad_sequencer = AdSequencer()
        ads = ad_sequencer.random_ad_queue(count)
        for ad in ads:
            ad_sequencer.add_queued_ad(ad)


def main():
    print("-----Ad Sequencer-----")
    try:
        if sys.argv[1] == 'fill_queue':
            print("--Inserting random test ads...")
            AdSequencer.insert_random_ads(int(sys.argv[2]))
    except ValueError:
        pass
    except IndexError:
        pass

    ad_sequencer = AdSequencer()
    last_block_checked = ad_sequencer.get_last_block_checked()
    print(f"Latest block checked: {last_block_checked}")
    latest_cp_block = ad_sequencer.get_current_block()
    print(f"Latest cp block: {latest_cp_block}")

    if last_block_checked < latest_cp_block:
        print("\n--Database State--")
        ad_sequencer.display_state()

        print("\n--Decreasing block remaining accounts for current ads...")
        ad_sequencer.decrement_blocks_remaining()

        print("\n---Updated slot values:")
        current_slots = ad_sequencer.get_current_ads()

        print("\n--Determine active and expired ads:")
        slots = {
            'active': [slot_entry for slot_entry in current_slots if slot_entry[2] > 0],
            'expired': [slot_entry for slot_entry in current_slots if slot_entry[2] == 0]
        }
        print(f"{pformat(slots)}")

        print("\n--Determine ads to replace expired ads...")
        next_ads = ad_sequencer.get_ready_ads(
            len(slots['expired']))  # list of ready ads, all available up to amount needed
        print(pformat(next_ads))

        print("\n--Setup new slot values:")
        for expired_ad in slots['expired'][:]:
            print(f"\nExpired ad: {pformat(expired_ad)}")
            slots['expired'].remove(expired_ad)
            if len(next_ads) > 0:
                next_ad = next_ads.pop(0)
                print(f"Next ad: {next_ad}")
                slots['active'].append(next_ad)
                if expired_ad[2] != '__default__':
                    print("--Archiving ad")
                    ad_sequencer.move_to_history(next_ad)
        print(f"{pformat(slots)}")

        print("\n--Determine new slot positions...")
        updated_slots = []
        active_ads_count = len(slots['active'])
        if active_ads_count == 0:  # RANDOM, PUMPURPEPE, PEPETRADERS
            updated_slots.append(ad_sequencer.default_ads['_RANDOM_'])
            updated_slots.append(ad_sequencer.default_ads['PUMPURPEPE'])
            updated_slots.append(ad_sequencer.default_ads['PEPETRADERS'])
        elif active_ads_count == 1:  # RANDOM, PUMPURPEPE, NEW
            updated_slots.append(ad_sequencer.default_ads['_RANDOM_'])
            updated_slots.append(ad_sequencer.default_ads['PUMPURPEPE'])
            updated_slots.append(slots['active'][0])
        elif active_ads_count == 2:  # NEW, PUMPURPEPE, NEW
            updated_slots.append(slots['active'][0])
            updated_slots.append(ad_sequencer.default_ads['PUMPURPEPE'])
            updated_slots.append(slots['active'][1])
        else:  # NEW, NEW, NEW
            updated_slots.append(slots['active'][0])
            updated_slots.append(slots['active'][1])
            updated_slots.append(slots['active'][2])
        print(f"{pformat(updated_slots)}")

        print("\n--Update database ad slots...")
        for i, slot_data in enumerate(updated_slots, start=1):
            ad_sequencer.update_slot(i, slot_data)

        print(f"Updating slot history...")
        new_ads = ad_sequencer.get_current_ads()
        ad_sequencer.update_slot_history(latest_cp_block, [new_ads[0][1], new_ads[1][1], new_ads[2][1]])

        print("\nFinal database state: ")
        ad_sequencer.display_state()

        print("\nClose database and exit.")
        ad_sequencer.db_connection.close()


if __name__ == '__main__':
    main()
