import json
import orjson

from src.pivot.dtypes import ServerClasses, PlayerEphemeralConsts, UsefulServerClasses, SteamID, \
    UsefulDataTables, ServerClass
from pathlib import Path
from loguru import logger
from copy import deepcopy


class DataCollectorV2:
    """
    DataCollectorV2 is the cleaner implementation of several functions inside the older `Sequencer` class.
    The purpose of this class to collect information mapped in the demo so we can use it later for translating
    things like identifier constants, server_class numbers, and datatable references.
    """
    demo_json_raw: dict = None
    server_classes: ServerClasses = None
    data_tables: list[str] = None
    mapped_identifiers: dict[int, dict[str, str | int]] = None
    # How to use this type:
    # for each slot id (001, 002, ..., 099, 100), there will be a dict of tick numbers to PlayerEphemeralConsts objects
    slot_details_by_tick_range: dict[int, dict[int, PlayerEphemeralConsts]] = None

    def __init__(self, demo_json: dict | str | bytes) -> None:
        """

        :param demo_json: can be a string or bytes read directly from a json file, and will be converted using `orjson`,
                          or can be an already deserialized python dictionary.
        """
        self.demo_json_raw = orjson.loads(demo_json) if isinstance(demo_json, str) else demo_json
        self.server_classes = ServerClasses()
        self.mapped_identifiers = {}
        self.data_tables = []
        self.slot_details_by_tick_range = {}
        self._extract_identifier_names()
        self._get_mapped_accounts_by_time_period()

    def get_player_consts(self, entity_idx: int, current_tick: int) -> PlayerEphemeralConsts | None:
        _greatest_smaller = None
        for tick in self.slot_details_by_tick_range[entity_idx]:
            if tick <= current_tick:
                _greatest_smaller = tick
            else:
                break
        if _greatest_smaller is not None:
            return self.slot_details_by_tick_range[entity_idx][_greatest_smaller]
        else:
            return None

    def _extract_identifier_names(self) -> None:
        logger.info("[V2] Extracting identifier names and relationships...")
        for packet in self.demo_json_raw:
            if packet['type'] != 'DataTables':
                continue

            for table in packet['tables']:
                self.data_tables.append(table['name'])
                for prop in table['props']:
                    _kv = {
                        int(prop['identifier']): {
                            'name': prop['name'],
                            'parent': table['name'],
                            'type': prop['prop_type']
                        }
                    }
                    self.mapped_identifiers |= _kv

            if 'server_classes' in packet:
                for sc in packet['server_classes']:
                    # server_class like:
                    # {
                    #   "data_table": "DT_AI_BaseNPC",
                    #   "id": 0,
                    #   "name": "CAI_BaseNPC"
                    # },
                    _class = ServerClass(
                        server_class=sc['id'],
                        name=sc['name'],
                        dt=sc['data_table']
                    )
                    self.server_classes.add_class(_class)

    def _get_mapped_accounts_by_time_period(self) -> None:
        logger.info("[V2] Extracting account details and life-times...")
        _slots = {}
        _account_ident_to_slot_id = {}
        _user_ident_to_slot_id = {}
        # Extract the identifiers that map each of the slot names ("001", "002", ..., "099", "100")
        # to their m_iAccountID and m_iUserID variables
        logger.debug("[V2] Extracting identifiers...")
        for packet in self.demo_json_raw:
            if packet['type'] != 'DataTables':
                continue

            for table in packet['tables']:
                if table['name'] == 'm_iAccountID':
                    for prop in table['props']:
                        if prop['name'] not in _slots:
                            _slots[int(prop['name'])] = PlayerEphemeralConsts(prop['name'])
                        _slots[int(prop['name'])].m_iAccountID_identifier = int(prop['identifier'])

                elif table['name'] == 'm_iUserID':
                    for prop in table['props']:
                        if int(prop['name']) not in _slots:
                            _slots[int(prop['name'])] = PlayerEphemeralConsts(prop['name'])
                        _slots[int(prop['name'])].m_iUserID_identifier = int(prop['identifier'])
        # pivot on the slots data to create an efficient lookups for mapping identifier numbers to potential slot
        # ids. The keys will be the m_iUserID identifier or the m_iAccountID identifier (depending on var),
        # and the value will be the slot id that maps to (for grabbing the PlayerEphemeralConsts object from _slots)
        for slot_id in _slots:
            # May as well initialise the dicts for later while we are here
            self.slot_details_by_tick_range[slot_id] = {}
            _slot = _slots[slot_id]
            _account_ident_to_slot_id[_slot.m_iAccountID_identifier] = slot_id
            _user_ident_to_slot_id[_slot.m_iUserID_identifier] = slot_id

        # Changes to m_iUserID and m_iAccountID (i.e. if a player leaves or joins during the demo) would
        # get mapped by prop changes indicated in PacketEntities message for the 'CTFPlayerResource' server
        # class, in testing mapped to id 249, and associated with the 'DT_TFPlayerResource' data table
        #
        # Assumptions:
        #   Every time there is a change mapped to m_iUserID, there will be a corresponding change to m_iAccountID in
        #   the same packet/tick.
        logger.debug("[V2] Extracting values by time dependency...")
        for packet in self.demo_json_raw:
            if packet['type'] != "Message":
                continue

            # I'm sorry for this, dear god.
            tick_num = int(packet['tick'])
            for message in packet['messages']:
                if message['type'] != 'PacketEntities':
                    continue

                for entity in message['entities']:
                    if not self.server_classes.is_id_named(
                            entity['server_class'],
                            UsefulServerClasses.PlayerResource
                    ):
                        continue

                    for prop in entity['props']:
                        _slot_id = None
                        _account = False
                        # Attempt to match the identifier in this prop to any of the known user or account idents
                        if int(prop['identifier']) in _account_ident_to_slot_id:
                            _slot_id = _account_ident_to_slot_id[int(prop['identifier'])]
                            _account = True
                        elif int(prop['identifier']) in _user_ident_to_slot_id:
                            _slot_id = _user_ident_to_slot_id[int(prop['identifier'])]

                        # if no match, continue to next prop
                        if _slot_id is None:
                            continue

                        # we have a userID or accountID property match
                        # check if we have previously copied a PlayerEphemeralConsts object for this tick, else
                        # create one by deepcopying the base
                        if tick_num in self.slot_details_by_tick_range[_slot_id]:
                            _details_base = self.slot_details_by_tick_range[_slot_id][tick_num]
                        else:
                            _details_base = deepcopy(_slots[_slot_id])

                        # If we found our identifier match when looking in the accountID mappings, ...
                        # Else it must be a userID match
                        if _account:
                            _details_base.m_iAccountID = int(prop['value'])
                        else:
                            _details_base.m_iUserID = int(prop['value'])

                        self.slot_details_by_tick_range[_slot_id][tick_num] = _details_base


