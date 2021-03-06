"""A module containing useful tools for obtaining item information and pricing data."""
import requests
from prettytable import PrettyTable
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict


class Timestamp(Enum):
    """Contains acceptable timestamps for the OSRS wiki."""
    LATEST = 'latest'
    FIVE_MINUTE = '5m'
    ONE_HOUR = '1h'
    SIX_HOUR = '6h'


class GeTimestamp(Enum):
    """Contains acceptable timestamps for the official GE."""
    CURRENT = 'current'
    TODAY = 'today'
    DAY30 = 'day30'
    DAY90 = 'day90'
    DAY180 = 'day180'


def _value_or_none(data, key):
    """Returns the value of data at key or None if they key does not exist or if data is not subscriptable."""
    try:
        return data[key]
    except KeyError:
        return None
    except TypeError:
        return None


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


TimedData = Dict[Timestamp, int]


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
    avg_high_price: TimedData
    high_price_volume: TimedData
    avg_low_price: TimedData
    low_price_volume: TimedData
    margin: int = field(init=False)
    roi: int = field(init=False)
    platinumtokens_link: str = field(init=False)

    def __post_init__(self):
        if self.high_price and self.low_price:
            self.margin = self.high_price-self.low_price
            self.roi = self.margin/self.low_price * 100
        else:
            self.margin = None
            self.roi = None
        self.platinumtokens_link = f'https://platinumtokens.com/item/{self.name.lower().replace(" ", "-")}'
        self._ge_data_endpoint = f'http://services.runescape.com/m=itemdb_oldschool/api/catalogue/detail.json?item={self.id}'
        self._ge_data = None

    def _get_timestamp_data(self, attr: str, timestamp: Timestamp) -> TimedData:
        if timestamp == Timestamp.LATEST:
            raise KeyError(
                "Latest is not a valid timestamp - 5 minutes or more is required for averages.")
        return getattr(self, attr)[timestamp]

    def get_avg_high_price(self, timestamp: Timestamp):
        """Returns the average high price of the item over the timestamp period."""
        return self._get_timestamp_data('avg_high_price', timestamp)

    def get_high_price_volume(self, timestamp: Timestamp):
        """Returns the volume of items sold at the high value over the timestamp period."""
        return self._get_timestamp_data('high_price_volume', timestamp)

    def get_avg_low_price(self, timestamp: Timestamp):
        """Returns the average low price of the item over the timestamp period."""
        return self._get_timestamp_data('avg_low_price', timestamp)

    def get_low_price_volume(self, timestamp: Timestamp):
        """Returns the volume of items sold at the low value over the timestamp period."""
        return self._get_timestamp_data('low_price_volume', timestamp)

    def has_attr(self, attr):
        """returns true if the attribute is not None"""
        return bool(getattr(self, attr))

    def has_timedata(self, attr: str, timestamp: Timestamp):
        """returns true if the attribute is not None at the provided timestamp"""
        if not self.has_attr(attr):
            return False
        return bool(getattr(self, attr)[timestamp])

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
        itm_d = _value_or_none(self.item_info, item_id)
        itm_pl = _value_or_none(self.price_info[Timestamp.LATEST], item_id)

        i_id = item_id
        i_members = _value_or_none(itm_d, 'members')
        i_lowalch = _value_or_none(itm_d, 'lowalch')
        i_limit = _value_or_none(itm_d, 'limit')
        i_value = _value_or_none(itm_d, 'value')
        i_highalch = _value_or_none(itm_d, 'highalch')
        i_name = _value_or_none(itm_d, 'name')
        i_high = _value_or_none(itm_pl, 'high')
        i_low = _value_or_none(itm_pl, 'low')

        avg_high_price = {}
        high_price_volume = {}
        avg_low_price = {}
        low_price_volume = {}
        for timestamp in Timestamp:
            if timestamp == Timestamp.LATEST:
                continue
            try:
                # Not all items are availible in this data.
                # Assign none and skip if this is the case.
                data = self.price_info[timestamp][item_id]
            except KeyError:
                avg_high_price[timestamp] = None
                high_price_volume[timestamp] = None
                avg_low_price[timestamp] = None
                low_price_volume[timestamp] = None
                continue

            # The data is there, so if this breaks we want an error.
            avg_high_price[timestamp] = data['avgHighPrice']
            high_price_volume[timestamp] = data['highPriceVolume']
            avg_low_price[timestamp] = data['avgLowPrice']
            low_price_volume[timestamp] = data['lowPriceVolume']
        return Item(i_id, i_members, i_lowalch,
                    i_limit, i_value, i_highalch,
                    i_name, i_high, i_low,
                    avg_high_price, high_price_volume, avg_low_price, low_price_volume)

    def get_items(self) -> List[Item]:
        """Returns a list of all items."""
        # I tried to do a list comphrehension here but things got weird...
        # TODO try again.
        items = []
        for item_id in list(self.item_info.keys()):
            item = self.get_item(item_id)
            if item:
                items.append(item)
        return items

    def filter_empty_items(self, items: List[Item], attributes: List[str] = list(vars(Item)['__annotations__'])):
        """Removes items with None values at the provided attributes."""
        filtered_items = []
        for item in items:
            include_item_flag = True
            for attr in attributes:
                if not item.has_attr(attr):
                    include_item_flag = False
                    break
            if include_item_flag:
                filtered_items.append(item)
        return filtered_items

    # Lot of repeated code, maybe there's a more elegant way to do this?
    def filter_empty_timedata(self,
                              items: List[Item],
                              attributes: List[str] = [
                                  'avg_high_price', 'high_price_volume', 'avg_low_price', 'low_price_volume'],
                              timestamps: List[Timestamp] = [ts for ts in Timestamp][1:]):
        """Removes items with None values at the provided attributes and timestamps."""
        filtered_items = []
        for item in items:
            include_item_flag = True
            for attr in attributes:
                if not item.has_attr(attr):
                    include_item_flag = False
                    break
                for ts in timestamps:
                    if not item.has_timedata(attr, ts):
                        include_item_flag = False
                        break
            if include_item_flag:
                filtered_items.append(item)
        return filtered_items

    def _get_ge_data(self, item: Item, force_latest: bool):
        data = None
        if force_latest:
            data = item._update_ge_data(self.session)
        else:
            data = item._get_ge_data(self.session)

        return data

    def get_ge_price_change(self, item: Item, ge_timestamp: GeTimestamp, force_latest: bool = False) -> float:
        """
        Returns the long-term % change in price of an item over the provided timestamp.

        Sample output: -32.0 or 1.0

        Args:
            item (Item): an instance of the item dataclass
            ge_timestamp (GeTimestamp): A valid timestamp of 30 days or longer.
            force_latest (bool): Forces the cache to update with the most recent data (slow!)
        """
        if not isinstance(ge_timestamp, GeTimestamp) or ge_timestamp == GeTimestamp.CURRENT or ge_timestamp == GeTimestamp.TODAY:
            raise NameError(
                f'Time selected was not in the list of valid times: {list(GeTimestamp._member_names_)[2:]}')
        return float(self._get_ge_data(item, force_latest)[ge_timestamp.value]['change'].strip('%'))

    def get_ge_trend(self, item: Item, ge_timestamp: GeTimestamp, force_latest: bool = False) -> str:
        """Returns the trend of an item, 'positive', 'neutral', or 'negative'."""
        return self._get_ge_data(item, force_latest)[ge_timestamp.value]['trend']

    def get_ge_today_price_change(self, item: Item, force_latest: bool = False) -> int:
        """Returns the amount an item has changed in price today."""
        return int(self._get_ge_data(item, force_latest)['today']['price'])

    def get_ge_current_price(self, item: Item, force_latest: bool = False) -> int:
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
        table = PrettyTable(columns)
        for item in items:
            table.add_row([g(item) for g in getters])
        print(table)
