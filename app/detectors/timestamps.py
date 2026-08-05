from __future__ import annotations

import math
from datetime import time, timedelta


def parse_birdnet_timestamp(
    value: object,
    *,
    field_name: str = "timestamp",
) -> float:
    """Convert a BirdNET audio offset to non-negative seconds.

    BirdNET CSV output uses ``HH:MM:SS.ff`` strings, while older and
    programmatic callers may provide numeric seconds or ``MM:SS.ff``.
    """
    if isinstance(value, bool):
        raise ValueError(f"Invalid BirdNET {field_name}: {value!r}")

    if isinstance(value, timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, time):
        seconds = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        )
    elif isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            raise ValueError(f"Invalid BirdNET {field_name}: empty value")

        parts = raw_value.split(":")
        try:
            if len(parts) == 1:
                seconds = float(parts[0])
            elif len(parts) == 2:
                minutes = int(parts[0])
                second_component = float(parts[1])
                if minutes < 0 or not 0 <= second_component < 60:
                    raise ValueError
                seconds = minutes * 60 + second_component
            elif len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                second_component = float(parts[2])
                if (
                    hours < 0
                    or not 0 <= minutes < 60
                    or not 0 <= second_component < 60
                ):
                    raise ValueError
                seconds = hours * 3600 + minutes * 60 + second_component
            else:
                raise ValueError
        except ValueError as error:
            raise ValueError(
                f"Invalid BirdNET {field_name}: {value!r}"
            ) from error
    else:
        raise ValueError(f"Invalid BirdNET {field_name}: {value!r}")

    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"Invalid BirdNET {field_name}: {value!r}")

    return seconds
