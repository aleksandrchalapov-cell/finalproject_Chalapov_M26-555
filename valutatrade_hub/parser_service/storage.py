"""History and latest snapshots of the rates collected by the parser."""

from dataclasses import dataclass
from datetime import datetime
from fcntl import LOCK_EX, flock

from valutatrade_hub.core.utils import from_iso, to_iso, utc_now
from valutatrade_hub.infra.database import read_json, write_json_atomic
from valutatrade_hub.parser_service.config import ParserConfig


@dataclass(frozen=True)
class RateObservation:
    """One validated rate received from a source at a given time."""

    pair: str
    rate: float
    observed_at: datetime
    source: str

    def to_dict(self) -> dict[str, str | float]:
        """Build the history entry and its pair-and-time identifier."""
        from_currency, to_currency = self.pair.split("_")
        timestamp = to_iso(self.observed_at)
        return {
            "id": f"{self.pair}_{timestamp}",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": self.rate,
            "timestamp": timestamp,
            "source": self.source,
        }


class RatesStorage:
    """Store the history and publish the latest known rates to Core."""

    def __init__(self, config: ParserConfig) -> None:
        self._rates_path = config.rates_path
        self._history_path = config.history_path
        self._lock_path = self._rates_path.with_name(".rates.lock")

    def save_batch(self, observations: list[RateObservation]) -> tuple[int, str | None]:
        """Return the number of updated pairs and the cache refresh timestamp."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a", encoding="utf-8") as lock_file:
            flock(lock_file.fileno(), LOCK_EX)
            return self._save_locked(observations)

    def _save_locked(
        self, observations: list[RateObservation]
    ) -> tuple[int, str | None]:
        history = read_json(self._history_path, [])
        cache = read_json(self._rates_path, {})
        if not isinstance(history, list):
            raise ValueError("История курсов должна содержать JSON-массив")
        if not isinstance(cache, dict) or not isinstance(cache.get("pairs", {}), dict):
            raise ValueError("Некорректный формат кеша курсов")

        known_ids = {record["id"] for record in history}
        original_size = len(history)
        for observation in observations:
            record = observation.to_dict()
            record_id = record["id"]
            if record_id not in known_ids:
                history.append(record)
                known_ids.add(record_id)

        pairs = cache.setdefault("pairs", {})
        updated_pairs = set()
        for record in history:
            pair = f"{record['from_currency']}_{record['to_currency']}"
            timestamp = record["timestamp"]
            current = pairs.get(pair)
            if current is not None and from_iso(timestamp) <= from_iso(
                current["updated_at"]
            ):
                continue
            pairs[pair] = {
                "rate": record["rate"],
                "updated_at": timestamp,
                "source": record["source"],
            }
            updated_pairs.add(pair)

        if len(history) > original_size:
            write_json_atomic(self._history_path, history)
        if updated_pairs:
            cache["last_refresh"] = to_iso(utc_now())
            write_json_atomic(self._rates_path, cache)
        return len(updated_pairs), cache.get("last_refresh")
