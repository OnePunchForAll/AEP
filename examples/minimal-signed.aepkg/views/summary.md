# Minimal AEP v0.5.5 Example Packet

This packet demonstrates the minimum-viable shape of a valid AEP v0.5.5 packet:
1 source (RFC 8785 with external URL anchor), 1 span, 2 claims (one STRONGLY_PLAUSIBLE + GO; one ASSUMPTION + EXPLORE), 1 relation.

Validates clean under `aep:0.5/stable` strict Level-2 via `python -m aep.validate_v0_5_1`.
