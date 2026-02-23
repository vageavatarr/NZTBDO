from __future__ import annotations

from nztbdo_labeling.types import Episode, TickEvent


def build_combat_episodes(events: list[TickEvent], pre_ticks: int = 2, post_ticks: int = 2) -> list[Episode]:
    episodes: list[Episode] = []
    if not events:
        return episodes

    in_combat = False
    combat_start = 0
    combat_end = 0

    for idx, event in enumerate(events):
        if event.fsm_state == "COMBAT" and not in_combat:
            in_combat = True
            combat_start = idx
            combat_end = idx
        elif in_combat and event.fsm_state == "COMBAT":
            combat_end = idx
        elif in_combat and event.fsm_state != "COMBAT":
            episodes.append(_slice_episode(events, combat_start, combat_end, pre_ticks, post_ticks))
            in_combat = False

    if in_combat:
        episodes.append(_slice_episode(events, combat_start, combat_end, pre_ticks, post_ticks))

    return episodes


def _slice_episode(
    events: list[TickEvent],
    combat_start: int,
    combat_end: int,
    pre_ticks: int,
    post_ticks: int,
) -> Episode:
    start = max(0, combat_start - pre_ticks)
    end = min(len(events) - 1, combat_end + post_ticks)
    subset = events[start : end + 1]
    first = subset[0]
    last = subset[-1]
    episode_idx = combat_start

    return Episode(
        session_id=first.session_id,
        episode_id=f"{first.session_id}-ep-{episode_idx:05d}",
        start_ts_ms=first.timestamp_ms,
        end_ts_ms=last.timestamp_ms,
        tick_count=len(subset),
        events=subset,
    )
