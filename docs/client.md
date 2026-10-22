# PixLite client library

The `advatek-pixlite-client` distribution contains the asynchronous HTTP protocol client without a Home Assistant dependency. Its canonical source is `custom_components/advatek_pixlite/_client`; the custom integration's `api.py` reexports that client so a manual custom integration installation remains self-contained. Core uses the separately installed `advatek_pixlite_client` package instead.

Build a wheel and source distribution from the repository root with `python -m build`. For development, install it with `python -m pip install -e .`.

Version 0.1.0 is a proposed first release, not an existing PyPI release. Do not publish it or add it to an upstream requirement until the source, release contents and license have been reviewed. Publication requires an agreed OSI-approved license, a public source repository and issue tracker, a matching release tag, and a public CI build and publication workflow. No license grant or release approval is asserted by this preparation.

The library uses a caller-owned aiohttp session, serializes HTTP requests, checks API v1.9 support, authenticates with the controller's password-hash query format, and returns controller objects. It does not configure Home Assistant, install entities, or manage Home Assistant state.
