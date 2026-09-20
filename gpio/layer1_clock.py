"""The clock id and counter the GPIO Layer 1s publish, shared by both of them.

lapdata times laps by subtracting two counters that carry the same clock id, so it never
needs anyone's wall clock (see docs/lap-timing-plan.md). For GPIO that counter is
CLOCK_MONOTONIC, which:

- never steps, so setting the Pi's clock mid-meet — by hand from the laptop Home page,
  there being no RTC and no NTP offline — can no longer shorten or lengthen a lap. It
  used to change every lap in progress by the size of the step.
- is shared by every process on the kernel, which is why the clock id is the BOOT id
  rather than a per-process one. It has to be: the two lane containers are separate
  processes, and a car that changes lane mid-race has lap N stamped by one and lap N+1
  by the other. A per-process id would make every such lap a cross-clock one.

Deliberately a module of its own rather than a few lines copied into both scripts. The
ONE thing that must not drift between the two lane containers is agreement about the
clock, and copies drift.
"""
import os
import secrets
import time

MQTT_CLOCK_TOPIC = "layer1_clock"

# lapdata's anchor only has to be roughly right for GPIO — its crossings are
# interrupt-driven, so a sample is microseconds old rather than up to a Slot rotation.
# Once a second is plenty to have it converged well before any lights-out.
HEARTBEAT_INTERVAL_S = 1.0


def _boot_id() -> str:
    """An id that changes when the kernel's monotonic clock restarts, i.e. at boot.

    The fallback is only reached off Linux — running mocked_timestamps.py natively on
    Windows — where there is no /proc. It is per-process, which is correct there: there
    is one process, so nothing has to agree with anything.
    """
    try:
        with open('/proc/sys/kernel/random/boot_id') as f:
            return f.read().strip().replace('-', '')[:8]
    except OSError:
        return secrets.token_hex(4)


CLOCK = f"gpio:{_boot_id()}"


def counter_ms() -> int:
    """The counter, read now. Call this in the interrupt callback, not after the MQTT
    publish — the whole point is that the value is stamped at detection."""
    return time.monotonic_ns() // 1_000_000
