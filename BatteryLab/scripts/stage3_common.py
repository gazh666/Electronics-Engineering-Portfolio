"""第三阶段脚本共用的数据装载与 OCV 构建。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from battery_models.ocv_model import IdentifiedOcvModel
from battery_models.parameters import load_yaml
from datasets.calce_loader import load_archive
from identification.capacity_estimator import estimate_capacity_from_frame
from identification.models import CapacityResult
from identification.ocv_extractor import build_ocv_table, extract_low_current_ocv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
IDENTIFIED_DIR = PROJECT_ROOT / "data" / "identified"
CONFIG_DIR = PROJECT_ROOT / "configs"


def configs() -> dict[str, Any]:
    return {
        "split": load_yaml(CONFIG_DIR / "dataset_split.yaml"),
        "identification": load_yaml(CONFIG_DIR / "identification_config.yaml"),
        "bounds": load_yaml(CONFIG_DIR / "parameter_bounds.yaml"),
        "validation": load_yaml(CONFIG_DIR / "stage3_validation.yaml"),
    }


@lru_cache(maxsize=16)
def load_record(name: str) -> pd.DataFrame:
    split = load_yaml(CONFIG_DIR / "dataset_split.yaml")
    record = split["datasets"][name]
    loaded = load_archive(RAW_DIR / record["file_name"], record["dataset_id"], record.get("cell_id", "UNKNOWN"))
    frame = loaded.frame
    if record.get("source_file"):
        frame = frame[frame["source_file"] == record["source_file"]]
    return frame.sort_values("time_s").reset_index(drop=True)


def capacity_bundle() -> dict[str, CapacityResult]:
    settings = load_yaml(CONFIG_DIR / "identification_config.yaml")["data_quality"]
    results: dict[str, CapacityResult] = {}
    for key, record_name in (("sp2", "capacity_reference"), ("sp1", "capacity_cross_check")):
        frame = load_record(record_name)
        results[key] = estimate_capacity_from_frame(
            frame,
            dataset_id=load_yaml(CONFIG_DIR / "dataset_split.yaml")["datasets"][record_name]["dataset_id"],
            rated_capacity_ah=2.0,
            temperature_c=25.0,
            minimum_discharge_current_a=settings["minimum_discharge_current_a"],
            minimum_duration_s=settings["minimum_complete_discharge_s"],
            maximum_gap_s=settings["maximum_sampling_gap_s"],
        )
    return results


def ocv_bundle() -> dict[str, Any]:
    """低电流 OCV 提取 + 查表模型 + 跨样品对照。"""
    split = load_yaml(CONFIG_DIR / "dataset_split.yaml")
    identification = load_yaml(CONFIG_DIR / "identification_config.yaml")
    capacities = capacity_bundle()
    frame = load_record("ocv_low_current_primary")
    curves = extract_low_current_ocv(
        frame,
        capacity_ah=capacities["sp1"].integrated_capacity_ah,
        current_tolerance_a=identification["ocv"]["low_current_max_abs_a"],
        grid_points=identification["ocv"]["soc_grid_points"],
    )
    soc_values, ocv_values, table_metadata = build_ocv_table(curves["average"])
    model = IdentifiedOcvModel(
        tuple(float(value) for value in soc_values),
        tuple(float(value) for value in ocv_values),
        metadata_info={
            "cell_model": split["cell_model"],
            "cell_id": "SP1",
            "temperature_c": 25.0,
            "direction": "charge_discharge_average",
            "source_dataset": split["datasets"]["ocv_low_current_primary"]["dataset_id"],
            "source_sha256": split["datasets"]["ocv_low_current_primary"]["sha256"],
            "soc_reference": "branch_integral",
            **table_metadata,
        },
        interpolation="piecewise_linear",
    )
    return {
        "model": model,
        "curves": curves,
        "soc_table": soc_values,
        "ocv_table": ocv_values,
        "table_metadata": table_metadata,
        "capacities": capacities,
    }


def write_ocv_artifacts(bundle: dict[str, Any], directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    curves = bundle["curves"]
    paths: dict[str, str] = {}
    mapping = {
        "ocv_low_current_charge.csv": curves["charge"],
        "ocv_low_current_discharge.csv": curves["discharge"],
        "ocv_low_current_average.csv": curves["average"],
        "ocv_hysteresis.csv": curves["hysteresis"],
    }
    for name, table in mapping.items():
        path = directory / name
        table.to_csv(path, index=False)
        paths[name] = str(path)
    table_path = IDENTIFIED_DIR / "ocv" / "ocv_soc_average.csv"
    table_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"soc": bundle["soc_table"], "ocv_v": bundle["ocv_table"]}).to_csv(table_path, index=False)
    paths["identified_table"] = str(table_path)
    return paths
