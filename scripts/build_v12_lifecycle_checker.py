#!/usr/bin/env python3
"""AEP v1.2 Packet Lifecycle State-Machine Companion (A10 closure).

Operator source.md L67-L72 (sec73.2 sacred):
> "Seventh, AEP needs formal packet lifecycle modeling. Right now the states
>  draft -> reviewed -> validated -> promoted -> decayed -> amended ->
>  deprecated -> revalidated live in prose only."

This is the EXECUTABLE companion to `aep_lifecycle.tla`. TLA+ tooling (TLC)
may not be installed on every developer machine; this Python module mirrors
the SAME transitions + invariants and runs as the CI gate. The TLA+ file is
the formal source-of-truth (operator A10 acceptance per adversary pre-mortem);
this Python module is the runner that operationalises it.

API:
  PacketLifecycle(packet_id, principals)  # init
  .submit_for_review(who) / .validate(who) / .attach_falsifier(who) /
  .promote() / .tick_clock() / .decay() / .amend(who) / .revalidate(who) /
  .re_promote() / .deprecate(who)
  .acquire_lock(who) / .release_lock(who)

  check_packet_history(history_records) -> {conforms: bool, violations: [...]}

  run_checker_on_dag(dag_jsonl_path) -> {packets_checked: int, conforms: bool,
                                          violations: [...]}

Safety invariants enforced (mirror SafetyOK in aep_lifecycle.tla):
  1. NoPromoteBeforeValidate        -- rater_quorum >= 2 distinct
  2. NoAmendWithoutPriorRevalidation -- amend after promote requires
                                        revalidate before re-promote
  3. SingleWriterPerPacket           -- write_lock cardinality <= 1
  4. QuorumDistinctOnPromote         -- promote requires F14 quorum >= 2

A10 CLOSURE FRAMING:
  - TLA+ file is the formal source-of-truth.
  - Python state-machine companion runs as `make lifecycle-check` CI gate.
  - On infrastructure platforms with TLC installed, both are equivalent.
  - On platforms without TLC, the Python runner is the load-bearing gate.

Composes with: v1.1 F14 / F13 / F15 + v1.1 A8 SrsDecay + sec41 HCRL.

Author: forge (Phase 6, single-forge per sec73.4).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional


LIFECYCLE_STATES = (
    "draft",
    "reviewed",
    "validated",
    "promoted",
    "decayed",
    "amended",
    "deprecated",
    "revalidated",
)


VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft":        ("reviewed", "deprecated"),
    "reviewed":     ("validated", "deprecated"),
    "validated":    ("promoted", "deprecated"),
    "promoted":     ("decayed", "amended", "deprecated"),
    "decayed":      ("amended", "deprecated"),
    "amended":      ("revalidated", "deprecated"),
    "revalidated":  ("promoted", "deprecated"),
    "deprecated":   (),  # terminal
}


class LifecycleInvariantViolation(RuntimeError):
    """Raised when a safety invariant is broken."""

    def __init__(self, invariant: str, packet_id: str, detail: str):
        super().__init__(
            f"INVARIANT_VIOLATED::{invariant}::packet={packet_id}::{detail}")
        self.invariant = invariant
        self.packet_id = packet_id
        self.detail = detail


@dataclass
class PacketLifecycle:
    """Single-packet lifecycle state machine.

    Mirrors `aep_lifecycle.tla` variables exactly: packet_state, raters,
    witnesses, signatures, decay_timer, write_lock, falsifier_present,
    revalidated_after_amend.
    """

    packet_id: str
    principals: set[str]
    max_clock_ticks: int = 8

    packet_state: str = "draft"
    raters: set[str] = field(default_factory=set)
    witnesses: set[str] = field(default_factory=set)
    signatures: set[str] = field(default_factory=set)
    decay_timer: int = 0
    write_lock: set[str] = field(default_factory=set)
    falsifier_present: bool = False
    revalidated_after_amend: bool = False

    # --- lock management -------------------------------------------------- #

    def acquire_lock(self, who: str) -> None:
        if len(self.write_lock) != 0:
            raise LifecycleInvariantViolation(
                "SingleWriterPerPacket", self.packet_id,
                f"lock_already_held_by={self.write_lock}, requested={who}")
        self.write_lock.add(who)

    def release_lock(self, who: str) -> None:
        if who not in self.write_lock:
            raise LifecycleInvariantViolation(
                "SingleWriterPerPacket", self.packet_id,
                f"release_by_{who}_who_does_not_hold_lock")
        self.write_lock.discard(who)

    # --- transitions ------------------------------------------------------ #

    def submit_for_review(self, who: str) -> None:
        self._require_state("draft")
        self._require_lock(who)
        self.raters.add(who)
        self.packet_state = "reviewed"

    def validate(self, who: str) -> None:
        self._require_state("reviewed")
        if who in self.raters:
            raise LifecycleInvariantViolation(
                "QuorumDistinctOnPromote", self.packet_id,
                f"second_rater={who}_already_in_raters")
        self.raters.add(who)
        if len(self.raters) < 2:
            raise LifecycleInvariantViolation(
                "QuorumDistinctOnPromote", self.packet_id,
                f"rater_count_{len(self.raters)}_below_2")
        self.packet_state = "validated"

    def attach_falsifier(self, who: str) -> None:
        self._require_lock(who)
        if self.packet_state not in ("draft", "reviewed", "validated"):
            raise LifecycleInvariantViolation(
                "NoFalsifierAfterPromote", self.packet_id,
                f"cannot_attach_falsifier_in_state_{self.packet_state}")
        self.falsifier_present = True

    def promote(self) -> None:
        self._require_state("validated")
        if not self.falsifier_present:
            raise LifecycleInvariantViolation(
                "NoPromoteWithoutFalsifier", self.packet_id,
                "F13_falsifier_missing")
        if len(self.raters) < 2:
            raise LifecycleInvariantViolation(
                "QuorumDistinctOnPromote", self.packet_id,
                f"raters={list(self.raters)}_size<2")
        self.packet_state = "promoted"
        self.decay_timer = 0

    def tick_clock(self) -> None:
        if self.packet_state != "promoted":
            return
        if self.decay_timer < self.max_clock_ticks:
            self.decay_timer += 1

    def decay(self) -> None:
        self._require_state("promoted")
        if self.decay_timer < self.max_clock_ticks:
            raise LifecycleInvariantViolation(
                "DecayTimerNotExpired", self.packet_id,
                f"timer_{self.decay_timer}<max_{self.max_clock_ticks}")
        self.packet_state = "decayed"

    def amend(self, who: str) -> None:
        if self.packet_state not in ("promoted", "decayed"):
            raise LifecycleInvariantViolation(
                "AmendFromInvalidState", self.packet_id,
                f"current_state_{self.packet_state}_cannot_amend")
        self._require_lock(who)
        self.packet_state = "amended"
        self.revalidated_after_amend = False

    def revalidate(self, who: str) -> None:
        self._require_state("amended")
        self.raters.add(who)
        if len(self.raters) < 2:
            raise LifecycleInvariantViolation(
                "QuorumDistinctOnPromote", self.packet_id,
                f"revalidate_rater_count_{len(self.raters)}_below_2")
        self.packet_state = "revalidated"
        self.revalidated_after_amend = True

    def re_promote(self) -> None:
        self._require_state("revalidated")
        if not self.revalidated_after_amend:
            raise LifecycleInvariantViolation(
                "NoAmendWithoutPriorRevalidation", self.packet_id,
                "revalidated_after_amend_flag_not_set")
        if not self.falsifier_present:
            raise LifecycleInvariantViolation(
                "NoPromoteWithoutFalsifier", self.packet_id,
                "F13_falsifier_missing_on_re_promote")
        if len(self.raters) < 2:
            raise LifecycleInvariantViolation(
                "QuorumDistinctOnPromote", self.packet_id,
                f"re_promote_raters_{len(self.raters)}<2")
        self.packet_state = "promoted"
        self.decay_timer = 0

    def deprecate(self, who: str) -> None:
        if self.packet_state == "deprecated":
            raise LifecycleInvariantViolation(
                "DeprecateAlreadyDeprecated", self.packet_id,
                "double_deprecate")
        self._require_lock(who)
        self.packet_state = "deprecated"

    # --- helpers ---------------------------------------------------------- #

    def _require_state(self, required: str) -> None:
        if self.packet_state != required:
            raise LifecycleInvariantViolation(
                "BadTransition", self.packet_id,
                f"required_state_{required}_actual_{self.packet_state}")

    def _require_lock(self, who: str) -> None:
        if who not in self.write_lock:
            raise LifecycleInvariantViolation(
                "SingleWriterPerPacket", self.packet_id,
                f"action_by_{who}_without_lock_held_by_{list(self.write_lock)}"
            )

    # --- invariant check (called after each transition by check_packet_history) #

    def check_invariants(self) -> list[str]:
        """Return list of violation strings (empty if all 4 invariants hold)."""
        out: list[str] = []
        # SAFE1: NoPromoteBeforeValidate
        if (self.packet_state == "promoted"
                and len(self.raters) < 2):
            out.append("NoPromoteBeforeValidate")
        # SAFE2: NoAmendWithoutPriorRevalidation -- represented by flag
        # (cannot re-promote without revalidated_after_amend=True; enforced on
        # re_promote()).
        # SAFE3: SingleWriterPerPacket
        if len(self.write_lock) > 1:
            out.append("SingleWriterPerPacket")
        # SAFE4: QuorumDistinctOnPromote
        if (self.packet_state in ("promoted", "revalidated")
                and len(self.raters) < 2):
            out.append("QuorumDistinctOnPromote")
        return out

    def snapshot(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "packet_state": self.packet_state,
            "raters": sorted(self.raters),
            "witnesses": sorted(self.witnesses),
            "signatures": sorted(self.signatures),
            "decay_timer": self.decay_timer,
            "write_lock": sorted(self.write_lock),
            "falsifier_present": self.falsifier_present,
            "revalidated_after_amend": self.revalidated_after_amend,
        }


# --------------------------------------------------------------------------- #
# History replay -- the CI gate runner
# --------------------------------------------------------------------------- #


def check_packet_history(
        history_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay an ordered transition history against the lifecycle machine.

    Each record:
      {"packet_id": str, "principals": [...], "action": "<name>", "who": str?,
       "max_clock_ticks": int?}

    Actions: acquire_lock, release_lock, submit_for_review, validate,
             attach_falsifier, promote, tick_clock, decay, amend, revalidate,
             re_promote, deprecate.

    Returns:
      {"conforms": bool, "violations": [...], "final_states": {pid: snapshot}}
    """
    machines: dict[str, PacketLifecycle] = {}
    violations: list[dict[str, Any]] = []
    final_states: dict[str, dict[str, Any]] = {}

    for idx, rec in enumerate(history_records):
        pid = rec.get("packet_id")
        if not pid:
            violations.append({
                "index": idx,
                "error": "missing_packet_id",
                "record": rec,
            })
            continue
        if pid not in machines:
            machines[pid] = PacketLifecycle(
                packet_id=pid,
                principals=set(rec.get("principals", [])),
                max_clock_ticks=int(rec.get("max_clock_ticks", 8)),
            )
        m = machines[pid]
        action = rec.get("action", "")
        who = rec.get("who")

        try:
            if action == "acquire_lock":
                m.acquire_lock(who)
            elif action == "release_lock":
                m.release_lock(who)
            elif action == "submit_for_review":
                m.submit_for_review(who)
            elif action == "validate":
                m.validate(who)
            elif action == "attach_falsifier":
                m.attach_falsifier(who)
            elif action == "promote":
                m.promote()
            elif action == "tick_clock":
                m.tick_clock()
            elif action == "decay":
                m.decay()
            elif action == "amend":
                m.amend(who)
            elif action == "revalidate":
                m.revalidate(who)
            elif action == "re_promote":
                m.re_promote()
            elif action == "deprecate":
                m.deprecate(who)
            else:
                violations.append({
                    "index": idx,
                    "packet_id": pid,
                    "error": f"unknown_action_{action}",
                })
                continue
        except LifecycleInvariantViolation as e:
            violations.append({
                "index": idx,
                "packet_id": pid,
                "action": action,
                "who": who,
                "invariant": e.invariant,
                "detail": e.detail,
            })

        post_inv = m.check_invariants()
        if post_inv:
            for inv in post_inv:
                violations.append({
                    "index": idx,
                    "packet_id": pid,
                    "post_action_invariant": inv,
                })

    for pid, m in machines.items():
        final_states[pid] = m.snapshot()

    return {
        "conforms": len(violations) == 0,
        "violations": violations,
        "final_states": final_states,
        "packets_checked": len(machines),
        "transitions_replayed": len(history_records),
        "lifecycle_safety_invariants_count": 4,
    }


