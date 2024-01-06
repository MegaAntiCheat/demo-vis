import json
import orjson

from src.pivot.dtypes import ServerClasses, PlayerEphemeralConsts, UsefulServerClasses, SteamID, \
    UsefulDataTables, ServerClass
from pathlib import Path
from loguru import logger
from copy import deepcopy
from typing import Any


class DataCollectorV2:
    """
    DataCollectorV2 is the cleaner implementation of several functions inside the older `Sequencer` class.
    The purpose of this class to collect information mapped in the demo, so we can use it later for translating
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
        """
        Get a PlayerEphemeralConsts object referencing a given slot id by searching for a PlayerEphemeralConsts
        most recently constructed before the current tick

        :param entity_idx: the entity idx (as per the PacketEntities/CTFPlayer class packet) aka the slot id
        :param current_tick: the current tick value from the parent packet containing the PacketEntities and CTFPlayer
                             messages
        :return: None if no PlayerEphemeralConsts object for that slot ID exists (yet), or a valid PlayerEphemeralConsts
                 object (may not have an m_iUserID or m_iAccountID, but will have their identifiers mapped)
        """
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
        # Interspersed amongst the demo packets will be a DataTables packet type, which
        # contains detail on all the data tables used or referenced in this demo
        for packet in self.demo_json_raw:
            if packet['type'] != 'DataTables':
                continue

            # The tables list contains data tables, their names and identifiers, and the names
            # and identifiers of all their child elements
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

            # Some DataTables packets will also contain a server_classes definition table,
            # which maps server_class names to an integer ID and their associated DataTable
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
        _slots: dict[int, PlayerEphemeralConsts] = {}
        _account_ident_to_slot_id: dict[int, int] = {}
        _user_ident_to_slot_id: dict[int, int] = {}
        # Extract the identifiers that map each of the slot names ("001", "002", ..., "099", "100")
        # to their m_iAccountID and m_iUserID variables
        logger.debug("[V2] Extracting identifiers...")
        packet: dict[str, Any]
        for packet in self.demo_json_raw:
            if packet['type'] != 'DataTables':
                continue

            table: dict[str, Any]
            for table in packet['tables']:
                if table['name'] == 'm_iAccountID':
                    prop: dict[str, Any]
                    for prop in table['props']:
                        if prop['name'] not in _slots:
                            _slots[int(prop['name'])] = PlayerEphemeralConsts(prop['name'])
                        _slots[int(prop['name'])].m_iAccountID_identifier = int(prop['identifier'])

                elif table['name'] == 'm_iUserID':
                    prop: dict[str, Any]
                    for prop in table['props']:
                        if int(prop['name']) not in _slots:
                            _slots[int(prop['name'])] = PlayerEphemeralConsts(prop['name'])
                        _slots[int(prop['name'])].m_iUserID_identifier = int(prop['identifier'])
        # pivot on the slots data to create an efficient lookups for mapping identifier numbers to potential slot
        # ids. The keys will be the m_iUserID identifier or the m_iAccountID identifier (depending on var),
        # and the value will be the slot id that maps to (for grabbing the PlayerEphemeralConsts object from _slots)
        slot_id: int
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
        packet: dict[str, Any]
        for packet in self.demo_json_raw:
            if packet['type'] != "Message":
                continue

            # I'm sorry for this, dear god.
            # It actually turned out better than expected - iterating big JSON just tends
            # to require multiple nested for loops
            tick_num = int(packet['tick'])
            message: dict[str, Any]
            for message in packet['messages']:
                if message['type'] != 'PacketEntities':
                    continue

                entity: dict[str, Any]
                for entity in message['entities']:
                    if not self.server_classes.is_id_named(
                            entity['server_class'],
                            UsefulServerClasses.PlayerResource
                    ):
                        continue

                    prop: dict[str, Any]
                    for prop in entity['props']:
                        _slot_id: int | None = None
                        _account: bool = False
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
                        # create one by deep copying the base
                        _details_base: PlayerEphemeralConsts
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
    _player_prop_changes: dict[str, dict[str, dict]]

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
        entity: dict[str, Any]
        _cnt = len(message['entities'])
        for entity in message['entities']:
            if not self.data_collection.server_classes.is_id_named(entity['server_class'], UsefulServerClasses.Player):
                continue

            entity_idx: int = entity['entity_index']
            player = self.data_collection.get_player_consts(entity_idx, tick_num)
            if player is None:
                logger.error(f"Player lookup returned None at Tick: {tick_num}, for entity_idx: {entity_idx}")
                continue

            if player.m_iAccountID is None or player.m_iAccountID <= 256:
                # BOT players in game will have steam ids ranging from 1 to 100
                # We don't care about their info, so skip to next entity, which may be a real
                # player again
                continue

            # if not a BOT player, m_iAccountID values are always the variable component of a SteamID3.
            steam_id: SteamID = SteamID(f"[U:1:{player.m_iAccountID}]")

            changes: dict[str, dict[str, Any]] = {}
            prop: dict[str, Any]
            for prop in entity['props']:
                try:
                    # Expected outcome of the named identifiers' dictionary:
                    # var = {'name': <name>, 'parent': <parent name>, 'type': <some type>}
                    var: dict[str, str | int] = self.data_collection.mapped_identifiers[int(prop['identifier'])]
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
                    _zVec: str = str(var['name'])
                    if _zVec.endswith("[2]") and _zVec.split("[")[0] in changes[var['parent']]:
                        changes[var['parent']][_zVec.split("[")[0]]['z'] = prop['value']
                    else:
                        changes[var['parent']][var['name']] = prop['value']
                except KeyError:
                    logger.error(f"Unknown or unseen identifier '{prop['identifier']}', skipping...")
                    continue

            self._player_prop_changes[tick_num][steam_id.steam_id_64] = changes

    def _extract_packets(self) -> None:
        logger.info(f"[V2] Extracting messages and game data...")

        packet: dict[str, Any]
        _cnt = len(self.demo_json_raw)
        for packet in self.demo_json_raw:
            if packet['type'] != "Message":
                continue

            tick_num: int = int(packet['tick'])
            self._player_prop_changes[tick_num] = {}
            # Maybe we would like to include this in the dump at some point.
            local_player: dict = packet['meta']['view_angles']

            message: dict[str, Any]
            for message in packet['messages']:
                # Analyse 'PacketEntities' message type
                # All functions called within this loop are state side-affecting,
                # and will return nothing.
                if message['type'] == 'PacketEntities':
                    self._analyse_packet_entities(tick_num, message)
        logger.success(f"[V2] Processed {_cnt} packets...")

    def __init__(
            self,
            demo_json: dict | str | bytes
    ) -> None:
        """
        Takes a demo json, as either a string, bytes or already converted python dict object,
        and extracts the packets to generate a data_collection object (from DataCollectorV2)
        and a player_prop_changes by tick mapping. Get it with `this.get_changes()`.

        :param demo_json: A python dict, json str or bytes of a json-converted TF2 demo file
        """
        self.data_collection = DataCollectorV2(demo_json)
        self.demo_json_raw = self.data_collection.demo_json_raw
        self._player_prop_changes = {}
        self._relevant_dts = [x.value for x in UsefulDataTables]

        self._extract_packets()

    def get_changes(self) -> dict[str, dict[str, dict]]:
        return self._player_prop_changes


def default_serialisation(obj):
    if isinstance(obj, PlayerEphemeralConsts):
        return obj.get_dict()
    else:
        return str(obj)


def test_v2():
    """
    A small test function for testing V2 capability. won't be in prod

    :return: None, writes file out to hardcoded file path
    """
    logger.info(f"[V2][TEST] Reading demo JSON...")
    _v2 = ExtractorV2(Path("data/noadd-demo_trace.json").read_text('utf8'))
    _changes = _v2.get_changes()
    logger.info(f"[V2][TEST] Writing out data...")

    with open('data/test_v2_big_all.json', 'w') as h:
        h.write(json.dumps(_changes, indent=2))

    with open('data/test_v2_big_players.json', 'w') as h:
        h.write(json.dumps(_v2.data_collection.slot_details_by_tick_range, indent=2, default=default_serialisation))
