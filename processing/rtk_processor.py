import subprocess
from pathlib import Path


def build_rtk_command(rover_obs: str, base_obs: str, nav_files: list[str],
                      output_path: str, config: dict) -> list[str]:
    """Build the rnx2rtkp command from configuration."""
    cmd = ["rnx2rtkp"]

    mode = config.get("mode", 2)
    cmd += ["-p", str(mode)]

    mask = config.get("elevation_mask", 15)
    cmd += ["-m", str(mask)]

    constellations = config.get("constellations", ["G", "R"])
    if constellations:
        cmd += ["-sys", ",".join(constellations)]

    freq = config.get("frequencies", 2)
    cmd += ["-f", str(freq)]

    ar_threshold = config.get("ar_threshold", 3.0)
    cmd += ["-v", str(ar_threshold)]

    if config.get("fix_and_hold", False):
        cmd.append("-h")

    if config.get("instantaneous_ar", False):
        cmd.append("-i")

    if config.get("combined_solution", False):
        cmd.append("-c")

    cmd.append("-t")

    if config.get("time_utc", False):
        cmd.append("-u")

    base_pos = config.get("base_position", {})
    if base_pos.get("source") == "manual":
        lat = base_pos.get("lat", 0.0)
        lon = base_pos.get("lon", 0.0)
        hgt = base_pos.get("hgt", 0.0)
        cmd += ["-l", str(lat), str(lon), str(hgt)]
    elif base_pos.get("source") == "rinex_header":
        lat = base_pos.get("lat", 0.0)
        lon = base_pos.get("lon", 0.0)
        hgt = base_pos.get("hgt", 0.0)
        if lat != 0.0 or lon != 0.0:
            cmd += ["-l", str(lat), str(lon), str(hgt)]

    cmd += ["-o", str(output_path)]
    cmd.append(str(rover_obs))
    cmd.append(str(base_obs))
    cmd += [str(f) for f in nav_files]

    return cmd


def run_rtk(rover_obs: str, base_obs: str, nav_files: list[str],
            output_path: str, config: dict) -> tuple[int, str, str]:
    """Run RTK post-processing with rnx2rtkp."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = build_rtk_command(rover_obs, base_obs, nav_files, output_path, config)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result.returncode, result.stdout, result.stderr


def run_single_point(rover_obs: str, nav_files: list[str],
                     output_path: str) -> tuple[int, str, str]:
    """Run single-point positioning (no base station) for comparison."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["rnx2rtkp"]
    cmd += ["-p", "0"]
    cmd += ["-m", "15"]
    cmd.append("-t")
    cmd += ["-o", str(output_path)]
    cmd.append(str(rover_obs))
    cmd += [str(f) for f in nav_files]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result.returncode, result.stdout, result.stderr
