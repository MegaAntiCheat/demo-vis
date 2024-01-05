import json

from loguru import logger
from pathlib import Path
from tqdm import tqdm

from src.pivot.dtypes import ServerClasses, PlayerEphemeralConstsCollection, ServerClass, PlayerEphemeralConsts, PropChangeMarker

CACHE_DIR: Path = Path('data/.cache')
DATA_DIR: Path = Path('data')


class Sequencer:
    """
    Sequencer is the early exploratory class for extracting info, otherwise known as 'v1'.

    The `ExtractorV2` class in `v2.py` is supersedes this class, and is only kept for legacy reasons.
    """
    _file: Path = None
    _raw: dict = None

    _ident_name_mapping: dict = None
    _fast_inverse_name_mapping: dict = None

    _property_changes_by_delta: dict = None

    classes: ServerClasses = None
    player_consts: PlayerEphemeralConstsCollection = None

    def __init__(self, file: Path) -> None:
        self._file = file
        with open(self._file, 'r') as h:
            _interim = json.load(h)
        if type(_interim) is dict:
            self._raw = _interim
        else:
            self._raw = {'data': _interim}

        self.classes = ServerClasses()
        self.player_consts = PlayerEphemeralConstsCollection()

    def get_raw(self) -> dict:
        return self._raw

    def get_fast_inverse_name_mapping(self) -> dict:
        if self._fast_inverse_name_mapping is None:
            if self._ident_name_mapping is None:
                self.extract_named_identifiers()
            self.generate_fast_inverse_name_mapping()
        return self._fast_inverse_name_mapping

    def extract_named_identifiers(self) -> None:
        _ident_to_name: dict = {}

        logger.info(f"Extracting named identifier pairs...")
        for elem in tqdm(self._raw['data']):
            # elem = dict, dict_keys anyOf ['type', 'tick', 'messages', 'meta', 'tables', 'server_classes', 'command']
            # type = str, anyOf ['Signon', 'DataTables', 'SyncTick', 'StringTables', 'ConsoleCmd', 'Message']
            if 'type' in elem:
                if elem['type'] == 'DataTables':
                    # A DataTables object always has a 'tables' list
                    for table in elem['tables']:
                        _ident_to_name[table['name']] = []
                        for prop in table['props']:
                            _kv = {int(prop['identifier']): (prop['name'], prop['prop_type'])}
                            _ident_to_name[table['name']].append(_kv)

                    if 'server_classes' in elem:
                        for server_class in elem['server_classes']:
                            # server_class like:
                            # {
                            #   "data_table": "DT_AI_BaseNPC",
                            #   "id": 0,
                            #   "name": "CAI_BaseNPC"
                            # },
                            _class = ServerClass(
                                server_class=server_class['id'],
                                name=server_class['name'],
                                dt=server_class['data_table']
                            )
                            self.classes.add_class(_class)

        self._ident_name_mapping = _ident_to_name

    def map_ident_value_changes_to_name_times(self) -> None:
        _prop_changes = {}

        logger.info(f"Extracting time-delta value changes...")
        for elem in tqdm(self._raw['data']):
            if 'messages' in elem:
                for message in elem['messages']:
                    if 'base_line' in message:
                        delta = message['delta']
                        _prop_changes[delta] = []
                        for entity in message['entities']:
                            if 'props' not in entity:
                                continue
                            for prop in entity['props']:
                                _prop_inst = PropChangeMarker(prop, mapping=self._fast_inverse_name_mapping)
                                _prop_changes[delta].append(_prop_inst)

        self._property_changes_by_delta = _prop_changes

    def generate_fast_inverse_name_mapping(self) -> None:
        _finm = {}
        logger.info(f"Generating fast inverse lookup map...")
        for parent in tqdm(self._ident_name_mapping.keys()):
            for ident_ in self._ident_name_mapping[parent]:
                for ident in ident_.keys():
                    _finm[ident] = {'name': ident_[ident][0], 'parent': parent, 'type': ident_[ident][1]}

        self._fast_inverse_name_mapping = _finm

    def generate_player_ephemeral_consts_mapping(self) -> None:
        if self._ident_name_mapping is None:
            logger.error(f"Please construct a name mapping first by calling this.extract_named_identifiers()")
            return
        if self._property_changes_by_delta is None:
            logger.error(f"Please construct a prop change by tick delta first by calling "
                         f"this.map_ident_value_changes_to_name_times() (make sure you call "
                         f"this.generate_fast_inverse_name_mapping() first)")
            return

        for account_mapping in self._ident_name_mapping['m_iAccountID']:
            # account_mapping: dict[str, list[str, str]]
            _player_inst = PlayerEphemeralConsts(list(account_mapping.values())[0][0])
            _player_inst.m_iAccountID_identifier = next(iter(account_mapping))
            self.player_consts.add_player(_player_inst)

        for account_mapping in self._ident_name_mapping['m_iUserID']:
            self.player_consts.add_to_player(int(list(account_mapping.values())[0][0]),
                                             user_id_ident=next(iter(account_mapping)))

        for delta in self._property_changes_by_delta:
            changes = self._property_changes_by_delta[delta]
            for change in changes:
                if change['parent'] == 'm_iAccountID' or change['parent'] == 'm_iUserID':
                    _player = self.player_consts.players[int(change['name'])]
                    _player.m_iAccountID = change['value'] if change['identifier'] == _player.m_iAccountID_identifier \
                        and _player.m_iAccountID is None else _player.m_iAccountID
                    _player.m_iUserID = change['value'] if change['identifier'] == _player.m_iUserID_identifier \
                        and _player.m_iUserID is None else _player.m_iUserID

    def write_name_mapping(self, path: Path) -> None:
        with open(path, 'w') as h:
            h.write(json.dumps(self._ident_name_mapping))

    def write_dt_names(self, path: Path) -> None:
        _dts = list(self._ident_name_mapping.keys())
        with open(path, 'w') as h:
            h.write(json.dumps(_dts, indent=2))

    def write_prop_changes(self, path: Path) -> None:
        with open(path, 'w') as h:
            h.write(json.dumps(self._property_changes_by_delta, indent=2))

    def write_player_ids(self, path: Path) -> None:
        _players = self.player_consts.players
        _players_json = [_players[x].__dict__ for x in _players]
        with open(path, 'w') as h:
            h.write(json.dumps(_players_json, indent=2))


def generate_cache(demo_file: Path) -> None:
    """

    Generates 4 cache files:
    - name_identifier_association.json
    - list_of_all_datatables.json
    - property_changes_by_time.json
    - player_identities.json

    :param demo_file:
    :return:
    """
    _inst = Sequencer(demo_file)
    _inst.extract_named_identifiers()
    _inst.generate_fast_inverse_name_mapping()
    _inst.write_name_mapping(CACHE_DIR.joinpath('/name_identifier_association.json'))
    _inst.write_dt_names(CACHE_DIR.joinpath('/list_of_all_datatables.json'))
    _inst.map_ident_value_changes_to_name_times()
    _inst.write_prop_changes(CACHE_DIR.joinpath('/property_changes_by_time.json'))
    _inst.generate_player_ephemeral_consts_mapping()
    _inst.write_player_ids(CACHE_DIR.joinpath('/player_identities.json'))
