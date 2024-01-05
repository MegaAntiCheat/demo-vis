import json

from enum import Enum
from threading import Lock
from loguru import logger
from typing import Any


class UsefulServerClasses(Enum):
    Player = "CTFPlayer"
    PlayerResource = "CTFPlayerResource"


class UsefulDataTables(Enum):
    Local = "DT_Local"
    LocalPlayer = "DT_LocalPlayerExclusive"
    TFLocalPlayer = "DT_TFLocalPlayerExclusive"
    BaseEntity = "DT_BaseEntity"
    PlayerState = "DT_PlayerState"
    PlayerClass = "DT_TFPlayerClassShared"
    TFPlayerState = "DT_TFPlayerShared"
    AmmoValues = "m_iAmmo"
    PlayerScoring = "DT_TFPlayerScoringDataExclusive"
    TFPlayer = "DT_TFPlayer"
    BasePlayer = "DT_BasePlayer"


class Singleton(type):
    _instances = {}
    _lock = Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class SteamID:
    _steam_id_64_ident = 76561197960265728

    steam_id_3: str = None
    steam_id_64: int = None
    steam_id_1: str = None

    """
    The following converter functions are shamelessly taken from
    https://gist.github.com/bcahue/4eae86ae1d10364bb66d
    
    Slight renaming and reformatting has been performed.
    """
    @classmethod
    def _sid64_to_sid1(cls, comm_id):
        steam_id = ['STEAM_0:']
        steam_id_acct = int(comm_id) - cls._steam_id_64_ident
        steam_id.append('0:' if steam_id_acct % 2 == 0 else '1:')
        steam_id.append(str(steam_id_acct // 2))

        return ''.join(steam_id)

    @classmethod
    def _sid1_to_sid64(cls, steam_id):
        sid_split = steam_id.split(':')
        comm_id = int(sid_split[2]) * 2

        if sid_split[1] == '1':
            comm_id += 1

        comm_id += cls._steam_id_64_ident
        return comm_id

    @classmethod
    def _sid1_to_sid3(cls, steam_id):
        steam_id_split = steam_id.split(':')
        u_steam_id = ['[U:1:']

        y = int(steam_id_split[1])
        z = int(steam_id_split[2])

        steam_acct = z * 2 + y

        u_steam_id.append(str(steam_acct) + ']')

        return ''.join(u_steam_id)

    @classmethod
    def _sid64_to_sid3(cls, comm_id):
        u_steam_id = ['[U:1:']
        steam_id_acct = int(comm_id) - cls._steam_id_64_ident

        u_steam_id.append(str(steam_id_acct) + ']')

        return ''.join(u_steam_id)

    @classmethod
    def _sid3_to_sid1(cls, u_steam_id):
        u_steam_id = u_steam_id.replace('[', '').replace(']', '')

        u_steam_id_split = u_steam_id.split(':')
        steam_id = ['STEAM_0:']

        z = int(u_steam_id_split[2])

        steam_id.append('0:' if z % 2 == 0 else '1:')
        steam_acct = z // 2
        steam_id.append(str(steam_acct))

        return ''.join(steam_id)

    @classmethod
    def _sid3_to_sid64(cls, u_steam_id):
        u_steam_id = u_steam_id.replace('[', '').replace(']', '')

        u_steam_id_split = u_steam_id.split(':')
        comm_id = int(u_steam_id_split[-1]) + cls._steam_id_64_ident

        return comm_id

    def get_profile_url(self) -> str:
        return f"https://steamcommunity.com/profiles/{self.steam_id_64}"

    def __init__(self, steam_id: str | int) -> None:
        """
        A wrapper and converter for a steam ID.

        :param steam_id: A steam id of any format (SID1/'steamid', SID3/'usteamid', SID64/'commid')
        """
        if isinstance(steam_id, int):
            self.steam_id_64 = steam_id
            self.steam_id_1 = self._sid64_to_sid1(steam_id)
            self.steam_id_3 = self._sid64_to_sid3(steam_id)
        else:
            if steam_id.startswith("STEAM_0:"):
                self.steam_id_64 = self._sid1_to_sid64(steam_id)
                self.steam_id_1 = steam_id
                self.steam_id_3 = self._sid1_to_sid3(steam_id)
            else:
                self.steam_id_64 = self._sid3_to_sid64(steam_id)
                self.steam_id_1 = self._sid3_to_sid1(steam_id)
                self.steam_id_3 = steam_id

    def __repr__(self) -> str:
        return f"{self.steam_id_3} ({self.get_profile_url()})"

    def __str__(self):
        return self.__repr__()


class PlayerEphemeralConsts:
    arr_idx_name: int = None  # I.e. "002"
    m_iUserID: int = None  # I.e. 2
    m_iUserID_identifier: int = None  # a var ident for this particular arr_idx_name'd element of the parent DT
    m_iAccountID: int = None  # I.e. 111216987 (i.e. [U:1:111216987] = sid3)
    m_iAccountID_identifier: int = None  # a var ident for this particular arr_idx_name'd element of the parent DT

    def __init__(self, arr_idx: str) -> None:
        self.arr_idx_name = int(arr_idx.strip())

    def __str__(self):
        return self.__repr__()

    def __repr__(self) -> str:
        _ain = self.arr_idx_name
        _uid = self.m_iUserID if self.m_iUserID else 'null'
        _aid = self.m_iAccountID if self.m_iAccountID else 'null'

        return f'{{"arr_idx_name":{_ain},"m_iUserID":{_uid},' \
               f'"m_iUserID_identifier":{self.m_iUserID_identifier},"m_iAccountID":{_aid},' \
               f'"m_iAccountID_identifier":{self.m_iAccountID_identifier}}}'


class PlayerEphemeralConstsCollection:
    players: dict[int, PlayerEphemeralConsts] = None

    def __init__(self):
        if self.players is None:
            self.players = {}

    def add_player(self, player: PlayerEphemeralConsts) -> None:
        if player.arr_idx_name in self.players:
            logger.warning(f"player of pattern [U:1:{player.m_iAccountID}] ({player.arr_idx_name}/{player.m_iUserID}) "
                           f"already exists, ignoring.")
            return
        self.players[player.arr_idx_name] = player

    def add_to_player(self, idx, *, account_id=None, user_id=None, account_id_ident=None, user_id_ident=None) -> None:
        _player = self.players[idx]
        _player.m_iAccountID = account_id if account_id is not None else _player.m_iAccountID
        _player.m_iUserID = user_id if user_id is not None else _player.m_iUserID
        _player.m_iAccountID_identifier = account_id_ident if account_id_ident is not None \
            else _player.m_iAccountID_identifier
        _player.m_iUserID_identifier = user_id_ident if user_id_ident is not None else _player.m_iUserID_identifier

    def get_player_by_idx(self, entity_idx: int) -> PlayerEphemeralConsts | None:
        if entity_idx not in self.players:
            logger.error(f"Player of entity id '{entity_idx}' not found in players.")
            return None
        return self.players[entity_idx]


class ServerClass(dict):
    server_class: int = None  # server class id, i.e. 247
    name: str = None  # server class name, i.e. CBaseTempEntity
    relevant_dt: str = None  # server class associated data table, i.e. DT_BaseTempEntity

    def __init__(self, server_class: int, name: str, dt: str) -> None:
        self.server_class = server_class
        self.name = name
        self.relevant_dt = dt
        super().__init__(
            server_class=self.server_class,
            name=self.name,
            relevant_dt=self.relevant_dt,
        )

    def is_name(self, name: str) -> bool:
        return name == self.name


class ServerClasses(metaclass=Singleton):
    classes: dict[int, ServerClass] = None

    def __init__(self):
        if self.classes is None:
            self.classes = {}

    def add_class(self, server_class: ServerClass) -> None:
        self.classes[server_class.server_class] = server_class

    def is_id_named(self, class_id: int, class_name: str | Enum) -> bool:
        if isinstance(class_name, Enum):
            class_name = class_name.value
        return self.classes[class_id].is_name(class_name)


class PropChangeMarker(dict):
    identifier: int = None
    name: str = None
    parent: str = None
    value: Any = None
    type: str = None
    index: int = None

    @staticmethod
    def _load_name_mapping(*, file_name: str = 'name_mapping.json') -> dict:
        with open(file_name, 'r') as h:
            data = json.load(h)

        return data

    def __init__(self, table: dict, mapping: dict) -> None:
        self.identifier = int(table['identifier'])
        self.value = table['value']
        self.index = table['index']

        if mapping is None:
            logger.error(f"Please provide a fast-inverse name mapping.")
            return

        _elem = mapping[self.identifier]
        self.parent = _elem['parent']
        self.name = _elem['name']
        self.type = _elem['type']
        dict.__init__(self,
                      identifier=self.identifier,
                      parent=self.parent,
                      name=self.name,
                      type=self.type,
                      value=self.value,
                      index=self.index,
                      )

    def __repr__(self) -> str:
        return f"{self.parent}.{self.name}: {self.type} = {self.value}"