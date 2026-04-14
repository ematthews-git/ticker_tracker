import json
from pathlib import Path
from datetime import datetime, timezone

import logging

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 96  # 48 hours of :00 + :30 runs


def get_stats_path() -> Path:
    """Returns path to the rolling stats JSON file, creating parent dirs if needed."""
    path = Path.home() / ".ticker_tracker" / "stats" / "collection_stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_stat(stat: dict) -> None:
    """Appends a stat entry to the rolling stats file, trimming to the last 96 entries.

    Args:
        stat (dict): The stat entry to append. Should include a 'timestamp' key.
    """
    path = get_stats_path()

    try:
        if path.exists():
            with open(path, "r") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        else:
            entries = []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read stats file, starting fresh: {e}")
        entries = []

    stat.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    entries.append(stat)
    entries = entries[-_MAX_ENTRIES:]

    try:
        with open(path, "w") as f:
            json.dump(entries, f, indent=2, default=str)
    except OSError as e:
        logger.error(f"Could not write stats file: {e}")