class ExtractorV2:
    """
    ExtractorV2 is the 'new and improved' extraction multitool for demo jsons.

    Who is jason? what is he demoing?
    """
    player_details: dict[int, dict[int, PlayerEphemeralConsts]] = None
    data_collection: DataCollectorV2 = None

    _relevant_dts: list[str] = None
    _player_prop_changes: dict[int, dict[str | SteamID, dict]]

    def _analyse_packet_entities(self, tick_num: int, message: dict) -> None:
        """
        The message format we are expecting here is like so:
        {
            'type': 'Message',
            'tick': <some integer>,
            'messages': [
                {
                    'type': 'PacketEntities',
                    'entities': [
                        {
                            'entity_index': <some integer>,
                            'props': [
                                'identifier': <some integer>,
                                'value': <some value, int, float or str>,
                                'index': <some integer>
                            ]
                        },
                        ...
                    ]
                },
                ...
            ]
        }

        :param tick_num: the tick_num from the outer message object
        :param message: the demo 'message' type packet
        :return: None
        """
        for entity in message['entities']:
            if not self.data_collection.server_classes.is_id_named(entity['server_class'], UsefulServerClasses.Player):
                continue

            entity_idx = entity['entity_index']
            player = self.data_collection.get_player_consts(entity_idx, tick_num)
            if player is None:
                print(self.data_collection.slot_details_by_tick_range)
                print(f"Tick: {tick_num}, for entity_idx: {entity_idx}")

            if player.m_iAccountID is None or player.m_iAccountID <= 256:
                # BOT players in game will have steam ids ranging from 1 to 100
                # We don't care about their info, so skip to next entity, which may be a real
                # player again
                continue

            # if not a BOT player, m_iAccountID values are always the variable component of a SteamID3.
            steam_id = SteamID(f"[U:1:{player.m_iAccountID}]")

            changes = {}
            for prop in entity['props']:
                try:
                    # Expected outcome of the named identifiers' dictionary:
                    # var = {'name': <name>, 'parent': <parent name>, 'type': <some type>}
                    var = self.data_collection.mapped_identifiers[int(prop['identifier'])]
                    if var['parent'] not in self._relevant_dts:
                        continue
                    if var['parent'] not in changes:
                        changes[var['parent']] = {}

                    # Correction for dealing with Valve's increasingly confusing mixed use of Vector
                    # types and float arrays. In this case, the demo would demonstrate an XY vector with changes
                    # then document the Z change as changing the 2-indexed item of a float array.
                    #
                    # i.e.
                    # m_vecOrigin: {
                    #       'x': <some value>,
                    #       'y': <some other value>
                    # },
                    # m_vecOrigin[2]: <some other other value>
                    #
                    # This is simply to merge it all into one vector
                    _zVec = str(var['name'])
                    if _zVec.endswith("[2]") and _zVec.split("[")[0] in changes[var['parent']]:
                        changes[var['parent']][_zVec.split("[")[0]]['z'] = prop['value']
                    else:
                        changes[var['parent']][var['name']] = prop['value']
                except KeyError:
                    logger.error(f"Unknown or unseen identifier '{prop['identifier']}', skipping...")
                    continue

            self._player_prop_changes[tick_num][str(steam_id)] = changes

    def _extract_packets(self) -> None:
        for packet in self.demo_json_raw:
            if packet['type'] != "Message":
                continue

            tick_num = int(packet['tick'])
            self._player_prop_changes[tick_num] = {}
            # Maybe we would like to include this in the dump at some point.
            local_player = packet['meta']['view_angles']

            for message in packet['messages']:
                # Analyse 'PacketEntities' message type
                # All functions called within this loop are state side-affecting,
                # and will return nothing.
                if message['type'] == 'PacketEntities':
                    self._analyse_packet_entities(tick_num, message)

    def __init__(
            self,
            demo_json: dict | str | bytes
    ) -> None:
        self.data_collection = DataCollectorV2(demo_json)
        self.demo_json_raw = self.data_collection.demo_json_raw
        self._player_prop_changes = {}
        self._relevant_dts = [x.value for x in UsefulDataTables]

        self._extract_packets()

    def get_changes(self) -> dict:
        return self._player_prop_changes


def test_v2():
    from .extractors import Sequencer
    # _inst = Sequencer(Path("data/demo_trace_2.json"))
    # _inst.extract_named_identifiers()
    # _inst.generate_fast_inverse_name_mapping()
    # _inst.map_ident_value_changes_to_name_times()
    # _inst.generate_player_ephemeral_consts_mapping()

    # print(_inst.get_fast_inverse_name_mapping())
    _v2 = ExtractorV2(Path("data/demo_trace_2.json").read_text('utf8'))
    _changes = _v2.get_changes()

    with open('data/test_v2_2.json', 'w') as h:
        h.write(json.dumps(_changes, indent=2))