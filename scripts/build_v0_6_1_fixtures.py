"""v0.6.1: build 5 new Lane B fixtures (ATK-3/4 + SP-R8-01 + GATE-J1 + H5)."""
import hashlib
import json
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "examples" / "minimal.aepkg"
LANE_B = Path(__file__).resolve().parents[1] / "tests" / "lane_b"


def setup(name: str) -> Path:
    target = LANE_B / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(BASE, target)
    return target


def write_jsonl(path: Path, records):
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    # ATK-3 GR transitive laundering: A -> B -> C=GR
    atk7 = setup("atk-gr-laundering-chain.aepkg")
    chain_claims = [
        {
            "id": "claim:A", "type": "Claim", "reliability": "STRONGLY_PLAUSIBLE",
            "scope": "GENERAL_CLAIM", "axis_b_action": "GO", "status": "active",
            "claim_text": "Top-level claim laundering through GR chain",
            "basis": [{"claim_id": "claim:B"}],
            "decision_time_revalidation_required": False, "semantic_stability": "stable",
            "created_at": "2026-05-14T12:00:00Z",
        },
        {
            "id": "claim:B", "type": "Claim", "reliability": "PLAUSIBLE",
            "scope": "CONTEXT_BOUND_PATTERN", "axis_b_action": "EXPERIMENT", "status": "active",
            "claim_text": "Intermediate claim hiding the GR-only chain",
            "basis": [{"claim_id": "claim:C"}],
            "decision_time_revalidation_required": False, "semantic_stability": "stable",
            "created_at": "2026-05-14T12:00:00Z",
        },
        {
            "id": "claim:C", "type": "Claim", "reliability": "GOVERNANCE_RULE",
            "scope": "GENERAL_CLAIM", "axis_b_action": "GO", "status": "active",
            "claim_text": "Bare governance rule",
            "basis": [], "go_justification_claim_ids": ["claim:A"],
            "decision_time_revalidation_required": True, "semantic_stability": "stable",
            "created_at": "2026-05-14T12:00:00Z",
        },
    ]
    write_jsonl(atk7 / "data" / "claims.jsonl", chain_claims)
    print("#7 atk-gr-laundering-chain: A->B->C=GR")

    # ATK-4 supersession self-loop + degenerate migration receipt
    atk8 = setup("atk-supersession-self-loop.aepkg")
    m = json.loads((atk8 / "aepkg.json").read_text(encoding="utf-8"))
    m["extensions"] = m.get("extensions", {}) or {}
    m["extensions"]["supersedes_packet_id"] = m["packet_id"]
    m["extensions"]["aep:deep_migration_receipt"] = {
        "pre_state_hash": "sha256:abc12345abc12345abc12345abc12345abc12345abc12345abc12345abc12345",
        "post_state_hash": "sha256:abc12345abc12345abc12345abc12345abc12345abc12345abc12345abc12345",
        "tool": "fake-migrator", "tool_version": "0.0.1",
        "timestamp": "2026-05-14T12:00:00Z",
    }
    (atk8 / "aepkg.json").write_text(
        json.dumps(m, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("#8 atk-supersession-self-loop: supersedes_packet_id==packet_id + pre==post_state_hash")

    # SP-R8-01 body-envelope-leak
    atk9 = setup("atk-body-envelope-leak.aepkg")
    m = json.loads((atk9 / "aepkg.json").read_text(encoding="utf-8"))
    state_hash_hex = m["integrity"]["state_hash"].partition(":")[2]
    claims_path = atk9 / "data" / "claims.jsonl"
    records = []
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    if records:
        records[0]["claim_text"] = f"Recursive attack: my envelope hash is {state_hash_hex}"
    write_jsonl(claims_path, records)
    print(f"#9 atk-body-envelope-leak: data/claims.jsonl contains state_hash hex {state_hash_hex[:16]}...")

    # GATE-J1 shared-schema-lens-collapse
    atk10 = setup("atk-shared-schema-lens-collapse.aepkg")
    shared_schema = "sha256:" + "a" * 64
    fake_reviews = [
        {
            "id": f"rev:0{i}", "type": "Review", "reviewer_agent": agent,
            "review_tier": "R2", "authoring_schema_sha256": shared_schema,
            "convergence_count": 3, "target_claim_id": "claim:c01",
            "verdict": "PROVEN/RELIABLE", "created_at": "2026-05-14T12:00:00Z",
        }
        for i, agent in enumerate(["alice", "bob", "carol"], start=1)
    ]
    write_jsonl(atk10 / "reviews" / "reviews.jsonl", fake_reviews)
    print("#10 atk-shared-schema-lens-collapse: 3 reviews shared authoring_schema_sha256")

    # H5 content-hash-mismatch
    atk11 = setup("atk-content-hash-mismatch.aepkg")
    sources_path = atk11 / "data" / "sources.jsonl"
    records = []
    for line in sources_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    records.append({
        "id": "src:bad-content-hash", "type": "Source",
        "created_at": "2026-05-14T12:00:00Z", "source_type": "in_packet_file",
        "title": "Source claiming wrong content_hash",
        "location": {
            "kind": "file", "value": "./data/claims.jsonl",
            "location_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        },
        "provenance_strength": "strong", "limits": [],
    })
    write_jsonl(sources_path, records)
    print("#11 atk-content-hash-mismatch: claimed location_hash differs from actual sha256(./data/claims.jsonl)")

    print()
    print("v0.6.1 — 5 new Lane B fixtures built.")


if __name__ == "__main__":
    main()
