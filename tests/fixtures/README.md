# ADAR controller replies

The two JSON replies were captured from physical A4-S Mk3 and E16-S Mk3 controllers on 23 October 2026. Both advertised firmware 3.15.0 and API v1.0 through v1.9. Capture used the production ADAR discovery function on Windows WiFi with both controllers on the same /24 subnet.

`macAddr`, `ipAddr` and `gateway` were replaced with test identifiers and documentation addresses. All other fields retain their captured values. Tests reconstruct the standard discovery-response header around these JSON payloads.

These fixtures verify response parsing, duplicate handling and model-independent HA selection. They do not verify API authentication, output controls, Linux networking or other firmware versions. Live validation sent discovery requests only.
