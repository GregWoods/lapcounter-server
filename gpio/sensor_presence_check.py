"""Can the GPIO Layer 1 tell whether its sensor board is plugged in? (#116)

Runs on the race Pi, inside the gpio image (privileged, has RPi.GPIO). Stop the lane
containers first, since they hold the pins:

    docker stop gpio-1 gpio-2
    docker run --rm -it --privileged -v $PWD/sensor_presence_check.py:/app/check.py \\
        gregkwoods/lapcounter-server-gpio:latest python check.py
    docker start gpio-1 gpio-2

It samples every input pin of both lanes for a few seconds under each pull setting (down,
up, none), once with the board plugged in and once unplugged, with no car crossing. Then
it says, per lane, whether presence can be read from the pins.

The idea under test: when the board is idle, `SELECTED` sits high (handshake_end() in
gpio_to_timestamps.py waits for it). With an internal pull-down, an unplugged pin reads
low. So **if the board actively drives SELECTED high**, pull-down tells the two apart.
If its output only pulls low and relies on a pull-up (open collector), plugged-in-idle and
unplugged both read low under pull-down, and presence has to come from a crossing instead.

It also counts edges on the unplugged, unpulled pin. Every falling edge there would be a
phantom crossing with a random car ID, which is how gpio_to_timestamps.py sets the pins up
today.
"""
import sys
import time

# The same pin map as gpio_to_timestamps.py. Not imported from it: that module sets the
# pins up and starts edge detection at import time.
LANES = [{
    "SELECTED": 2,
    "HSHAKE": 4,
    "CARCODE1": 27,
    "CARCODE2": 22,
    "CARCODE3": 17
}, {
    "SELECTED": 19,
    "HSHAKE": 13,
    "CARCODE1": 6,
    "CARCODE2": 5,
    "CARCODE3": 26
}]
INPUTS = ("SELECTED", "CARCODE1", "CARCODE2", "CARCODE3")
PULLS = ("down", "up", "none")

SAMPLE_SECONDS = 3.0
SAMPLE_INTERVAL_S = 0.001
STEADY = 0.99   # a pin reading high this fraction of the time (or low, 1 - this) is steady

DETECTABLE = "DETECTABLE"
NOT_DRIVEN_HIGH = "NOT_DRIVEN_HIGH"
INCONCLUSIVE = "INCONCLUSIVE"


def summarise(samples):
    """(fraction of samples high, number of level changes) for one pin's readings."""
    if not samples:
        return 0.0, 0
    changes = sum(1 for a, b in zip(samples, samples[1:]) if a != b)
    return sum(samples) / len(samples), changes


def analyse(plugged, unplugged):
    """Verdict for one lane. `plugged` / `unplugged` map pull -> (fraction high, changes)
    for its SELECTED pin. Returns (verdict, explanation)."""
    p_high, p_changes = plugged["down"]
    u_high, u_changes = unplugged["down"]
    if p_high >= STEADY and p_changes == 0 and u_high <= 1 - STEADY and u_changes == 0:
        return DETECTABLE, ("with pull-down, SELECTED is held high by the board and reads low "
                            "unplugged: GPIO can report sensors_connected from the pin")
    if p_high <= 1 - STEADY and plugged["up"][0] >= STEADY:
        return NOT_DRIVEN_HIGH, ("the board only pulls SELECTED low and relies on a pull-up, so "
                                 "idle and unplugged look the same: presence must come from a crossing")
    return INCONCLUSIVE, (f"pull-down: plugged {p_high:.0%} high / {p_changes} changes, "
                          f"unplugged {u_high:.0%} high / {u_changes} changes. Was a car crossing, "
                          f"or the board not idle? Run again")


def phantom_risk(unplugged):
    """Falling edges an unplugged SELECTED would raise with no pull resistor, as set up today."""
    return unplugged["none"][1] // 2 + unplugged["none"][1] % 2


def _sample(GPIO, pin, pull):
    pud = {"down": GPIO.PUD_DOWN, "up": GPIO.PUD_UP, "none": GPIO.PUD_OFF}[pull]
    GPIO.setup(pin, GPIO.IN, pull_up_down=pud)
    time.sleep(0.05)   # let the pull settle before reading
    samples = []
    end = time.monotonic() + SAMPLE_SECONDS
    while time.monotonic() < end:
        samples.append(GPIO.input(pin))
        time.sleep(SAMPLE_INTERVAL_S)
    return summarise(samples)


def _measure(GPIO):
    """lane index -> pin name -> pull -> (fraction high, changes)."""
    result = {}
    for idx, lane in enumerate(LANES):
        # Handshake high, as gpio_to_timestamps.py leaves it, so the board is idle.
        GPIO.setup(lane["HSHAKE"], GPIO.OUT)
        GPIO.output(lane["HSHAKE"], True)
        result[idx] = {}
        for name in INPUTS:
            result[idx][name] = {pull: _sample(GPIO, lane[name], pull) for pull in PULLS}
            print(f"  lane {idx + 1} {name:9} " + "  ".join(
                f"{pull}: {high:4.0%} high, {changes} changes"
                for pull, (high, changes) in result[idx][name].items()))
    return result


def main():
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    try:
        input("Plug the sensor board in, keep cars off the line, and press Enter... ")
        plugged = _measure(GPIO)
        input("\nNow UNPLUG the sensor board and press Enter... ")
        unplugged = _measure(GPIO)
    finally:
        GPIO.cleanup()

    print()
    for idx in range(len(LANES)):
        verdict, why = analyse(plugged[idx]["SELECTED"], unplugged[idx]["SELECTED"])
        print(f"Lane {idx + 1}: {verdict} - {why}")
        phantoms = phantom_risk(unplugged[idx]["SELECTED"])
        if phantoms:
            print(f"Lane {idx + 1}: unplugged with no pull resistor, SELECTED changed level "
                  f"{unplugged[idx]['SELECTED']['none'][1]} times in {SAMPLE_SECONDS:.0f}s: about "
                  f"{phantoms} phantom crossings, as gpio_to_timestamps.py sets the pin up today")
    return 0


if __name__ == "__main__":
    sys.exit(main())