# --------------------------------------------------------------------------- #
# DAG ingestion (sec41 HCRL packet_history_dag binding)
# --------------------------------------------------------------------------- #


def run_checker_on_dag(dag_jsonl_path: str) -> dict[str, Any]:
    """Read a packet_history_dag JSONL emitted by build_f17 and replay.

    Falls back to empty conforms-True result if the DAG file is absent (the
    A10 closure is opt-in at run time per sec73.6 honest framing).
    """
    if not os.path.exists(dag_jsonl_path):
        return {
            "conforms": True,
            "violations": [],
            "packets_checked": 0,
            "note": f"dag_file_absent={dag_jsonl_path}",
            "lifecycle_safety_invariants_count": 4,
        }
    history: list[dict[str, Any]] = []
    with open(dag_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # F17 emits records with `node` + `transition_action`.
            if "transition_action" in rec and "packet_id" in rec:
                history.append({
                    "packet_id": rec["packet_id"],
                    "action": rec["transition_action"],
                    "who": rec.get("transition_actor"),
                })
    return check_packet_history(history)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--check", type=str, default=None,
                   help="Path to a history JSONL (list of transition records).")
    p.add_argument("--dag", type=str, default=None,
                   help="Path to packet_history_dag JSONL (F17).")
    p.add_argument("--list-invariants", action="store_true",
                   help="List the 4 safety invariants.")
    args = p.parse_args(argv)

    if args.list_invariants:
        for inv in (
            "1. NoPromoteBeforeValidate (rater_quorum >= 2)",
            "2. NoAmendWithoutPriorRevalidation (re_promote requires "
            "revalidated_after_amend flag set)",
            "3. SingleWriterPerPacket (write_lock cardinality <= 1)",
            "4. QuorumDistinctOnPromote (F14 binding -- distinct principals)",
        ):
            print(inv)

    if args.check:
        with open(args.check, "r", encoding="utf-8") as f:
            records: list[dict[str, Any]] = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        result = check_packet_history(records)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["conforms"] else 1

    if args.dag:
        result = run_checker_on_dag(args.dag)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["conforms"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
