"""Pure protocol helpers for intensity, colours and palette presets."""


def color_channel_count(data):
    """Read the channel count from the commissioned controller configuration."""
    config = data.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("pix"), dict):
        return None
    kind = config["pix"].get("colorType")
    return (
        {"RGB": 3, "RGBW": 4, "RGBWX": 5}.get(kind) if isinstance(kind, str) else None
    )


def require_color_channels(data):
    """Reject colour writes without a recognized controller colour type."""
    count = color_channel_count(data)
    if count is None:
        raise ValueError("Pixel colour type is missing or unsupported")
    return count


def validate_color(data, color):
    """Validate a complete 16-bit vector against the configured channel count."""
    count = require_color_channels(data)
    if (
        not isinstance(color, (tuple, list))
        or len(color) != count
        or any(type(value) is not int or not 0 <= value <= 65535 for value in color)
    ):
        raise ValueError("Colour does not match the configured pixel channels")
    return tuple(color)


def transition_ms(seconds):
    return max(0, min(4294967295, round(float(seconds) * 1000)))


def pixel_intensity(data):
    return next(
        (
            item
            for item in data.get("status", {}).get("outInt", [])
            if item.get("out") == "Pix"
        ),
        {},
    )


def effective_brightness(data):
    item = pixel_intensity(data)
    factors = item.get("fc", [])
    if len(factors) != 2:
        return None
    live = data.get("statistic", {}).get("pixData", {}).get("liveIntAv", False)
    return factors[0 if item.get("progPri") != "Hi" and live else 1]


def solid_color(data):
    """Return top-level solid colour in 16-bit units, not a playlist item."""
    status = data.get("status", {})
    params = status.get("params") or {}
    if status.get("mode") != "playback" or params.get("op") != "Color":
        return None
    color = params.get("color")
    resolution = params.get("colorRes", "8Bit")
    if resolution not in ("8Bit", "16Bit") or not isinstance(color, (list, tuple)):
        return None
    maximum = 255 if resolution == "8Bit" else 65535
    if any(type(value) is not int or not 0 <= value <= maximum for value in color):
        return None
    scale = 257 if resolution == "8Bit" else 1
    try:
        return validate_color(data, tuple(value * scale for value in color))
    except ValueError:
        return None


def palette(data):
    interface = data.get("config", {}).get("operIf", {})
    resolution = interface.get("colorRes", "8Bit")
    colors = interface.get("pal", [])
    if resolution not in ("8Bit", "16Bit") or not isinstance(colors, list):
        return []
    maximum = 255 if resolution == "8Bit" else 65535
    scale = 257 if resolution == "8Bit" else 1
    result = []
    for color in colors[:12]:
        if not isinstance(color, (list, tuple)) or any(
            type(value) is not int or not 0 <= value <= maximum for value in color
        ):
            return []
        result.append(tuple(value * scale for value in color))
    return result


def intensity_params(brightness, duration=0):
    # HiSet makes explicit HA brightness/on/off commands take control from live DMX.
    return {
        "item": [{"out": "Pix", "op": "HiSet", "fc": brightness, "durMs": duration}]
    }


def color_params(color, duration=0):
    # Field order follows Table 46; preserve all five channels for palette colours.
    return {
        "op": "Color",
        "color": list(color),
        "colorRes": "16Bit",
        "fadeMs": duration,
    }
