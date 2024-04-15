import msgpack
from typing import cast, BinaryIO
from pathlib import Path
# from src.gsd.player import Player


def unpack_generator(pack_file: Path) -> tuple[msgpack.Unpacker, BinaryIO]:
    _file_handle = open(pack_file, 'rb')
    unpacker = msgpack.Unpacker(_file_handle, raw=False, strict_map_key=False)
    return unpacker, _file_handle

    # with open(pack_file, 'rb') as h:
    #
    #     for idx, unpacked in enumerate(unpacker):
    #         if idx == 0:
    #             continue
    #         _unpacked_players: list = cast(list, unpacked[0])
    #         _tick: int = unpacked[1]
    #
    #         for unpacked_player in _unpacked_players:
    #             _player_obj = Player.from_msgpack_list(unpacked_player, _tick)
