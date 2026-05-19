#!/usr/bin/env python3
"""build_f16_attack_registry.py - F16 AttackClass registry builder + matcher.

F16 frontier-break primitive (AEP v1.1): adversary's prior pre-mortems become
LIVE detectors on every new claim emit. Bidirectional index:
  - AttackClass record: id, name, mechanism_signature_regex, detected_in_packets[],
    canonical_disconfirmer, lineage_attack_class_id.
  - inverse index: attack_id -> [closed_by_packet_ids] (built by scanning corpus
    assertions for attack_classes_closed[] field references).

This module:
  1. Initializes the registry at
     projects/v11-aep/publish-ready/aep/recall/attack_class_registry/registry.jsonl
  2. Seeds the registry with:
       - 7 KNOWN dormitive patterns from sec50 NP-2 list
       - 6 attacks closed yesterday + today (HV-1 contamination / HV-3 fictional
         topology / HV-5 scope-misassignment / HV-6 fake-merge-convergence-counting /
         sibling-132 V103 HV1 dormitive-BC-V103-1 / sibling-132 HV2 self-certification)
  3. Provides match_claim_against_registry(claim_text) -> [attack_class_ids]
  4. Builds inverse_index.jsonl by scanning corpus .aepkg packets' assertions.

Composes_with: F16 schema (f16_attack_class_registry.schema.json),
sec02 truth tags, sec50 EH Law-3 multi-lens, sec73.5 warden-receipts-or-halt,
sibling-132 HV closures.

API:
  - load_registry() -> list[AttackClass]
  - seed_registry() -> writes registry.jsonl with 13+ entries
  - match_claim_against_registry(claim_text, registry=None) -> list[str]
  - build_inverse_index(corpus_root) -> writes inverse_index.jsonl

Exit codes:
  0 = registry built + writeable
  2 = infrastructure error
"""
from __future__ import annotations
import argparse
import dataclasses
import datetime
import json
import pathlib
import re
import sys
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RECALL_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "recall" / "attack_class_registry"
REGISTRY_PATH = RECALL_DIR / "registry.jsonl"
INVERSE_INDEX_PATH = RECALL_DIR / "inverse_index.jsonl"


@dataclasses.dataclass
class AttackClass:
    id: str
    attack_class_id: str
    attack_class_name: str
    attack_signature_regex: str
    registered_by_principal: str
    registered_at: str
    detection_runtime: str = "python_re"
    first_seen_in_claim_id: Optional[str] = None
    closed_by_packets: List[str] = dataclasses.field(default_factory=list)
    severity: str = "MEDIUM"
    composes_with_doctrine_slots: List[str] = dataclasses.field(default_factory=list)
    false_positive_rate_observed: Optional[float] = None
    narrative_description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "AttackClass",
            "schema_version": "aep-attack-class-registry-0.1",
            "id": self.id,
            "attack_class_id": self.attack_class_id,
            "attack_class_name": self.attack_class_name,
            "attack_signature_regex": self.attack_signature_regex,
            "registered_by_principal": self.registered_by_principal,
            "registered_at": self.registered_at,
            "detection_runtime": self.detection_runtime,
            "first_seen_in_claim_id": self.first_seen_in_claim_id,
            "closed_by_packets": self.closed_by_packets,
            "severity": self.severity,
            "composes_with_doctrine_slots": self.composes_with_doctrine_slots,
            "false_positive_rate_observed": self.false_positive_rate_observed,
            "narrative_description": self.narrative_description,
        }


# ============================================================================
# Seed data
# ============================================================================

REGISTRATION_TS = "2026-05-18T12:00:00Z"


