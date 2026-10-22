"""Pure protocol helpers for intensity, colours and palette presets."""


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
    color = params.get("color", [0, 0, 0])
    scale = 257 if params.get("colorRes", "8Bit") == "8Bit" else 1
    return tuple(value * scale for value in color)


def palette(data):
    interface = data.get("config", {}).get("operIf", {})
    scale = 257 if interface.get("colorRes", "8Bit") == "8Bit" else 1
    return [
        tuple(value * scale for value in color)
        for color in interface.get("pal", [])[:12]
    ]


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
