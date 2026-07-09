from pathlib import Path

# Directory where this file lives — YAML configs must be placed here during Step 3
_CV_DIR = Path(__file__).parent

# Mapping of logical tracker names to YAML filenames
_TRACKER_MAP: dict[str, str] = {
    "botsort": "my_bytetrack.yaml",
    "bytetrack_bw": "my_bytetrack_bw.yaml",
}


def get_tracker_config(name: str) -> str:
    if name not in _TRACKER_MAP:
        valid = ", ".join(f'"{k}"' for k in _TRACKER_MAP)
        raise ValueError(
            f"Unknown tracker name: '{name}'. Valid options are: {valid}."
        )

    config_path = _CV_DIR / _TRACKER_MAP[name]

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Tracker configuration not found: '{config_path}'.\n"
            f"Please complete the asset migration step (Step 3) to copy "
            f"'{_TRACKER_MAP[name]}' into the cv/ directory."
        )

    return str(config_path)
