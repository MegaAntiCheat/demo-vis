import json

import matplotlib.pyplot as plt
import matplotlib.animation as animation

from typing import Any
from enum import Enum
from pathlib import Path
from loguru import logger
from tqdm import tqdm
from src.pivot.v2 import ExtractorV2


class PlaybackConsts(Enum):
    PLAYBACK_TICKRATE_NORMAL: int = 66
    PLAYBACK_TICKRATE_10X: int = 660
    PLAYBACK_TICKRATE_20X: int = 1320
    PLAYBACK_TICKRATE_100X: int = 6600


class PlayerMovement:
    # SteamID64
    target_player: str = None
    time_series: dict[str, dict[str, dict[str, Any]]]
    # Warning, this array may be 10s to hundreds of thousands of elements long
    positions_by_tick: list[tuple[float, float, float] | None] = None
    every_other_player: dict[str, list[tuple[float, float, float] | None]] = None
    # For visualisations
    _last_xyz: tuple[float, float, float] = None
    _fig: plt.Figure = None
    _point: plt.Line2D = None
    _other_points: dict[str, plt.Line2D] = None
    _range_x: tuple[float, float] = None
    _range_y: tuple[float, float] = None
    _range_z: tuple[float, float] = None

    def _update_ranges(self, pos_tuple: tuple[float, float, float]) -> None:
        # Update X range
        if pos_tuple[0] > self._range_x[1]:
            self._range_x = (self._range_x[0], pos_tuple[0])
        elif pos_tuple[0] < self._range_x[0]:
            self._range_x = (pos_tuple[0], self._range_x[1])
        # Update Y Range
        if pos_tuple[1] > self._range_y[1]:
            self._range_y = (self._range_y[0], pos_tuple[1])
        elif pos_tuple[1] < self._range_y[0]:
            self._range_y = (pos_tuple[1], self._range_y[1])
        # Update Z Range
        if pos_tuple[2] > self._range_z[1]:
            self._range_z = (self._range_z[0], pos_tuple[2])
        elif pos_tuple[2] < self._range_z[0]:
            self._range_z = (pos_tuple[2], self._range_z[1])

    def __init__(
            self,
            target_player: str,  # SteamID64 of the target player
            time_series: dict[str, dict[str, dict[str, Any]]]
    ) -> None:
        self.time_series = time_series
        self.target_player = target_player
        self.positions_by_tick = []
        self.every_other_player = {}
        self._other_points = {}
        self._last_xyz = (.0, .0, .0)

        self._range_x = (.0, .0)
        self._range_z = (.0, .0)
        self._range_y = (.0, .0)

        player: str
        for player in self.time_series["0"]:
            if player != self.target_player:
                self.every_other_player[player] = []

        _current_idx: int = 0
        tick_num: str
        for tick_num in tqdm(self.time_series):
            _players: dict[str, dict[str, Any]] = self.time_series[tick_num]
            _target = _players.get(self.target_player)

            other: str
            for other in self.every_other_player:
                _other = _players.get(other)
                if _other is None:
                    self.every_other_player[other].append((-1000.0, -1000.0, -1000.0))
                else:
                    if 'DT_TFLocalPlayerExclusive' in _other:
                        if 'm_vecOrigin' in _other['DT_TFLocalPlayerExclusive']:
                            _pos_dict = _other['DT_TFLocalPlayerExclusive']['m_vecOrigin']
                            if 'z' in _pos_dict:
                                _z = _pos_dict['z']
                            else:
                                _z: float | None = None
                                for elem in self.every_other_player[other][::-1]:
                                    if elem is not None:
                                        _z = elem[2]
                                        break
                                if _z is None:
                                    _z = .0
                            _pos_tuple = (_pos_dict['x'], _pos_dict['y'], _z)
                            self.every_other_player[other].append(_pos_tuple)
                            continue
                    self.every_other_player[other].append((-1000.0, -1000.0, -1000.0))

            if _target is not None:
                if 'DT_TFLocalPlayerExclusive' in _target:
                    if 'm_vecOrigin' in _target['DT_TFLocalPlayerExclusive']:
                        _pos_dict = _target['DT_TFLocalPlayerExclusive']['m_vecOrigin']
                        if 'z' in _pos_dict:
                            _z = _pos_dict['z']
                        else:
                            _z: float | None= None
                            for elem in self.positions_by_tick[::-1]:
                                if elem is not None:
                                    _z = elem[2]
                                    break
                            if _z is None:
                                _z = .0
                        _pos_tuple = (_pos_dict['x'], _pos_dict['y'], _z)
                        # logger.debug(f"Player Movement[{tick_num}] -> {_pos_tuple}")
                        self._update_ranges(_pos_tuple)
                        self.positions_by_tick.append(_pos_tuple)
                        continue
                    elif 'm_vecOrigin[2]' in _target['DT_TFLocalPlayerExclusive']:
                        try:
                            _previous_xy = self.positions_by_tick[-1]
                        except IndexError:
                            # No previous position, but only a position update for one axis here?
                            # Assume default and ECC later
                            _previous_xy = (0, 0, 0)
                        _pos_z = _target['DT_TFLocalPlayerExclusive']['m_vecOrigin[2]']
                        self.positions_by_tick.append(
                            (_previous_xy[0], _previous_xy[1], _pos_z)
                        )
                        continue

                try:
                    _prev = self.positions_by_tick[-1]
                    self.positions_by_tick.append(_prev)
                except IndexError:
                    self.positions_by_tick.append(None)
                finally:
                    continue
            else:
                self.positions_by_tick.append(None)

    def _frame(self, frame: int) -> Any:
        _xyz = self.positions_by_tick[frame]
        if _xyz is None:
            _xyz = self._last_xyz
        else:
            self._last_xyz = _xyz
        # if frame % 100 == 0:
        #     logger.debug(f"[VISUALISING] New point: {_xyz}")
        self._point.set_xdata(_xyz[0])
        self._point.set_ydata(_xyz[1])
        for other in self._other_points:
            try:
                _point = self.every_other_player[other][frame]
            except IndexError:
                _point = (-1000.0, -1000.0, -1000.0)
            self._other_points[other].set_xdata(_point[0])
            self._other_points[other].set_ydata(_point[1])

        return self._point

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

        self._fig = plt.figure()
        plt.xlabel('X Coordinate')
        plt.ylabel('Y Coordinate')
        plt.xlim(self._range_x[0], self._range_x[1])
        plt.ylim(self._range_y[0], self._range_y[1])
        self._point = plt.plot(0.0, 0.0, 'ro', label=f'{self.target_player} XY position')[0]
        for other in self.every_other_player:
            self._other_points[other] = plt.plot(-1000.0, -1000.0, 'go')[0]

        plt.legend()

        ani = animation.FuncAnimation(
            fig=self._fig,
            func=self._frame,
            frames=len(self.positions_by_tick),
            interval=1000/playback_rate
        )
        plt.show()


def test_movement():
    logger.info("[V2][VIS] Loading json...")
    # _v2 = ExtractorV2(Path("data/noadd-demo_trace.json").read_text('utf8'))
    with open('data/test_v2_big_all.json', 'r') as h:
        _changes = json.load(h)

    logger.info("[V2][VIS] Generating movement series...")
    _player = PlayerMovement("76561198071482715", _changes)
    logger.info("[V2][VIS] Visualising...")
    _player.visualise(PlaybackConsts.PLAYBACK_TICKRATE_100X.value)
