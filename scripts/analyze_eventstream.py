#!/usr/bin/env python3
"""Report on a captured SecuritySpy event stream, and reduce it with the library.

Parsing goes through `aiosecurityspy.parse_event_line`, and the CLASSIFY signals
are fed through the real `EpisodeReducer`, so this measures the shipped
behaviour rather than a reimplementation of it. The headline number is the
signal-to-episode reduction ratio PRD 11.1 treats as a correctness requirement.

Usage:
    uv run --directory aiosecurityspy python ../scripts/analyze_eventstream.py CAPTURE.log
    ... --threshold 70 --debounce 3 --gap 30      # try other tuning
    ... --sweep                                    # grid over plausible tunings
"""

from __future__ import annotations

import argparse
import collections
import itertools
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiosecurityspy import (
    ClassificationPayload,
    DetectionEpisode,
    EpisodeClosed,
    EpisodeOpened,
    EpisodeReducer,
    ReducerConfig,
    StreamEvent,
    parse_event_line,
)

#: How many distinct peak confidences to print per tuning row.
PEAKS_SHOWN = 8


def load(path: Path, offset_seconds: int) -> tuple[list[tuple[int, StreamEvent]], int]:
    """Parse a capture into (connection, StreamEvent) pairs, keeping order."""
    tz = timezone(timedelta(seconds=offset_seconds))
    events: list[tuple[int, StreamEvent]] = []
    connection = unparsed = 0
    # The capture is stored as raw wire bytes, so records are CR-terminated while
    # the `#CONNECT` markers the capture script writes are LF-terminated.
    # `splitlines()` handles both, which is exactly what is wanted here.
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("#CONNECT"):
            connection += 1
            continue
        if line.startswith("#") or not line.strip():
            continue
        event = parse_event_line(line, server_timezone=tz)
        if event is None:
            unparsed += 1
            continue
        events.append((connection, event))
    return events, unparsed


def reduce_stream(
    events: list[tuple[int, StreamEvent]], config: ReducerConfig
) -> tuple[list[DetectionEpisode], int, int]:
    """Feed every CLASSIFY event through the reducer; return episodes + counts."""
    reducer = EpisodeReducer(default=config)
    episodes: list[DetectionEpisode] = []
    opened = signals = 0
    last: datetime | None = None
    for _connection, event in events:
        if isinstance(event.payload, ClassificationPayload):
            signals += sum(1 for _ in event.payload.classes)
        for emitted in reducer.feed(event):
            if isinstance(emitted, EpisodeOpened):
                opened += 1
            elif isinstance(emitted, EpisodeClosed):
                episodes.append(emitted.episode)
        if event.timestamp is not None:
            last = event.timestamp
    if last is not None:
        episodes.extend(
            emitted.episode
            for emitted in reducer.close_all(last)
            if isinstance(emitted, EpisodeClosed)
        )
    return episodes, opened, signals


def main() -> int:  # noqa: PLR0915 - a report reads better as one linear pass
    """Parse the capture, describe it, and run the reducer over it."""
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument(
        "--offset-seconds",
        type=int,
        default=None,
        help="server UTC offset; defaults to this machine's current offset",
    )
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--debounce", type=int, default=3)
    ap.add_argument("--gap", type=float, default=30.0, help="seconds")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    offset = args.offset_seconds
    if offset is None:
        offset = -(time.altzone if time.daylight and time.localtime().tm_isdst else time.timezone)

    events, unparsed = load(Path(args.capture), offset)
    if not events:
        print("no parseable records -- is the capture empty?")
        return 1

    kinds = collections.Counter(e.event_type for _c, e in events)
    connections = max(c for c, _e in events)
    span = events[-1][1].timestamp - events[0][1].timestamp

    print(f"records            {len(events)}  ({unparsed} unparseable)")
    print(f"connections        {connections}")
    print(f"span               {span}")
    print("event types        " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))

    # Event numbers restart per connection -- show it rather than assume it.
    per_conn = collections.defaultdict(list)
    for c, e in events:
        per_conn[c].append(e.event_number)
    resets = [c for c, nums in per_conn.items() if nums and nums[0] == 0]
    print(f"connections whose event numbers restart at 0: {len(resets)}/{len(per_conn)}")

    classify = [e for _c, e in events if isinstance(e.payload, ClassificationPayload)]
    if not classify:
        print("\nno CLASSIFY records in this capture -- nothing for the reducer to reduce.")
        return 0

    labels = collections.Counter()
    confidences = []
    for e in classify:
        for label, value in e.payload.classes.items():
            labels[label] += 1
            confidences.append(value)
    print(f"\nCLASSIFY records   {len(classify)}")
    print("labels             " + ", ".join(f"{k}={v}" for k, v in labels.most_common(10)))
    print(
        f"confidence         min={min(confidences):.0f} "
        f"median={statistics.median(confidences):.0f} max={max(confidences):.0f}"
    )

    gaps = []
    by_cam = collections.defaultdict(list)
    for e in classify:
        by_cam[e.camera].append(e.timestamp)
    for stamps in by_cam.values():
        gaps.extend((b - a).total_seconds() for a, b in itertools.pairwise(stamps) if b >= a)
    if gaps:
        print(f"inter-signal gap   median={statistics.median(gaps):.1f}s max={max(gaps):.1f}s")

    tunings = [(args.threshold, args.debounce, args.gap)]
    if args.sweep:
        tunings = [
            (t, d, g)
            for t in (50.0, 60.0, 70.0, 80.0, 90.0)
            for d in (1, 2, 3, 5)
            for g in (10.0, 30.0, 60.0)
        ]

    print(f"\n{'thresh':>7} {'deb':>4} {'gap':>6} {'episodes':>9} {'ratio':>8}  peak confidences")
    for threshold, debounce, gap in tunings:
        config = ReducerConfig(threshold=threshold, debounce=debounce, gap=timedelta(seconds=gap))
        episodes, opened, signals = reduce_stream(events, config)
        emissions = opened + len(episodes)
        peaks = sorted({round(ep.peak_confidence) for ep in episodes})
        shown = ", ".join(str(p) for p in peaks[:PEAKS_SHOWN])
        shown += "..." if len(peaks) > PEAKS_SHOWN else ""
        ratio = f"{signals / emissions:8.1f}" if emissions else f"{'n/a':>8}"
        print(f"{threshold:7.0f} {debounce:4d} {gap:6.0f} {len(episodes):9d} {ratio}  {shown}")

    print(
        f"\n(signals fed: {signals}. ratio = signals / (opens + closes); "
        f"PRD 11.1 wants roughly 190:1 on the reference burst.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
