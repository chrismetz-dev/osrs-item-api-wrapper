"""A module containing useful tools for obtaining item information and pricing data."""
import requests
from prettytable import PrettyTable
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict


class Timestamp(Enum):
    """Contains acceptable timestamps for the OSRS wiki."""
    LATEST = 'latest'
    FIVE_MINUTE = '5m'
    ONE_HOUR = '1h'
    SIX_HOUR = '6h'


class Ge_Timestamp(Enum):
    """Contains acceptable timestamps for the official GE."""
    CURRENT = 'current'
    TODAY = 'today'
    DAY30 = 'day30'
    DAY90 = 'day90'
    DAY180 = 'day180'


def value_to_float(x: str):
    """
    Converts strings with abbreviated numbers to floats

    >>> value_to_float('1.2k')
    1200.0
    """
    if type(x) == float or type(x) == int:
        return x
    x = x.upper()
    x = x.replace(',', '')
    if 'K' in x:
        if len(x) > 1:
            return float(x.replace('K', '')) * 1000
        return 1000.0
    if 'M' in x:
        if len(x) > 1:
            return float(x.replace('M', '')) * 1000000
        return 1000000.0
    if 'B' in x:
        return float(x.replace('B', '')) * 1000000000
    return float(x)


@dataclass
class Item:
    """A class to store item information and pricing."""
    id: str
    members: bool
    lowalch: int
    limit: int
    npc_value: int
    highalch: int
    name: str
    high_price: int
    low_price: int
    avg_high_price: Dict[Timestamp, int]
    high_price_volume: Dict[Timestamp, int]
    avg_low_price: Dict[Timestamp, int]
    low_price_volume: Dict[Timestamp, int]

    def __post_init__(self):
        self.margin = self.high_price-self.low_price
        self.roi = self.margin/self.low_price * 100
        self.platinumtokens_link = f'https://platinumtokens.com/item/{self.name.lower().replace(" ", "-")}'
        self._ge_data_endpoint = f'http://services.runescape.com/m=itemdb_oldschool/api/catalogue/detail.json?item={self.id}'
        self._ge_data = None

    # Keep this as a separate function so that we can update GE data
    def _update_ge_data(self, session: requests.Session):
        """Returns and caches official live GE data."""
        self._ge_data = session.get(self._ge_data_endpoint).json()['item']
        return self._ge_data

    def _get_ge_data(self, session: requests.session):
        """Returns cached GE data or if none, calls and returns the update function."""
        if self._ge_data:
            return self._ge_data
        else:
            return self._update_ge_data(session)


class OsrsItemManager:
    """
    A tool that finds and stores GE item data.

    Collects and stores item information and pricing data from the OSRS wiki
    and the official Runescape website.
    """

    def __init__(self, user_agent: str):
        """
        Initializes the item manager.

        user_agent (str): A description of what you are using the item
            manager for and your contact information,
            for example: 'volume_tracker - @Cook#2222'."""
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        self.update_prices()
        self.item_info = {str(item_info['id']): item_info
                          for item_info in self.session.get('https://prices.runescape.wiki/api/v1/osrs/mapping').json()}

    def update_prices(self):
        """Updates the live pricing data from the OSRS wiki."""
        self.price_info = {}
        for timestamp in Timestamp:
            self.price_info[timestamp] = self.session.get(
                f'https://prices.runescape.wiki/api/v1/osrs/{timestamp.value}').json()['data']
        return self.price_info

    def get_item(self, item_id: str) -> Item:
        """
        Returns an instance of Item containing item information and pricing
        or None if the item information could not be populated.

        Args:
            item_id (str): the ID of the item you want.
        """
        try:
            itm_d = self.item_info[item_id]  # item information data
            itm_pl = self.price_info[Timestamp.LATEST][item_id]
            avg_high_price = {}
            high_price_volume = {}
            avg_low_price = {}
            low_price_volume = {}
            for timestamp in Timestamp:
                if timestamp == Timestamp.LATEST:
                    continue
                data = self.price_info[timestamp][item_id]
                avg_high_price[timestamp] = data['avgHighPrice']
                high_price_volume[timestamp] = data['highPriceVolume']
                avg_low_price[timestamp] = data['avgLowPrice']
                low_price_volume[timestamp] = data['lowPriceVolume']
            return Item(itm_d['id'], itm_d['members'], itm_d['lowalch'],
                        itm_d['limit'], itm_d['value'], itm_d['highalch'],
                        itm_d['name'], itm_pl['high'], itm_pl['low'],
                        avg_high_price, high_price_volume, avg_low_price, low_price_volume)
        except KeyError:
            return None

    def get_items(self) -> List[Item]:
        """Returns a list of all items."""
        items = []
        for item_id in list(self.item_info.keys()):
            item = self.get_item(item_id)
            if item:
                items.append(item)
        return items

    def _get_ge_data(self, item:Item, force_latest:bool):
        data = None
        if force_latest:
            data = item._update_ge_data(self.session)
        else:
            data = item._get_ge_data(self.session)
        
        return data

    def get_ge_price_change(self, item: Item, ge_timestamp: Ge_Timestamp, force_latest:bool = False) -> str:
        """
        Returns the long-term % change in price of an item.

        Sample output: '-32.0%' or '+1.0%'

        Args:
            item (Item): an instance of the item dataclass
            ge_timestamp (Ge_Timestamp): A valid timestamp of 30 days or longer.
        """
        if not isinstance(ge_timestamp, Ge_Timestamp) or ge_timestamp == Ge_Timestamp.CURRENT or ge_timestamp == Ge_Timestamp.TODAY:
            raise NameError(
                f'Time selected was not in the list of valid times: {list(Ge_Timestamp._member_names_)[2:]}')
        return self._get_ge_data(item, force_latest)[ge_timestamp.value]['change']

    def get_ge_trend(self, item: Item, ge_timestamp: Ge_Timestamp, force_latest:bool = False) -> str:
        """Returns the trend of an item, 'positive', 'neutral', or 'negative'."""
        if not isinstance(ge_timestamp, Ge_Timestamp):
            raise NameError(
                f'Time selected was not in the list of valid times: {list(Ge_Timestamp._member_names_)}')
        return self._get_ge_data(item, force_latest)[ge_timestamp]['trend']

    def get_ge_today_price_change(self, item: Item, force_latest:bool = False) -> str:
        """Returns the amount an item has changed in price today eg '+7' or '-3'."""
        return self._get_ge_data(item, force_latest)['today']['price']

    def get_ge_current_price(self, item: Item, force_latest:bool = False) -> int:
        """Returns the currently listed GE price as an int."""
        return value_to_float(self._get_ge_data(item, force_latest)['current']['price'])

    def print_items(self, items: List[Item],
                    columns: List[str] = [
                        'Name', 'Low Price', 'High Price', 'Link'],
                    getters=[lambda item: getattr(item, 'name'),
                             lambda item: getattr(item, 'low_price'),
                             lambda item: getattr(item, 'high_price'),
                             lambda item: getattr(item, 'platinumtokens_link')]):
        """
        Prints items in a pretty table.

        Args:
            items ([Item]): The list of items you wish to display.
            columns ([str]): A list of column headings for the items.
            getters ([func]): A list of functions to get the data for
                each column.
        """
        table = PrettyTable(['Name', 'Low Price', 'High Price', 'Link'])
        for item in items:
            table.add_row([g(item) for g in getters])
        print(table)
