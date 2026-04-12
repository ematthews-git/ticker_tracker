import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TICKERS_PATH = Path(__file__).parent.parent / "valid_tickers.json"
FAILURES_PATH = Path(__file__).parent.parent / "ticker_failures.json"
FAILURE_THRESHOLD = 3


def _load_json(path: Path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def record_failures(failed_tickers: list[str]) -> list[str]:
    """Record fetch failures for tickers. Returns any tickers that hit the
    threshold and were removed from valid_tickers.json.

    Args:
        failed_tickers: Tickers that failed to fetch in this run.

    Returns:
        List of tickers that were removed from valid_tickers.json.
    """
    if not failed_tickers:
        return []

    failures: dict[str, int] = _load_json(FAILURES_PATH, {})

    for ticker in failed_tickers:
        failures[ticker] = failures.get(ticker, 0) + 1

    to_remove = [t for t, count in failures.items() if count >= FAILURE_THRESHOLD]

    if to_remove:
        valid: list[str] = _load_json(TICKERS_PATH, [])
        valid_set = set(valid)
        removed = [t for t in to_remove if t in valid_set]

        if removed:
            updated = [t for t in valid if t not in set(to_remove)]
            _save_json(TICKERS_PATH, updated)
            logger.warning(
                f"Removed {len(removed)} tickers after {FAILURE_THRESHOLD}+ "
                f"fetch failures: {removed}"
            )

        # Clear removed tickers from failure tracker
        for ticker in to_remove:
            failures.pop(ticker, None)

    _save_json(FAILURES_PATH, failures)
    return to_remove
