from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nztbdo_labeling.auto_labeler import auto_label_episode
from nztbdo_labeling.episode_builder import build_combat_episodes
from nztbdo_labeling.io import read_tick_events, write_jsonl


@dataclass(frozen=True)
class LabelingSummary:
    session_id: str
    events_total: int
    episodes_total: int
    output_path: Path


def run_labeling_for_session(
    *,
    events_path: Path,
    labels_root: Path,
    pre_ticks: int = 2,
    post_ticks: int = 2,
) -> LabelingSummary:
    events = read_tick_events(events_path)
    if not events:
        session_id = events_path.parent.name
        output_path = labels_root / session_id / "episodes.jsonl"
        write_jsonl(output_path, [])
        return LabelingSummary(
            session_id=session_id,
            events_total=0,
            episodes_total=0,
            output_path=output_path,
        )

    session_id = events[0].session_id
    episodes = build_combat_episodes(events, pre_ticks=pre_ticks, post_ticks=post_ticks)
    labels = [auto_label_episode(ep) for ep in episodes]
    output_path = labels_root / session_id / "episodes.jsonl"
    write_jsonl(output_path, labels)

    return LabelingSummary(
        session_id=session_id,
        events_total=len(events),
        episodes_total=len(episodes),
        output_path=output_path,
    )


def latest_events_file(logs_root: Path) -> Path | None:
    candidates = sorted(logs_root.glob("*/events.jsonl"))
    if not candidates:
        return None
    return candidates[-1]
