from time import sleep as _sleep

# 0.1 means all delays run at 10x speed vs legacy behavior.
SPEED_MULTIPLIER = 0.1


def set_speed_multiplier(multiplier: float) -> None:
    global SPEED_MULTIPLIER
    SPEED_MULTIPLIER = max(0.0, float(multiplier))


def sleep(seconds: float) -> None:
    _sleep(max(0.0, seconds) * SPEED_MULTIPLIER)