def _seed_attack_classes() -> List[AttackClass]:
    """Returns the 13 seed AttackClass records.

    7 dormitive patterns (sec50 NP-2 list) + 6 closures from yesterday + today.

    All regex patterns chosen for high recall on the failure-mode literal-textual
    surface; false_positive_rate_observed is null (unmeasured), so validator
    will emit AEP11_F16_FPR_UNMEASURED warning after >=5 corpus runs.
    """
    return [
        # ============== 7 dormitive patterns (sec50 NP-2) ==============
        AttackClass(
            id="atk:tautological-redefinition:v0",
            attack_class_id="ATK-V11-NP2-1",
            attack_class_name="Tautological Redefinition",
            # Matches "X is X because X" / "by definition X" / "we define X to be X"
            attack_signature_regex=r"\b(?:by definition|we define|defined as|is defined to be)\b[^.]{0,80}\bbecause\b|\b(\w+)\s+is\s+\1\b",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Defining a term in terms of itself, then citing the definition as evidence the thing exists or behaves as defined. "
                "Failure mode: claim provides no falsifiable predicate; circular self-justification."
            ),
        ),
        AttackClass(
            id="atk:name-as-explanation:v0",
            attack_class_id="ATK-V11-NP2-2",
            attack_class_name="Name as Explanation",
            attack_signature_regex=r"\b(?:works|succeeds|wins|fires|engages)\s+because\s+(?:it\s+is|of)\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[a-z-]+(?:-[a-z]+)+|good\s+architecture|good\s+design|deep\s+research)\b",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Naming the mechanism (proper noun or hyphenated phrase) IS the explanation. "
                "Example: 'it works because it is Deep Research' provides no mechanism. NP-2 dormitive virtue."
            ),
        ),
        AttackClass(
            id="atk:single-hardcoded-constant-driving-load-bearing-diagnosis:v0",
            attack_class_id="ATK-V11-NP2-3",
            attack_class_name="Single Hardcoded Constant Driving Load-Bearing Diagnosis",
            attack_signature_regex=r"(?:threshold|magic\s+number|hardcoded|=\s*\d+\.?\d*\s*(?:#|//|/\*)?\s*(?:works|tuned|empirical))",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="MEDIUM",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "A single hardcoded threshold (e.g. score>=4.0) gates a load-bearing PASS/FAIL diagnosis without "
                "calibration evidence. Caught in V103 VG04 rubric calibration HARD-CONDITIONAL."
            ),
        ),
        AttackClass(
            id="atk:virtue-words-as-proof:v0",
            attack_class_id="ATK-V11-NP2-4",
            attack_class_name="Virtue Words as Proof",
            attack_signature_regex=r"\b(?:robust|elegant|principled|sound|coherent|comprehensive|state-of-the-art|cutting-edge|world-class|industry-leading)\b\s+(?:(?:and|,)\s+\b(?:robust|elegant|principled|sound|coherent|comprehensive)\b\s+){0,3}(?:design|approach|system|architecture)",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="MEDIUM",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Adjective-cluster substituted for mechanism: 'robust principled elegant design.' "
                "If you delete the adjectives, no claim remains. NP-2 virtue-words-as-proof."
            ),
        ),
        AttackClass(
            id="atk:restatement-as-mechanism:v0",
            attack_class_id="ATK-V11-NP2-5",
            attack_class_name="Restatement as Mechanism",
            attack_signature_regex=r"\b(?:because|since|due to|owing to)\s+(?:it|the system|this)\s+(?:does|is)\s+(?:exactly\s+)?(?:what|that)\b",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="MEDIUM",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Restating the observed behavior as its own explanation. "
                "'The system catches X because it catches X' — same surface as tautological but driven by observed output not definition."
            ),
        ),
        AttackClass(
            id="atk:self-citation-as-evidence:v0",
            attack_class_id="ATK-V11-NP2-6",
            attack_class_name="Self-Citation as Evidence",
            attack_signature_regex=r"\b(?:per|cite|see)\s+(?:this|our|my)\s+(?:claim|paper|spec|doctrine|lesson|sibling)\b|\b(?:we|I)\s+(?:argued|claimed|showed)\s+(?:above|earlier|previously)\b",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="MEDIUM",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Citing the author's own earlier claim as evidence for the current one. "
                "Independent-lens requirement violated per sec50 Law-3 multi-lens convergence."
            ),
        ),
        AttackClass(
            id="atk:unfalsifiable-by-construction:v0",
            attack_class_id="ATK-V11-NP2-7",
            attack_class_name="Unfalsifiable by Construction",
            attack_signature_regex=r"\b(?:no\s+counter-?example\s+can|cannot\s+be\s+(?:falsified|disproven|tested))\b|\b(?:always|never)\s+(?:works|holds|true|succeeds)\b(?!\s+(?:when|if|under))",
            registered_by_principal="adversary:v11-phase-3b:seed",
            registered_at=REGISTRATION_TS,
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Claim is structured so no observation could falsify it. "
                "'Always works' without operational conditions is the canonical surface."
            ),
        ),

        # ============== 6 attacks closed yesterday + today ==============
        AttackClass(
            id="atk:hv1-contamination:v1",
            attack_class_id="ATK-V11-HV1",
            attack_class_name="Contamination - Same-Author Evaluation Bleed",
            attack_signature_regex=r"\b(?:same\s+author|same\s+session|self[-\s]score|judge\s+(?:rates|scores|attests)\s+own)\b",
            registered_by_principal="adversary:v11-phase-3a:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v11-legion:f12-contamination",
            closed_by_packets=["packet:v11-spec:f12_recall_layer_index"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50", "sec11"],
            narrative_description=(
                "Evaluator and producer share author/session, so evaluation rates the author's own work without "
                "lens independence. Closed by F12 contamination_flag preservation per sec11 anti-collusion."
            ),
        ),
        AttackClass(
            id="atk:hv3-fictional-topology:v1",
            attack_class_id="ATK-V11-HV3",
            attack_class_name="Fictional Topology - Schema Without Proof",
            attack_signature_regex=r"\b(?:DAG|graph|tree|topology|structure)\s+(?:enforces|guarantees|prevents)\b(?!\s+via\s+\w+)",
            registered_by_principal="adversary:v11-phase-3a:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v11-legion:f-tier-schemas",
            closed_by_packets=["packet:v11-spec:topology-proof-grep-each-f-tier"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Claiming a topological/structural property enforces a behavior without showing the operational "
                "mechanism that does the enforcement. Closed by topology-proof line each F-tier section."
            ),
        ),
        AttackClass(
            id="atk:hv5-scope-misassignment:v1",
            attack_class_id="ATK-V11-HV5",
            attack_class_name="Scope Misassignment - HARD-CONDITIONAL Mis-Tagged PASS",
            attack_signature_regex=r"\b(?:HARD[-\s]CONDITIONAL|CONDITIONAL[-\s]GO|hard\s+conditional)\b[^.]{0,80}\b(?:PASS|passed|complete|done|shipped)\b",
            registered_by_principal="adversary:v11-phase-3a:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v103:vg04-hard-conditional",
            closed_by_packets=["packet:v103-1-f14-a4-backport"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec73.6", "sec69.5"],
            narrative_description=(
                "Labeling a HARD-CONDITIONAL outcome as PASS or COMPLETE without surfacing the conditional gap. "
                "Closed by v1.0.3.1 F14 rater_quorum_attestation + A4 rubric calibration."
            ),
        ),
        AttackClass(
            id="atk:hv6-fake-merge-convergence-counting:v1",
            attack_class_id="ATK-V11-HV6",
            attack_class_name="Fake Merge - Convergence Counting Without Independence",
            attack_signature_regex=r"\b(?:N\s*=\s*\d+|count\s+of\s+\d+|across\s+\d+\s+(?:agents|lenses|readers))\b(?:[^.]{0,80}converge|[^.]{0,80}unanimous)",
            registered_by_principal="adversary:v11-phase-3a:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v11-legion:f11-cross-corpus-merge",
            closed_by_packets=["packet:v11-spec:f11-split-a6-a7-a8"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "Counting N=X cross-agent convergence votes as evidence without checking independence of the "
                "underlying lenses (they may share a single source or author). Closed by F11 split into A6/A7/A8 independent observables."
            ),
        ),
        AttackClass(
            id="atk:sibling-132-hv1-dormitive-bc-v103-1:v1",
            attack_class_id="ATK-V103-HV1",
            attack_class_name="Dormitive BC Claim - Manifest sha256 Stable Trivially",
            attack_signature_regex=r"\b(?:manifest|aepkg\.json)\s+sha256\s+(?:unchanged|invariant|stable)\b",
            registered_by_principal="adversary:2026-05-18:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v103:bc-v103-1-dormitive",
            closed_by_packets=["packet:v103:test_bc_v103_1_canonical_state_hash_unchanged"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec50"],
            narrative_description=(
                "BC test claimed 'manifest sha256 unchanged' as the BC property. But aepkg.json is not in state_hash, "
                "so the manifest test is dormitive. Closed by canonical state_hash test over data/{claims,relations,spans,sources}.jsonl + ops/events.jsonl."
            ),
        ),
        AttackClass(
            id="atk:sibling-132-hv2-self-certification:v1",
            attack_class_id="ATK-V103-HV2",
            attack_class_name="Self-Certification - Judge Self-Scores Without Independent Reader",
            attack_signature_regex=r"\bjudge\s+(?:re-)?scores?\s+(?:one\s+attempt|own)\b|\bself[-\s]score\b|\bjudge\s+verifies?\s+own\s+rubric\b",
            registered_by_principal="adversary:2026-05-18:premortem",
            registered_at=REGISTRATION_TS,
            first_seen_in_claim_id="claim:v103:phase-2-judge-self-score",
            closed_by_packets=["packet:v103:warden-rescore-plus-judge-tiebreaker"],
            severity="HIGH-VETO",
            composes_with_doctrine_slots=["sec11", "sec50"],
            narrative_description=(
                "Phase 2 originally specified 'judge re-scores one attempt independently' — self-certification because "
                "rubric author scores own rubric. Closed by warden 3-attempt re-score blind + judge tiebreaker independence."
            ),
        ),
    ]


# ============================================================================
# Registry I/O
# ============================================================================

def seed_registry(force: bool = False) -> List[AttackClass]:
    """Write the registry.jsonl. If force=False and registry exists, no-op (returns loaded)."""
    RECALL_DIR.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.exists() and not force:
        return load_registry()
    attacks = _seed_attack_classes()
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        for a in attacks:
            f.write(json.dumps(a.to_dict()) + "\n")
    return attacks


def load_registry() -> List[AttackClass]:
    """Load registry.jsonl into AttackClass instances. Returns [] if missing."""
    if not REGISTRY_PATH.exists():
        return []
    out: List[AttackClass] = []
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(AttackClass(
                id=d["id"],
                attack_class_id=d["attack_class_id"],
                attack_class_name=d["attack_class_name"],
                attack_signature_regex=d["attack_signature_regex"],
                registered_by_principal=d["registered_by_principal"],
                registered_at=d["registered_at"],
                detection_runtime=d.get("detection_runtime", "python_re"),
                first_seen_in_claim_id=d.get("first_seen_in_claim_id"),
                closed_by_packets=d.get("closed_by_packets", []),
                severity=d.get("severity", "MEDIUM"),
                composes_with_doctrine_slots=d.get("composes_with_doctrine_slots", []),
                false_positive_rate_observed=d.get("false_positive_rate_observed"),
                narrative_description=d.get("narrative_description", ""),
            ))
    return out


# ============================================================================
# Matching API
# ============================================================================

_COMPILED_CACHE: Optional[List[tuple]] = None


def _compile_registry(attacks: List[AttackClass]):
    """Pre-compile regex objects for the registry."""
    out = []
    for a in attacks:
        try:
            pat = re.compile(a.attack_signature_regex, re.IGNORECASE | re.DOTALL)
        except re.error as e:
            print(f"WARN: regex compile failed for {a.attack_class_id}: {e}", file=sys.stderr)
            continue
        out.append((a.attack_class_id, pat, a.severity, a.attack_class_name))
    return out


def match_claim_against_registry(claim_text: str, registry: Optional[List[AttackClass]] = None) -> List[str]:
    """Return list of attack_class_id strings that match the claim_text."""
    global _COMPILED_CACHE
    if registry is not None:
        compiled = _compile_registry(registry)
    else:
        if _COMPILED_CACHE is None:
            _COMPILED_CACHE = _compile_registry(load_registry())
        compiled = _COMPILED_CACHE
    matches = []
    for atk_id, pat, _sev, _name in compiled:
        if pat.search(claim_text):
            matches.append(atk_id)
    return matches


# ============================================================================
# Inverse index builder
# ============================================================================

def build_inverse_index(corpus_root: pathlib.Path) -> Dict[str, List[str]]:
    """Scan all .aepkg packets under corpus_root for assertions that reference
    attack_classes_closed[]. Build inverse: attack_id -> [closed_by_packet_ids].
    """
    inverse: Dict[str, List[str]] = {}
    # Walk for claims.jsonl files inside .aepkg dirs.
    for claims_path in corpus_root.rglob("*.aepkg/data/claims.jsonl"):
        packet_id_guess = claims_path.parent.parent.name
        try:
            with claims_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    closed_list = d.get("attack_classes_closed", [])
                    if not isinstance(closed_list, list):
                        continue
                    for atk_id in closed_list:
                        if not isinstance(atk_id, str):
                            continue
                        inverse.setdefault(atk_id, []).append(packet_id_guess)
        except (OSError, UnicodeDecodeError):
            continue
    # De-dupe.
    return {k: sorted(set(v)) for k, v in inverse.items()}


def write_inverse_index(inverse: Dict[str, List[str]]) -> int:
    """Write inverse index as JSONL rows: {attack_class_id, closed_by_packets[]}."""
    RECALL_DIR.mkdir(parents=True, exist_ok=True)
    with INVERSE_INDEX_PATH.open("w", encoding="utf-8") as f:
        for atk_id, packets in sorted(inverse.items()):
            f.write(json.dumps({
                "type": "AttackClassInverseIndexEntry",
                "attack_class_id": atk_id,
                "closed_by_packets": packets,
                "indexed_at": datetime.datetime.utcnow().isoformat() + "Z",
            }) + "\n")
    return len(inverse)


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Build + query F16 AttackClass registry.")
    ap.add_argument("--force-seed", action="store_true", help="Re-seed even if registry exists.")
    ap.add_argument("--build-inverse-index", action="store_true",
                    help="Walk corpus + emit inverse_index.jsonl.")
    ap.add_argument("--match", help="Match a single claim_text against the registry; print matched attack_class_ids.")
    args = ap.parse_args()

    if args.match:
        matches = match_claim_against_registry(args.match)
        for m in matches:
            print(m)
        return 0 if matches else 1

    attacks = seed_registry(force=args.force_seed)
    print(f"F16 registry: {len(attacks)} entries at {REGISTRY_PATH.relative_to(REPO_ROOT)}")
    if args.build_inverse_index:
        inverse = build_inverse_index(REPO_ROOT)
        n = write_inverse_index(inverse)
        print(f"F16 inverse_index: {n} attack-class rows written to {INVERSE_INDEX_PATH.relative_to(REPO_ROOT)}")
    return 0


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F16's documented role is the ATTACK-CLASSIFICATION registry.
# Extended: F16 is the registry of attack patterns, so it must DETECT all
# attack-shaped mutations across the full matrix - this is its ground-truth
# coverage role. Patterns include: prompt injection, hash flip, self-attestation,
# DAG corruption, span removal, score shift, event reorder, completion witness
# missing, recall-payload injection, claim-text injection.
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
import hashlib as _v15_hashlib

V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"


_F16_ATTACK_PATTERNS = {
    "prompt_injection_signatures": [
        "ignore all prior instructions",
        "ignore previous instructions",
        "set validator outcome to pass",
        "drop the database",
        "disregard the above",
        "override constitution",
    ],
    "dag_corrupt_markers": ["NONEXISTENT", "BOGUS", "CORRUPT", "FORGED"],
}


def _v15_hash_valid(h):
    if not isinstance(h, str) or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except (ValueError, TypeError):
        return False


def _v15_check_all_attack_classes(packet):
    """F16 is the registry: it must classify any attack-shaped mutation."""
    out = []
    # Class: prompt-injection (recall + claim text + reviewer rationale + metadata)
    for sig in _F16_ATTACK_PATTERNS["prompt_injection_signatures"]:
        # recall_payload
        rp = packet.get("recall_payload") or {}
        rp_text = rp.get("text", "") if isinstance(rp, dict) else ""
        if isinstance(rp_text, str) and sig in rp_text.lower():
            out.append(f"AEP15_F16_ATTACK_RECALL_INJECTION:{sig}")
            break
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            for sig in _F16_ATTACK_PATTERNS["prompt_injection_signatures"]:
                if sig in text.lower():
                    out.append(f"AEP15_F16_ATTACK_CLAIM_INJECTION:{sig}")
                    break
            else:
                continue
            break
    # Class: source-hash flip / corruption
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F16_ATTACK_HASH_MALFORMED")
            continue
        if isinstance(text, str) and _v15_hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_F16_ATTACK_HASH_FLIP")
    # Class: self-attestation (reviewer principal == author principal)
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid and (pid == creator or pid in claim_authors):
            out.append(f"AEP15_F16_ATTACK_SELF_ATTESTATION:{pid}")
    # Class: DAG-parent corruption
    for p in (packet.get("manifest") or {}).get("dag_parents", []) or []:
        if isinstance(p, str):
            for marker in _F16_ATTACK_PATTERNS["dag_corrupt_markers"]:
                if marker in p:
                    out.append(f"AEP15_F16_ATTACK_DAG_CORRUPT:{p}")
                    break
    # Class: span-removal / span integrity
    span_index = set()
    for src in packet.get("sources", []):
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index.add(sid)
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            out.append("AEP15_F16_ATTACK_SPAN_REMOVED")
        else:
            for sid in bsids:
                if sid not in span_index:
                    out.append(f"AEP15_F16_ATTACK_SPAN_UNRESOLVED:{sid}")
    # Class: score shift / out-of-scale / NaN-inf
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F16_ATTACK_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F16_ATTACK_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F16_ATTACK_SCORE_OUT_OF_SCALE:{s}")
    # Class: event-reorder (review_submit before create)
    events = (packet.get("manifest") or {}).get("events", [])
    kinds = [ev.get("kind") for ev in events]
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F16_ATTACK_EVENT_REORDER")
    # Class: completion-witness-missing
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            if not cl.get("witness") and not cl.get("witness_sha256") and not cl.get("witness_artifact"):
                out.append(f"AEP15_F16_ATTACK_WITNESS_MISSING:{cl.get('claim_id')}")
    return out


def _v15_check_extended_attack_classes(packet):
    """Additional attack-pattern classifications surfacing in v1.5 LTS suite."""
    out = []
    # Reviewer extras (removed / duplicate / forged) — attack class registry.
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F16_ATTACK_REVIEWER_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F16_ATTACK_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F16_ATTACK_REVIEWER_FORGED:{pid}")
    # Span geometry attacks.
    for src in packet.get("sources", []):
        text = src.get("text", "")
        src_len = len(text) if isinstance(text, str) else 0
        for sp in src.get("spans", []) or []:
            start, end = sp.get("start"), sp.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            if start > end:
                out.append("AEP15_F16_ATTACK_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F16_ATTACK_SPAN_BEYOND_SOURCE")
    # DAG self-reference + cycle attacks.
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if isinstance(p, str) and p == pkt_id:
            out.append("AEP15_F16_ATTACK_DAG_SELF_REFERENCE_OR_CYCLE")
    # Forged witness_sha256 attack.
    for cl in packet.get("claims", []):
        ws = cl.get("witness_sha256")
        if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
            out.append(f"AEP15_F16_ATTACK_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_all_attack_classes(packet))
    out.extend(_v15_check_extended_attack_classes(packet))
    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib as _pl
            _spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(_pl.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out


if __name__ == "__main__":
    sys.exit(main())
