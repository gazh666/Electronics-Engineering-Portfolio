"""真实 PCB 布线统计（pcbnew 对象级）。

注意：本模块只统计板卡对象，不能单独证明网络已连接；
连接性以 kicad-cli DRC 的 unconnected_items 为准（见 verify_final_pcb.py）。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pcbnew


def inspect_board(board_path: str | Path) -> dict:
    path = Path(board_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    board = pcbnew.LoadBoard(str(path))
    footprints = list(board.GetFootprints())
    tracks = list(board.GetTracks())
    segments = [t for t in tracks if not isinstance(t, pcbnew.PCB_VIA)]
    vias = [t for t in tracks if isinstance(t, pcbnew.PCB_VIA)]

    per_net_len: dict[str, float] = defaultdict(float)
    per_net_seg: dict[str, int] = defaultdict(int)
    per_layer_seg: dict[str, int] = defaultdict(int)
    for t in segments:
        net = t.GetNetname() or ""
        per_net_len[net] += pcbnew.ToMM(t.GetLength())
        per_net_seg[net] += 1
        per_layer_seg[board.GetLayerName(t.GetLayer())] += 1

    per_net_via: dict[str, int] = defaultdict(int)
    for v in vias:
        per_net_via[v.GetNetname() or ""] += 1

    bb = board.GetBoardEdgesBoundingBox()
    zones = list(board.Zones())
    filled_zones = [z for z in zones if z.IsFilled()]

    return {
        "file": str(path),
        "footprint_count": len(footprints),
        "copper_layer_count": board.GetCopperLayerCount(),
        "track_segment_count": len(segments),
        "via_count": len(vias),
        "total_track_length_mm": round(sum(pcbnew.ToMM(t.GetLength()) for t in segments), 3),
        "board_width_mm": round(pcbnew.ToMM(bb.GetWidth()), 3),
        "board_height_mm": round(pcbnew.ToMM(bb.GetHeight()), 3),
        "zone_count": len(zones),
        "zone_filled_count": len(filled_zones),
        "zone_layers": sorted({board.GetLayerName(z.GetLayer()) for z in zones}),
        "segments_per_layer": dict(sorted(per_layer_seg.items())),
        "net_track_length_mm": {k: round(v, 3) for k, v in sorted(per_net_len.items()) if k},
        "net_segment_count": {k: v for k, v in sorted(per_net_seg.items()) if k},
        "net_via_count": {k: v for k, v in sorted(per_net_via.items()) if k},
        "footprints": [
            {
                "reference": fp.GetReference(),
                "value": fp.GetValue(),
                "layer": board.GetLayerName(fp.GetLayer()),
                "x_mm": round(pcbnew.ToMM(fp.GetPosition().x), 3),
                "y_mm": round(pcbnew.ToMM(fp.GetPosition().y), 3),
                "rotation_deg": round(fp.GetOrientationDegrees(), 1),
            }
            for fp in sorted(footprints, key=lambda f: f.GetReference())
        ],
    }
