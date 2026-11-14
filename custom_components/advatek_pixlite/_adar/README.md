# Advatek ADAR discovery client

Asynchronous IPv4 discovery for Advatek PixLite Mk3 controllers advertising API v1.9. The client sends discovery requests only. It does not configure devices, upload firmware or control outputs.

```python
from advatek_adar import discover

result = await discover(("192.168.1.10",))
for device in result.devices:
    print(device.mac, device.host, device.model)
```

Pass local interface addresses selected by the caller. Results contain eligible devices, a completion flag and conflicting MAC addresses. Discovery uses multicast followed by limited broadcast, at most six half-second rounds per interface, and at most fifty devices. Network failures produce an incomplete result. Cancellation closes sockets. Device identity must be checked separately through an authenticated connection.

The package is bundled in the custom Home Assistant integration. It is not published, licensed for distribution or qualified on physical controllers. Its private classifier prevents accidental PyPI upload. See the repository's `docs/adar.md` for local validation and the remaining publication requirements.
