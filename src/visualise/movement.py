import json

import matplotlib.pyplot as plt
import matplotlib.animation as animation

from typing import Any, BinaryIO, cast
from enum import Enum
from pathlib import Path

import msgpack
from loguru import logger
from tqdm import tqdm

from src.gsd.player import Player
from src.gsd.load import unpack_generator
from src.pivot.v2 import ExtractorV2


class PlaybackConsts(Enum):
    PLAYBACK_TICKRATE_NORMAL: int = 66
    PLAYBACK_TICKRATE_10X: int = 660
    PLAYBACK_TICKRATE_20X: int = 1320
    PLAYBACK_TICKRATE_100X: int = 6600


class PlayerMovement:
    # SteamID64
    target_player: str = None
    unpacker: msgpack.Unpacker = None
    unpacker_handle: BinaryIO = None
    positions_by_tick: list[list[Player | None]] = None

    # For visualisations
    fig: plt.Figure = None
    ax = None
    _points: list[plt.Line2D] = None

    def __init__(
            self,
            gsd_unpacker: msgpack.Unpacker,
            gsd_file_handle: BinaryIO
    ) -> None:
        self.unpacker = gsd_unpacker
        self.unpacker_handle = gsd_file_handle
        self.positions_by_tick = []

        for idx, unpacked in tqdm(enumerate(self.unpacker)):
            if idx == 0:
                continue
            _unpacked_players: list = cast(list, unpacked[0])
            _tick: int = unpacked[1]

            _players_this_tick: list[Player | None] = [None] * len(_unpacked_players)
            for player_slot, unpacked_player in enumerate(_unpacked_players):
                _player_obj = Player.from_msgpack_list(unpacked_player, _tick)
                _players_this_tick[player_slot] = _player_obj

            self.positions_by_tick.append(_players_this_tick)

    def _frame(self, frame: int) -> Any:
        self.ax.clear()
        _players = self.positions_by_tick[frame]

        for idx, _player in enumerate(_players):
            if _player is None:
                continue
            if _player.position[0] == 0.0 and _player.position[1] == 0.0 and _player.position[2] == 0.0:
                continue
            self.ax.plot(
                _player.position[0],
                _player.position[1],
                _player.position[2],
                color='red' if _player.team.value == 2 else 'blue',
                label=_player.name,
                marker='o'
            )

    def total_non_none_frames(self) -> int:
        _cnt: int = 0
        for pos in self.positions_by_tick:
            if pos is not None:
                _cnt += 1
        return _cnt

    def visualise(self, playback_rate: int) -> None:
        """
        Visualise the XYZ position data of the target player using a plot

        :param playback_rate: Tick rate (in ticks/second) to replay the data at
        :return: None
        """
        logger.info(f"Have {len(self.positions_by_tick)} frames to visualise, "
                    f"for {self.total_non_none_frames()} total valid positions")

        self.fig = plt.figure()

        self.ax = self.fig.add_subplot(projection='3d')
        self.ax.set_xlabel('X Coordinate')
        self.ax.set_ylabel('Y Coordinate')
        self.ax.set_zlabel('Z Coordinate')
        # self.ax.set_xlim(-2000, 2000)
        # self.ax.set_ylim(-2000, 2000)
        # self.ax.set_zlim(-1000, 1000)
        # self.ax.legend()
        self.fig.legend()

        ani = animation.FuncAnimation(
            fig=self.fig,
            func=self._frame,
            frames=len(self.positions_by_tick),
            interval=1,
        )
        plt.show()


def test_movement():
    raise NotImplementedError
    # logger.info("[V2][VIS] Loading json...")
    # # _v2 = ExtractorV2(Path("data/noadd-demo_trace.json").read_text('utf8'))
    # with open('data/test_v2_big_all.json', 'r') as h:
    #     _changes = json.load(h)
    #
    # logger.info("[V2][VIS] Generating movement series...")
    # _player = PlayerMovement("76561198071482715", _changes)
    # logger.info("[V2][VIS] Visualising...")
    # _player.visualise(PlaybackConsts.PLAYBACK_TICKRATE_100X.value)


def test_with_gsd():
    _file = Path('./rs/demo_packet_dumper/output2/jayce_is_very_pretty_2-gsd.msgpack')
    _unpacker, _handle = unpack_generator(_file)
    _inst = PlayerMovement(_unpacker, _handle)
    _inst.visualise(PlaybackConsts.PLAYBACK_TICKRATE_100X.value)


if __name__ == "__main__":
    test_with_gsd()
