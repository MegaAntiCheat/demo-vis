from enum import Enum
from typing import Self


class Class(Enum):
    Other: int = 0
    Scout: int = 1
    Sniper: int = 2
    Soldier: int = 3
    Demoman: int = 4
    Medic: int = 5
    Heavy: int = 6
    Pyro: int = 7
    Spy: int = 8
    Engineer: int = 9

    @classmethod
    def from_str(cls, pc_str: str) -> Self:
        _input = pc_str.lower().strip()
        match _input:
            case 'scout':
                return Class.Scout
            case 'soldier':
                return Class.Soldier
            case 'pyro':
                return Class.Pyro
            case 'demoman':
                return Class.Demoman
            case 'medic':
                return Class.Medic
            case 'sniper':
                return Class.Sniper
            case 'heavy':
                return Class.Heavy
            case 'engineer':
                return Class.Engineer
            case 'spy':
                return Class.Spy
            case _:
                return Class.Other


class Team(Enum):
    Other: int = 0
    Spectator: int = 1
    Red: int = 2
    Blue: int = 3

    @classmethod
    def from_str(cls, pt_str: str) -> Self:
        _input = pt_str.lower().strip()
        match _input:
            case 'blue':
                return Team.Blue
            case 'red':
                return Team.Red
            case 'spectator':
                return Team.Spectator
            case _:
                return Team.Other

    def to_str_lower(self) -> str:
        match self.value:
            case 1:
                return 'spectator'
            case 2:
                return 'red'
            case 3:
                return 'blue'
            case _:
                return 'other'



class PlayerInfo:
    classes: list[Class] = None
    name: str = None
    user_id: int = None
    steam_id: str = None
    team: Team = None

    @classmethod
    def from_msgpack_list(cls, msgpack_list: list) -> Self:
        _inst = PlayerInfo()
        _, _n, _uid, _sid, _t = msgpack_list
        _inst.name = _n
        _inst.user_id = _uid
        _inst.steam_id = _sid
        _inst.team = _t
        _inst.classes = []
        return _inst


class PlayerState(Enum):
    Alive: int = 0
    Dying: int = 1
    Death: int = 2
    Respawnable: int = 3

    @classmethod
    def from_str(cls, ps_str: str) -> Self:
        _input = ps_str.lower().strip()
        match _input:
            case 'alive':
                return PlayerState.Alive
            case 'dying':
                return PlayerState.Dying
            case 'death':
                return PlayerState.Death
            case 'respawnable':
                return PlayerState.Respawnable
            case _:
                return PlayerState.Alive


class Player:
    """
    A Player representation - this is primatively how the tf_demo_parser Rust package see's players, so we re-represent
    here in Python.
    """
    name: str = None
    tick: int = None
    # from gsd
    ent_id: int = None
    position: list[float] = None
    health: int = None
    max_health: int = None
    pclass: Class = None
    team: Team = None
    view_angle: float = None
    pitch_angle: float = None
    state: PlayerState = None
    info: PlayerInfo = None
    charge: int = None
    simtime: int = None
    ping: int = None
    in_pvs: int = None

    def __init__(self, tick: int) -> None:
        self.tick = tick

    def _process_name(self) -> None:
        """
        Extracts the name from the info object and puts a reference to it in this object.

        Will throw an AssertionError if the info object or the encapsulated name object is None, or if this object
        already has a defined name.
        :return: None
        """
        assert self.info is not None and self.info.name is not None
        try:
            assert self.name is None
        except AssertionError as e:
            raise Exception(f"This Player object already has a defined name of '{self.name}'! {e}")
        self.name = self.info.name

    @classmethod
    def from_msgpack_list(cls, msgpack_list: list, tick_num: int) -> Self:
        """
        Player: Entity ID, Position (VectorXYZ), Health, Max Health, class, team, view angle, pitch angle, state, info,
                charge, simtime, ping, in_pvs

        An unpacked list from the msgpack encoding might look like:

        [8, [1407.81982421875, -5854.81591796875, -63.96875], 125, 125, 'sniper', 'blue', 81.29032135009766,
         -2.4705886840820312, 'Alive', [{}, 'Lilith', 368, '[U:1:111216987]', 'other'], 0, 82, 21, True]

        :param msgpack_list: The list object of a single player extracted from stream unpacking a single element out of
                             the GameStateDelta msgpack file and iterating the top level list
        :param tick_num: The current tick number - i.e. at what tick in the demo did this GameState occur
        :return: A Player object representing the player data from the given msgpack
        """
        _ent_id, _pos, _hp, _mhp, _c, _t, _va, _pa, _s, _i, _ct, _st, _p, _pvs = msgpack_list
        _inst = Player(tick_num)
        _inst.ent_id = _ent_id
        _inst.position = _pos
        _inst.health = _hp
        _inst.max_health = _mhp
        _inst.pclass = Class.from_str(_c)
        _inst.team = Team.from_str(_t)
        _inst.view_angle = _va
        _inst.pitch_angle = _pa
        _inst.state = PlayerState.from_str(_s)
        _inst.info = PlayerInfo.from_msgpack_list(_i)
        _inst.charge = _ct
        _inst.simtime = _st
        _inst.ping = _p
        _inst.in_pvs = _pvs
        _inst._process_name()
        return _inst
