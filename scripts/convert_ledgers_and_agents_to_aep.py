"""Convert agent ledgers + agent definitions to AEP packets.

Three steps:

  STEP 1 — Ledger packets (10 canonical agents):
    For each `.claude/agents/_ledgers/<agent>.jsonl`, wrap into
    `.claude/agents/_ledgers/<agent>.aepkg/` with each ledger row as a claim.

  STEP 2 — Agent definition companions (10 canonical agents):
    For each `.claude/agents/<agent>.html` + `<agent>.md` pair, build
    `.claude/agents/<agent>.aepkg/` that carries:
      - .md content as views/source.md (byte-identical to .md Claude Code loads)
      - extracted claims (tools, model, scope, description) in data/claims.jsonl
      - integrity envelope
    Then DELETE the .html (superseded by views/rendered-from-canonical inside packet).
    The .md STAYS unchanged so Claude Code's loader still works.

The original .md file (which Claude Code's loader reads) is NEVER modified.
"""
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path("C:/Users/example-user/")
AEP_PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AEP_PROJECT / "src"))

from aep.validate_v0_5 import canonical_state_hash_v0_5, manifest_hash_v0_5

CANONICAL_AGENTS = [
    "adversary", "curator", "forge", "judge", "pathfinder",
    "scout", "scribe", "strategist", "warden", "visual-judge",
]


def sha256_hex(s: bytes) -> str:
    return hashlib.sha256(s).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_jsonl(path: Path, records):
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")


def write_canonical(packet_root: Path, manifest: dict):
    """Compute integrity envelope + write aepkg.json."""
    state_hash = canonical_state_hash_v0_5(packet_root, manifest["canonical_files"])
    manifest["integrity"]["state_hash"] = state_hash
    manifest["integrity"]["assets_merkle_root"] = "sha256:" + sha256_hex(b"")
    # Compute manifest_hash with manifest_hash field excluded
    mfh = json.loads(json.dumps(manifest))
    mfh["integrity"].pop("manifest_hash", None)
    manifest["integrity"]["manifest_hash"] = manifest_hash_v0_5(mfh)
    (packet_root / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )


def ensure_packet_skeleton(packet_root: Path):
    """Create the standard directory layout."""
    (packet_root / "data").mkdir(parents=True, exist_ok=True)
    (packet_root / "ops").mkdir(parents=True, exist_ok=True)
    (packet_root / "reviews").mkdir(parents=True, exist_ok=True)
    (packet_root / "validations").mkdir(parents=True, exist_ok=True)
    (packet_root / "assets").mkdir(parents=True, exist_ok=True)
    (packet_root / "views").mkdir(parents=True, exist_ok=True)


