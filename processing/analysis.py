import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


def parse_pos_file(path: str) -> pd.DataFrame:
    """Parse an RTKLIB .pos solution file into a DataFrame."""
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("%") or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 14:
                continue
            try:
                time_str = parts[0] + " " + parts[1]
                row = {
                    "time": pd.to_datetime(time_str, format="%Y/%m/%d %H:%M:%S.%f"),
                    "lat": float(parts[2]),
                    "lon": float(parts[3]),
                    "height": float(parts[4]),
                    "Q": int(parts[5]),
                    "ns": int(parts[6]),
                    "sdn": float(parts[7]),
                    "sde": float(parts[8]),
                    "sdu": float(parts[9]),
                    "sdne": float(parts[10]),
                    "sdeu": float(parts[11]),
                    "sdun": float(parts[12]),
                    "age": float(parts[13]),
                    "ratio": float(parts[14]) if len(parts) > 14 else 0.0,
                }
                rows.append(row)
            except (ValueError, IndexError):
                continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _lla_to_enu(lat0: float, lon0: float, lat: float, lon: float, h0: float, h: float) -> tuple:
    """Convert lat/lon/height difference to local ENU (east, north, up) in meters."""
    d2r = math.pi / 180.0
    dlat = (lat - lat0) * d2r
    dlon = (lon - lon0) * d2r

    R = 6378137.0
    e2 = 0.00669437999014

    sin_lat0 = math.sin(lat0 * d2r)
    Rn = R / math.sqrt(1 - e2 * sin_lat0 * sin_lat0)
    Rm = Rn * (1 - e2) / (1 - e2 * sin_lat0 * sin_lat0)

    north = dlat * Rm
    east = dlon * Rn * math.cos(lat0 * d2r)
    up = h - h0

    return east, north, up


def compute_jitter(df: pd.DataFrame) -> pd.DataFrame:
    """Compute epoch-to-epoch position jitter in ENU."""
    if len(df) < 2:
        return pd.DataFrame()

    east_j, north_j, up_j = [], [], []
    times = []
    for i in range(1, len(df)):
        e, n, u = _lla_to_enu(
            df.iloc[i - 1]["lat"], df.iloc[i - 1]["lon"],
            df.iloc[i]["lat"], df.iloc[i]["lon"],
            df.iloc[i - 1]["height"], df.iloc[i]["height"],
        )
        east_j.append(e)
        north_j.append(n)
        up_j.append(u)
        times.append(df.iloc[i]["time"])

    return pd.DataFrame({"time": times, "east": east_j, "north": north_j, "up": up_j})


def compute_statistics(df: pd.DataFrame) -> dict:
    """Compute summary statistics from a parsed .pos DataFrame."""
    if df.empty:
        return {}

    total = len(df)
    stats = {
        "total_epochs": total,
        "fix_rate": (df["Q"] == 1).sum() / total * 100,
        "float_rate": (df["Q"] == 2).sum() / total * 100,
        "sbas_rate": (df["Q"] == 3).sum() / total * 100,
        "dgps_rate": (df["Q"] == 4).sum() / total * 100,
        "single_rate": (df["Q"] == 5).sum() / total * 100,
        "sdn_rms": np.sqrt(np.mean(df["sdn"] ** 2)),
        "sde_rms": np.sqrt(np.mean(df["sde"] ** 2)),
        "sdu_rms": np.sqrt(np.mean(df["sdu"] ** 2)),
        "sdn_max": df["sdn"].max(),
        "sde_max": df["sde"].max(),
        "sdu_max": df["sdu"].max(),
        "sdn_95": df["sdn"].quantile(0.95),
        "sde_95": df["sde"].quantile(0.95),
        "sdu_95": df["sdu"].quantile(0.95),
        "ns_mean": df["ns"].mean(),
        "ns_min": df["ns"].min(),
        "ns_max": df["ns"].max(),
    }

    jitter = compute_jitter(df)
    if not jitter.empty:
        horiz = np.sqrt(np.array(jitter["east"]) ** 2 + np.array(jitter["north"]) ** 2)
        stats["jitter_horiz_rms"] = np.sqrt(np.mean(horiz ** 2))
        stats["jitter_horiz_max"] = np.max(horiz)
        stats["jitter_vert_rms"] = np.sqrt(np.mean(np.array(jitter["up"]) ** 2))
        stats["jitter_vert_max"] = np.max(np.abs(jitter["up"]))

    return stats


