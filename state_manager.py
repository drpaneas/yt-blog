import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class StateManager:
    def __init__(self, state_dir: Path, prefix: str = ""):
        self._state_dir = state_dir
        self._state_file = state_dir / "seen_videos.json"
        self._prefix = prefix

    def _key(self, item_id: str) -> str:
        return f"{self._prefix}{item_id}" if self._prefix else item_id

    def load(self) -> dict:
        if not self._state_file.exists():
            return {}
        return json.loads(self._state_file.read_text(encoding="utf-8"))

    def is_seen(self, video_id: str) -> bool:
        return self._key(video_id) in self.load()

    def mark_seen(self, video_id: str, metadata: dict) -> None:
        state = self.load()
        entry = dict(metadata)
        if "processed_at" not in entry:
            entry["processed_at"] = datetime.now(timezone.utc).isoformat()
        state[self._key(video_id)] = entry
        self._atomic_write(state)

    def _atomic_write(self, state: dict) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._state_dir, suffix=".tmp", prefix="seen_videos_"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.write("\n")
            Path(tmp_path).replace(self._state_file)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
