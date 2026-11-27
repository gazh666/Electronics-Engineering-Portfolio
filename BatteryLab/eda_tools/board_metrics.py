"""PCB 工程指标提取（需要本机 KiCad Python 绑定 pcbnew）。

本模块在 import 时不导入 pcbnew；只有真正调用时才导入，
因此在没有 KiCad 的 kaifa_battery 环境中也能被测试导入。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path


def pcbnew_available() -> bool:
    try:
        import pcbnew  # noqa: F401
    except Exception:
        return False
    return True


def extract_board_metrics(board_path: str | Path) -> dict:
    import pcbnew  # 延迟导入，避免无 KiCad 环境时 import 失败

    board = pcbnew.LoadBoard(str(board_path))

    footprints = list(board.GetFootprints())
    tracks = list(board.GetTracks())

    vias = [item for item in tracks if isinstance(item, pcbnew.PCB_VIA)]
    routed_tracks = [item for item in tracks if not isinstance(item, pcbnew.PCB_VIA)]

    track_length_mm = sum(pcbnew.ToMM(item.GetLength()) for item in routed_tracks)

    bounding_box = board.GetBoardEdgesBoundingBox()
    width_mm = pcbnew.ToMM(bounding_box.GetWidth())
    height_mm = pcbnew.ToMM(bounding_box.GetHeight())

    track_widths = Counter(round(pcbnew.ToMM(item.GetWidth()), 4) for item in routed_tracks)

    return {
        "footprint_count": len(footprints),
        "copper_layer_count": board.GetCopperLayerCount(),
        "bounding_width_mm": width_mm,
        "bounding_height_mm": height_mm,
        "bounding_rectangle_area_mm2": width_mm * height_mm,
        "track_segment_count": len(routed_tracks),
        "via_count": len(vias),
        "total_track_length_mm": track_length_mm,
        "track_width_distribution": dict(track_widths),
        "notes": [
            "封装数量不等于 BOM 器件数量（含安装孔/测试点/端子）",
            "外接矩形面积不等于任意形状 PCB 的真实几何面积",
            "未连接网络数量必须来自真实 DRC 报告，不能由本函数推断",
        ],
    }