def is_rinex_observation(path: str) -> bool:
    """Check if a file is a RINEX observation file."""
    try:
        with open(path, "r") as f:
            for line in f:
                if "OBSERVATION DATA" in line or "OBS" in line.split()[-1:]:
                    return True
                if "END OF HEADER" in line:
                    break
    except Exception:
        pass
    return False


def parse_ground_truth(path: str) -> pd.DataFrame | None:
    """Parse a ground truth file (.pos or .csv).

    Returns DataFrame with columns: time, lat, lon, height.
    Returns None if the file is a RINEX observation file.
    """
    p = Path(path)
    ext = p.suffix.lower()

    if ext in (".obs",) or re.match(r"\.\d+o$", ext):
        return None

    if is_rinex_observation(path):
        return None

    if ext == ".pos":
        df = parse_pos_file(path)
        if not df.empty:
            return df[["time", "lat", "lon", "height"]].copy()
        return pd.DataFrame()

    # CSV / TXT
    try:
        df = pd.read_csv(path, comment="#")
        df.columns = [c.strip().lower() for c in df.columns]

        time_col = None
        for candidate in ["time", "timestamp", "datetime", "epoch", "date"]:
            if candidate in df.columns:
                time_col = candidate
                break

        if time_col is None:
            df["time"] = pd.to_datetime(df.iloc[:, 0])
        else:
            df["time"] = pd.to_datetime(df[time_col])

        lat_col = next((c for c in df.columns if "lat" in c), None)
        lon_col = next((c for c in df.columns if "lon" in c), None)
        hgt_col = next((c for c in df.columns if c in ("height", "hgt", "alt", "altitude", "h", "ellipsoidal_height")), None)

        if lat_col and lon_col and hgt_col:
            return pd.DataFrame({
                "time": df["time"],
                "lat": df[lat_col].astype(float),
                "lon": df[lon_col].astype(float),
                "height": df[hgt_col].astype(float),
            })
    except Exception:
        pass

    return pd.DataFrame()


def compare_to_ground_truth(solution_df: pd.DataFrame, truth_df: pd.DataFrame) -> dict:
    """Compare a solution to ground truth.

    Returns dict with error time series and statistics.
    """
    if solution_df.empty or truth_df.empty:
        return {}

    sol_ts = solution_df["time"].values.astype(np.int64)
    truth_ts = truth_df["time"].values.astype(np.int64)

    truth_lat = np.interp(sol_ts, truth_ts, truth_df["lat"].values)
    truth_lon = np.interp(sol_ts, truth_ts, truth_df["lon"].values)
    truth_hgt = np.interp(sol_ts, truth_ts, truth_df["height"].values)

    east_err, north_err, up_err = [], [], []
    for i in range(len(solution_df)):
        e, n, u = _lla_to_enu(
            truth_lat[i], truth_lon[i],
            solution_df.iloc[i]["lat"], solution_df.iloc[i]["lon"],
            truth_hgt[i], solution_df.iloc[i]["height"],
        )
        east_err.append(e)
        north_err.append(n)
        up_err.append(u)

    east_err = np.array(east_err)
    north_err = np.array(north_err)
    up_err = np.array(up_err)
    horiz_err = np.sqrt(east_err ** 2 + north_err ** 2)

    sorted_horiz = np.sort(horiz_err)
    cep50_idx = int(len(sorted_horiz) * 0.50)
    cep95_idx = min(int(len(sorted_horiz) * 0.95), len(sorted_horiz) - 1)

    return {
        "times": solution_df["time"].tolist(),
        "east_err": east_err.tolist(),
        "north_err": north_err.tolist(),
        "up_err": up_err.tolist(),
        "horiz_err": horiz_err.tolist(),
        "horiz_rms": float(np.sqrt(np.mean(horiz_err ** 2))),
        "horiz_mean": float(np.mean(horiz_err)),
        "horiz_max": float(np.max(horiz_err)),
        "horiz_cep50": float(sorted_horiz[cep50_idx]),
        "horiz_cep95": float(sorted_horiz[cep95_idx]),
        "vert_rms": float(np.sqrt(np.mean(up_err ** 2))),
        "vert_mean": float(np.mean(np.abs(up_err))),
        "vert_max": float(np.max(np.abs(up_err))),
    }
