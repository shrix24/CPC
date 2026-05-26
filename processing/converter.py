import shutil
import subprocess
from pathlib import Path

CONVBIN_EXE = r"C:\development\RTKLIB_bin\bin\convbin.exe"

_RINEX_EXTENSIONS = {
    "obs": ".obs",
    "nav": ".nav",
    "gnav": ".gnav",
    "hnav": ".hnav",
    "qnav": ".qnav",
    "lnav": ".lnav",
    "sbs": ".sbs",
}


def convert_ubx(ubx_path: str, output_dir: str) -> dict:
    """Convert a .ubx file to RINEX using convbin.

    Returns dict with keys like 'obs', 'nav', 'gnav', etc.
    mapping to file paths for each generated file.
    Also includes 'returncode', 'stdout', 'stderr'.
    """
    ubx_path = Path(ubx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [CONVBIN_EXE, str(ubx_path)],
        capture_output=True, text=True, timeout=300,
    )

    stem = ubx_path.stem
    src_dir = ubx_path.parent

    generated = {}
    for key, ext in _RINEX_EXTENSIONS.items():
        src = src_dir / f"{stem}{ext}"
        if src.exists() and src.stat().st_size > 0:
            dest = output_dir / src.name
            shutil.move(str(src), str(dest))
            generated[key] = str(dest)

    generated["returncode"] = result.returncode
    generated["stdout"] = result.stdout
    generated["stderr"] = result.stderr

    return generated


def parse_rinex_header_position(obs_path: str) -> tuple | None:
    """Extract approximate position from a RINEX observation file header.

    Returns (x, y, z) in ECEF meters, or None if not found.
    """
    with open(obs_path, "r") as f:
        for line in f:
            if "APPROX POSITION XYZ" in line:
                parts = line.split()
                try:
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    if x != 0.0 or y != 0.0 or z != 0.0:
                        return (x, y, z)
                except (ValueError, IndexError):
                    pass
            if "END OF HEADER" in line:
                break
    return None


def ecef_to_lla(x: float, y: float, z: float) -> tuple:
    """Convert ECEF coordinates to latitude, longitude, height (WGS84)."""
    import math

    a = 6378137.0
    f = 1.0 / 298.257223563
    b = a * (1.0 - f)
    e2 = 1.0 - (b * b) / (a * a)

    lon = math.atan2(y, x)
    p = math.sqrt(x * x + y * y)
    lat = math.atan2(z, p * (1.0 - e2))

    for _ in range(10):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        lat_new = math.atan2(z + e2 * N * sin_lat, p)
        if abs(lat_new - lat) < 1e-12:
            break
        lat = lat_new

    sin_lat = math.sin(lat)
    N = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    h = p / math.cos(lat) - N

    return (math.degrees(lat), math.degrees(lon), h)
