"""_frame.md, _persona.md, _watchlist.md 로드."""
from dataclasses import dataclass
from pathlib import Path

from pipeline import config


@dataclass(frozen=True)
class FrameSpec:
    frame_md: str
    persona_md: str
    watchlist_md: str


def load_frame(repo_root: Path | None = None) -> FrameSpec:
    root = repo_root or config.REPO_ROOT
    return FrameSpec(
        frame_md=(root / "_frame.md").read_text(encoding="utf-8"),
        persona_md=(root / "_persona.md").read_text(encoding="utf-8"),
        watchlist_md=(root / "_watchlist.md").read_text(encoding="utf-8"),
    )