def step1_convert_ledger(ledger_path: Path, agent_name: str) -> tuple[bool, str]:
    """Wrap a ledger .jsonl into an AEP packet."""
    packet_root = ledger_path.parent / f"{agent_name}.aepkg"
    if packet_root.exists():
        shutil.rmtree(packet_root)
    ensure_packet_skeleton(packet_root)
    if not ledger_path.exists():
        return False, f"ledger missing: {ledger_path}"

    rows = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    now_iso = utc_now_iso()

    # source = "agent ledger"
    sources = [{
        "id": f"src:{agent_name}-ledger",
        "type": "Source",
        "source_type": "in_packet_file",
        "title": f"{agent_name} agent ledger",
        "location": {"kind": "file", "value": "./data/ledger-rows.jsonl",
                     "location_hash": "sha256:" + sha256_hex(ledger_path.read_bytes())},
        "provenance_strength": "strong",
        "limits": [],
        "created_at": now_iso,
    }]
    write_jsonl(packet_root / "data" / "sources.jsonl", sources)

    # spans (one per ledger row)
    spans = []
    for i, row in enumerate(rows):
        spans.append({
            "id": f"span:row-{i:04d}",
            "type": "Span",
            "source_id": f"src:{agent_name}-ledger",
            "selector": {"line": i + 1},
            "quote_hash": "sha256:" + sha256_hex(
                json.dumps(row, sort_keys=True).encode("utf-8")
            ),
            "created_at": now_iso,
        })
    write_jsonl(packet_root / "data" / "spans.jsonl", spans)

    # claims (one per ledger row — outcome + cluster_tags + truth_tag)
    claims = []
    for i, row in enumerate(rows):
        truth_tag = row.get("truth_tag", "STRONGLY PLAUSIBLE")
        reliability = {
            "PROVEN/RELIABLE": "PROVEN_RELIABLE",
            "PROVEN_RELIABLE": "PROVEN_RELIABLE",
            "STRONGLY PLAUSIBLE": "STRONGLY_PLAUSIBLE",
            "STRONGLY_PLAUSIBLE": "STRONGLY_PLAUSIBLE",
            "EXPERIMENTAL": "EXPERIMENTAL",
            "SPECULATIVE FRONTIER": "SPECULATIVE_FRONTIER",
            "ASSUMPTION": "ASSUMPTION",
            "UNKNOWN": "UNKNOWN",
        }.get(truth_tag, "STRONGLY_PLAUSIBLE")
        axis_b = "GO" if row.get("outcome") in ("recovered", "shipped") else "EXPERIMENT"
        text = row.get("notes") or row.get("invocation") or f"{agent_name} ledger row {i}"
        claims.append({
            "id": f"claim:{agent_name}-row-{i:04d}",
            "type": "Claim",
            "reliability": reliability,
            "scope": "LOCAL_OBSERVATION",
            "axis_b_action": axis_b,
            "status": "active",
            "text": text[:500],
            "basis": [{"source_id": f"src:{agent_name}-ledger", "span_id": f"span:row-{i:04d}"}],
            "decision_time_revalidation_required": False,
            "semantic_stability": "stable",
            "created_at": row.get("date", now_iso),
        })
    write_jsonl(packet_root / "data" / "claims.jsonl", claims)

    # relations (empty)
    write_jsonl(packet_root / "data" / "relations.jsonl", [])

    # ops events
    write_jsonl(packet_root / "ops" / "events.jsonl", [{
        "id": "evt:001",
        "type": "WriteEvent",
        "event_type": "packet_created",
        "event_time": now_iso,
        "actor": "convert_ledgers_and_agents_to_aep.py",
        "target": "aepkg.json",
        "pre_state_hash": "sha256:" + sha256_hex(b""),
    }])

    # reviews + validations (empty)
    write_jsonl(packet_root / "reviews" / "reviews.jsonl", [])
    write_jsonl(packet_root / "validations" / "runs.jsonl", [])

    # Write canonicalized ledger rows (re-serialize each row to ensure strict-canonical)
    canonical_rows = []
    for r in rows:
        canonical_rows.append(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    (packet_root / "data" / "ledger-rows.jsonl").write_text(
        "\n".join(canonical_rows) + ("\n" if canonical_rows else ""),
        encoding="utf-8", newline="\n"
    )

    # Build manifest
    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": f"aepkg:{agent_name}-ledger",
        "packet_epoch": 1,
        "title": f"{agent_name} agent ledger",
        "created_at": now_iso,
        "created_by": "AEP-DEV convert_ledgers_and_agents_to_aep.py",
        "canonical_files": [
            "data/sources.jsonl",
            "data/spans.jsonl",
            "data/claims.jsonl",
            "data/relations.jsonl",
            "data/ledger-rows.jsonl",
            "ops/events.jsonl",
            "reviews/reviews.jsonl",
            "validations/runs.jsonl",
        ],
        "extensions": {
            "agent_name": agent_name,
            "ledger_row_count": len(rows),
            "original_path": str(ledger_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "",
            "manifest_hash": "",
            "assets_merkle_root": "",
        },
    }
    write_canonical(packet_root, manifest)
    return True, f"{len(rows)} rows wrapped"


def step2_agent_companion(agent_name: str) -> tuple[bool, str]:
    """Build AEP companion from .md + .html. KEEP .md, DELETE .html."""
    md_path = REPO_ROOT / ".claude" / "agents" / f"{agent_name}.md"
    html_path = REPO_ROOT / ".claude" / "agents" / f"{agent_name}.html"
    if not md_path.exists():
        return False, f"missing .md: {md_path}"
    packet_root = REPO_ROOT / ".claude" / "agents" / f"{agent_name}.aepkg"
    if packet_root.exists():
        shutil.rmtree(packet_root)
    ensure_packet_skeleton(packet_root)

    md_text = md_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    now_iso = utc_now_iso()

    # Parse YAML frontmatter from .md (Claude Code agent format)
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', md_text, re.DOTALL)
    frontmatter_raw = ""
    body = md_text
    if m:
        frontmatter_raw, body = m.group(1), m.group(2)

    # Extract structured fields from frontmatter
    fm_fields = {}
    for line in frontmatter_raw.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            fm_fields[key.strip()] = val.strip()

    # source = the agent definition
    sources = [{
        "id": f"src:{agent_name}-definition",
        "type": "Source",
        "source_type": "in_packet_file",
        "title": f"{agent_name} agent definition (canonical .md)",
        "location": {"kind": "file", "value": "./views/source.md",
                     "location_hash": "sha256:" + sha256_hex(md_path.read_bytes())},
        "provenance_strength": "strong",
        "limits": [],
        "created_at": now_iso,
    }]
    if html_path.exists():
        sources.append({
            "id": f"src:{agent_name}-rendered",
            "type": "Source",
            "source_type": "in_packet_file",
            "title": f"{agent_name} agent rendered view (pre-AEP)",
            "location": {"kind": "file", "value": "./assets/legacy-rendered.html",
                         "location_hash": "sha256:" + sha256_hex(html_path.read_bytes())},
            "provenance_strength": "strong",
            "limits": ["pre-AEP rendered form preserved for archival"],
            "created_at": now_iso,
        })
    write_jsonl(packet_root / "data" / "sources.jsonl", sources)

    # spans (one for frontmatter, one for body)
    spans = [
        {"id": "span:frontmatter", "type": "Span", "source_id": f"src:{agent_name}-definition",
         "selector": {"section": "frontmatter"},
         "quote_hash": "sha256:" + sha256_hex(frontmatter_raw.encode("utf-8")),
         "created_at": now_iso},
        {"id": "span:body", "type": "Span", "source_id": f"src:{agent_name}-definition",
         "selector": {"section": "body"},
         "quote_hash": "sha256:" + sha256_hex(body.encode("utf-8")),
         "created_at": now_iso},
    ]
    write_jsonl(packet_root / "data" / "spans.jsonl", spans)

    # claims (structured agent metadata)
    claims = []
    claims.append({
        "id": f"claim:{agent_name}-name",
        "type": "Claim", "reliability": "PROVEN_RELIABLE",
        "scope": "LOCAL_OBSERVATION", "axis_b_action": "GO", "status": "active",
        "text": f"agent name: {fm_fields.get('name', agent_name)}",
        "basis": [{"source_id": f"src:{agent_name}-definition", "span_id": "span:frontmatter"}],
        "decision_time_revalidation_required": False, "semantic_stability": "stable",
        "created_at": now_iso,
    })
    if "description" in fm_fields:
        claims.append({
            "id": f"claim:{agent_name}-description",
            "type": "Claim", "reliability": "PROVEN_RELIABLE",
            "scope": "GENERAL_CLAIM", "axis_b_action": "GO", "status": "active",
            "text": fm_fields["description"][:500],
            "basis": [{"source_id": f"src:{agent_name}-definition", "span_id": "span:frontmatter"}],
            "decision_time_revalidation_required": False, "semantic_stability": "stable",
            "created_at": now_iso,
        })
    if "tools" in fm_fields:
        claims.append({
            "id": f"claim:{agent_name}-tools",
            "type": "Claim", "reliability": "PROVEN_RELIABLE",
            "scope": "LOCAL_OBSERVATION", "axis_b_action": "GO", "status": "active",
            "text": f"tools: {fm_fields['tools']}",
            "basis": [{"source_id": f"src:{agent_name}-definition", "span_id": "span:frontmatter"}],
            "decision_time_revalidation_required": False, "semantic_stability": "stable",
            "created_at": now_iso,
        })
    if "model" in fm_fields:
        claims.append({
            "id": f"claim:{agent_name}-model",
            "type": "Claim", "reliability": "PROVEN_RELIABLE",
            "scope": "LOCAL_OBSERVATION", "axis_b_action": "GO", "status": "active",
            "text": f"model: {fm_fields['model']}",
            "basis": [{"source_id": f"src:{agent_name}-definition", "span_id": "span:frontmatter"}],
            "decision_time_revalidation_required": False, "semantic_stability": "stable",
            "created_at": now_iso,
        })
    claims.append({
        "id": f"claim:{agent_name}-canonical-md-hash",
        "type": "Claim", "reliability": "PROVEN_RELIABLE",
        "scope": "LOCAL_OBSERVATION", "axis_b_action": "GO", "status": "active",
        "text": f"canonical .md sha256: {sha256_hex(md_path.read_bytes())}",
        "basis": [{"source_id": f"src:{agent_name}-definition"}],
        "decision_time_revalidation_required": True, "semantic_stability": "stable",
        "created_at": now_iso,
    })
    write_jsonl(packet_root / "data" / "claims.jsonl", claims)
    write_jsonl(packet_root / "data" / "relations.jsonl", [])

    # ops + reviews + validations
    write_jsonl(packet_root / "ops" / "events.jsonl", [{
        "id": "evt:001", "type": "WriteEvent",
        "event_type": "packet_created", "event_time": now_iso,
        "actor": "convert_ledgers_and_agents_to_aep.py",
        "target": "aepkg.json",
        "pre_state_hash": "sha256:" + sha256_hex(b""),
    }])
    write_jsonl(packet_root / "reviews" / "reviews.jsonl", [])
    write_jsonl(packet_root / "validations" / "runs.jsonl", [])

    # views/ — byte-identical projection of the .md content
    (packet_root / "views" / "source.md").write_bytes(md_path.read_bytes())
    # Archive the original .html as asset (preserved, not load-bearing)
    if html_path.exists():
        (packet_root / "assets" / "legacy-rendered.html").write_bytes(html_path.read_bytes())

    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": f"aepkg:{agent_name}-agent",
        "packet_epoch": 1,
        "title": f"{agent_name} agent definition (AEP companion)",
        "created_at": now_iso,
        "created_by": "AEP-DEV convert_ledgers_and_agents_to_aep.py",
        "canonical_files": [
            "data/sources.jsonl",
            "data/spans.jsonl",
            "data/claims.jsonl",
            "data/relations.jsonl",
            "ops/events.jsonl",
            "reviews/reviews.jsonl",
            "validations/runs.jsonl",
        ],
        "extensions": {
            "agent_name": agent_name,
            "canonical_md_path": f".claude/agents/{agent_name}.md",
            "canonical_md_sha256": "sha256:" + sha256_hex(md_path.read_bytes()),
            "claude_code_loaded_file": f".claude/agents/{agent_name}.md",
            "aep_companion_role": "structured metadata + integrity envelope + queryable claims",
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "",
            "manifest_hash": "",
            "assets_merkle_root": "",
        },
    }
    write_canonical(packet_root, manifest)

    # Delete .html (superseded; preserved in assets/legacy-rendered.html)
    if html_path.exists():
        html_path.unlink()
        return True, f"{len(claims)} claims; .html deleted (preserved in assets/)"
    return True, f"{len(claims)} claims; no .html existed"


def main():
    overall_start = time.perf_counter()
    print("=" * 70)
    print("STEP 1 — Convert agent ledgers")
    print("=" * 70)
    ledgers_dir = REPO_ROOT / ".claude" / "agents" / "_ledgers"
    for agent in CANONICAL_AGENTS:
        ledger = ledgers_dir / f"{agent}.jsonl"
        if ledger.exists():
            ok, msg = step1_convert_ledger(ledger, agent)
            print(f"  {'OK' if ok else 'FAIL'}  {agent}-ledger: {msg}")
        else:
            print(f"  SKIP {agent}-ledger: file missing")

    print()
    print("=" * 70)
    print("STEP 2 — Build agent definition AEP companions (keep .md, delete .html)")
    print("=" * 70)
    for agent in CANONICAL_AGENTS:
        ok, msg = step2_agent_companion(agent)
        print(f"  {'OK' if ok else 'FAIL'}  {agent}: {msg}")

    elapsed = time.perf_counter() - overall_start
    print()
    print(f"Total time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
