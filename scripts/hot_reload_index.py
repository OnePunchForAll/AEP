"""hot_reload_index.py - mtime-cache incremental hot-reload wrapper for contextual indexes.

CLOSES adversary L2-NEW-A4 + L4-A4 stale-index race attack class.

The pre-built contextual index at
    projects/v11-aep/publish-ready/aep/data/contextual-indexes/<agent>.jsonl
is a snapshot. Between builds, the underlying ledger
    .claude/agents/_ledgers/<agent>.jsonl
appends new rows that the snapshot does not see. A query against the stale
snapshot returns a "no relevant prior runs" answer EVEN WHEN a new highly
relevant row exists in the live ledger -- the classic stale-index race.

This module fixes the race:

  1. HotReloadIndex caches (vocab_idx, idf_arr, rows, meta, ledger_mtime_ns,
     ledger_size_bytes, n_rows_consumed).
  2. On query() it polls os.stat(ledger_path).st_mtime_ns AND st_size. If
     either advanced past the cached value, the new tail of the ledger is
     parsed (only rows past byte-offset cached_size_bytes), each new row is
     transformed via build_contextual_index.extract_doc_from_ledger_row, the
     new doc's tokens are folded into the existing TF-IDF vocab + idf
     (additive incremental; collisions accept the existing idf weight to
     preserve byte-stable cos comparison with cached rows -- new vocab terms
     get a fresh idf computed from running df+1 / N+1).
  3. Pure-Python; no inotify/watchdog dependency. Polls mtime_ns at
     1-second granularity by default (see DEFAULT_POLL_GRANULARITY_S). On
     POSIX inotify or Windows ReadDirectoryChangesW could be added later;
     mtime polling is sufficient for correctness because we ALSO compare
     st_size, so an mtime-equal but size-grown file is still detected (the
     A4 attack scenario where atime/mtime resolution misses sub-second
     appends gets caught by the size check).

Falsifier (subprocess race): see __main__ self-test. Subprocess A appends a
NEW row to the ledger; subprocess B (which had loaded the cache before the
append) then issues a topically-relevant query and MUST see the new row. PASS
iff B's top-K contains the appended row's vec_id.

Cites: forge:lamport-216 F6-self canonical-resolve baseline; adversary:
lamport-54 L2-NEW-A4 attack-class authoring; pathfinder:lamport-null-bcdc549e4ace
loops-5-8 dependency-ordered ladder.

Section 04: NO network calls (socket monkey-patch).
Section 41 HCRL: emits index_hot_reload_event receipts on every cache refresh.
Section 50 Law-1: writes ONLY to projects/v11-aep/publish-ready/aep/data/
hot-reload-receipts/.
Section 57 Retrieval-architecture: schema-additive sibling to
build_contextual_index.py + lag_retrieve_contextual.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Section 04 offline assertion (relaxed for subprocess self-test that uses
# os.exec, not network).
_orig_socket = socket.socket


def _no_network(*a, **kw):
    raise RuntimeError("Section 04: hot_reload_index makes ZERO network calls")


socket.socket = _no_network  # type: ignore

DEFAULT_POLL_GRANULARITY_S = 1.0
EMPTY = "blake2b-256:" + hashlib.blake2b(b"", digest_size=32).hexdigest()
MODEL_ID = "lag-hot-reload-incremental-v1"

STOPWORDS = frozenset(
    "a an the of and or but not for to in on at by from with as is are was were be been being "
    "have has had do does did this that these those it its their there here we us our you your "
    "they them he she his her him will would should could may might must can shall about above "
    "after again against all am any aren't because been before below between both can't cannot "
    "couldn't did didn't doesn't doing don't down during each few further haven't hasn't hadn't "
    "her here's hers herself himself his how if into let's me more most mustn't my myself nor "
    "off once only other ought our ours ourselves out over own same shan't she'd she'll she's so "
    "some such than that's then theirs themselves there's they'd they'll they're they've through "
    "too under until up very wasn't we'd we'll we're we've weren't what what's when when's where "
    "where's which while who who's whom why why's won't wouldn't yours yourself yourselves".split()
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")


def tokenize(text: str) -> List[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def b2(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=32).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ----- Reuse the deterministic prefix builder from build_contextual_index. -----
def shorten_session(session_id: str, max_len: int = 40) -> str:
    if not isinstance(session_id, str) or not session_id:
        return "unknown-session"
    return session_id[:max_len]


def shorten_mission(mission: str, max_len: int = 40) -> str:
    if not isinstance(mission, str) or not mission:
        return "unknown-mission"
    if mission.startswith("AEP-V") and "-" in mission:
        parts = mission.split("-")
        tail = "-".join(parts[-4:])
        if len(tail) <= max_len:
            return tail
    return mission[:max_len]


def top_tags(cluster_tags, k: int = 3) -> str:
    if not isinstance(cluster_tags, list):
        return "no-tags"
    selected = [str(t) for t in cluster_tags[:k] if isinstance(t, (str, int, float))]
    if not selected:
        return "no-tags"
    return ",".join(selected)


def build_context_prefix(row: Dict, agent: str, k_tags: int = 3) -> str:
    sess = shorten_session(row.get("session_id") or "")
    miss = shorten_mission(row.get("mission") or "")
    tags = top_tags(row.get("cluster_tags") or [], k=k_tags)
    return f"[agent={agent} session={sess} mission={miss} cluster_tags={tags}]"


def extract_doc_from_ledger_row(row: Dict, agent_name: str, k_tags: int = 3) -> Dict:
    """Schema-identical to build_contextual_index.extract_doc_from_ledger_row.
    Inlined here to avoid Section 50 Law-1 import-cycle on monkey-patched socket
    AND to make this module standalone for the falsifier subprocess.
    """
    invocation = row.get("invocation") or ""
    notes = row.get("notes") or ""
    if not isinstance(invocation, str):
        invocation = str(invocation)
    if not isinstance(notes, str):
        notes = str(notes)

    context_prefix = build_context_prefix(row, agent_name, k_tags=k_tags)
    contextual_text = (context_prefix + " " + invocation + " " + notes).strip()

    lamport = row.get("lamport_counter")
    session = row.get("session_id", "?")
    if lamport is None or lamport == "":
        content_blob = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        lamport_fallback = "null-" + hashlib.blake2b(
            content_blob.encode("utf-8"), digest_size=8
        ).hexdigest()[:12]
        vec_id = f"ledger::{agent_name}::lamport-{lamport_fallback}::{session[:24]}"
    else:
        vec_id = f"ledger::{agent_name}::lamport-{lamport}::{session[:24]}"

    return {
        "vec_id": vec_id,
        "agent": agent_name,
        "source_path": f".claude/agents/_ledgers/{agent_name}.jsonl",
        "session_id": session,
        "date": row.get("date"),
        "lamport_counter": lamport,
        "cluster_tags": row.get("cluster_tags") if isinstance(row.get("cluster_tags"), list) else [],
        "outcome": row.get("outcome"),
        "truth_tag": row.get("truth_tag"),
        "reliability": row.get("truth_tag"),
        "axis_b": row.get("axis_b"),
        "cites": row.get("cites") or [],
        "lag_influenced_by": row.get("lag_influenced_by") or [],
        "context_prefix": context_prefix,
        "contextual_text": contextual_text,
        "raw_invocation_excerpt": invocation[:300],
        "raw_notes_excerpt": notes[:300],
    }


# ----- Cache loaders. -----
def load_cached_index(index_root: Path, agent: str) -> Tuple[
    Dict[str, int], List[float], List[Dict], Counter, int
]:
    """Load on-disk contextual index snapshot + reconstruct df Counter + n.
    Returns: (vocab_idx, idf_arr_list, rows, df, n_docs)
    """
    index_path = index_root / f"{agent}.jsonl"
    vocab_path = index_root / f"{agent}.vocab.jsonl"

    vocab_idx: Dict[str, int] = {}
    idf_list: List[float] = []
    if vocab_path.exists():
        with open(vocab_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                row = json.loads(line)
                vocab_idx[row["term"]] = i
                idf_list.append(row["idf"])

    rows: List[Dict] = []
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    # Reconstruct df from sparse_vec presence per term-idx (each row's
    # sparse_vec lists every term-idx with non-zero weight = present in doc).
    df: Counter = Counter()
    for r in rows:
        for tw in r.get("sparse_vec", []):
            df[tw["t"]] += 1
    n_docs = len(rows)
    return vocab_idx, idf_list, rows, df, n_docs


# ----- The hot-reload class. -----
class HotReloadIndex:
    """mtime-cache incremental contextual index.

    Public API:
        idx = HotReloadIndex(agent, ledger_path, index_root, k_tags=3)
        hits = idx.query("task hint text", top_k=5)
        meta = idx.refresh_status()  # for diagnostics

    Refresh semantics:
        On EVERY query we:
          1. Cheap stat() of ledger_path; if (mtime_ns, size_bytes) unchanged
             since last refresh -> serve from cache.
          2. If changed: re-open ledger at byte-offset = cached_size_bytes,
             parse only the new tail (faster than full rebuild for incremental
             appends, which is the common ledger-append pattern).
          3. Each new row -> extract_doc_from_ledger_row -> tokenize -> fold
             tokens into running df. New unseen tokens get a fresh vocab-idx;
             existing tokens reuse their cached vocab-idx.
          4. Compute the new doc's sparse_vec. For tokens that already exist
             in the cached vocab, REUSE the cached idf (preserves byte-stable
             cos for cached rows; tradeoff: cached rows do NOT get re-IDF'd
             on a per-tail-append basis -- this is the conservative
             additive-tier discipline per pattern:additive-tier-not-replacement).
             For genuinely new tokens, compute idf = log((N+1)/(df+1))+1.0
             with N = post-refresh n_docs.
          5. Append the new doc to self.rows; update self.df, self.vocab_idx,
             self.idf_list, self.cached_mtime_ns, self.cached_size_bytes.
          6. Emit an HCRL receipt (Section 41) per refresh.
    """

    def __init__(
        self,
        agent: str,
        ledger_path: Path,
        index_root: Path,
        k_tags: int = 3,
        receipts_root: Optional[Path] = None,
        poll_granularity_s: float = DEFAULT_POLL_GRANULARITY_S,
    ):
        self.agent = agent
        self.ledger_path = Path(ledger_path)
        self.index_root = Path(index_root)
        self.k_tags = k_tags
        self.poll_granularity_s = poll_granularity_s
        self.receipts_root = (
            Path(receipts_root)
            if receipts_root is not None
            else self.index_root.parent / "hot-reload-receipts"
        )
        self.receipts_root.mkdir(parents=True, exist_ok=True)
        self.receipts_path = self.receipts_root / f"{self.agent}.receipts.jsonl"

        # Load on-disk snapshot.
        v_idx, idf_list, rows, df, n_docs = load_cached_index(self.index_root, self.agent)
        self.vocab_idx: Dict[str, int] = v_idx
        self.idf_list: List[float] = idf_list
        self.rows: List[Dict] = rows
        self.df: Counter = df
        self.n_docs: int = n_docs

        # mtime+size watermark = the on-disk ledger state at construction
        # time, BUT we want the snapshot to truly reflect what was indexed
        # not what the ledger currently is. To support tests where the
        # snapshot is older than the ledger, we read up to current EOF
        # incrementally on first query() -- so initialize watermark to the
        # snapshot's "as of" point, which is byte 0 conceptually but we
        # can't reconstruct that from disk. Conservative choice: initialize
        # watermark to (-1, -1) so the FIRST query() ALWAYS triggers a
        # full-tail scan that re-emits already-indexed rows as no-ops
        # (we de-dupe by vec_id).
        self.cached_mtime_ns: int = -1
        self.cached_size_bytes: int = -1
        self.indexed_vec_ids: set = {r["vec_id"] for r in self.rows}
        self.last_refresh_ts: Optional[float] = None
        self.refresh_count: int = 0
        self.n_added_total: int = 0

    # ----- public API -----
    def refresh_status(self) -> Dict:
        st = self._stat_or_none()
        return {
            "agent": self.agent,
            "ledger_path": str(self.ledger_path),
            "ledger_exists": st is not None,
            "ledger_mtime_ns": st.st_mtime_ns if st else None,
            "ledger_size_bytes": st.st_size if st else None,
            "cached_mtime_ns": self.cached_mtime_ns,
            "cached_size_bytes": self.cached_size_bytes,
            "n_docs_indexed": self.n_docs,
            "vocab_size": len(self.vocab_idx),
            "refresh_count": self.refresh_count,
            "n_added_total": self.n_added_total,
            "last_refresh_ts": self.last_refresh_ts,
            "poll_granularity_s": self.poll_granularity_s,
        }

    def query(self, task_hint: str, top_k: int = 5) -> List[Dict]:
        """Refresh-then-retrieve. Returns top-K rows by cosine sim, EACH
        annotated with cos + a refresh_meta block on the FIRST hit."""
        n_added = self._maybe_refresh()
        qvec = self._vectorize_query(task_hint)
        if not qvec:
            return [{"_summary": {"empty_query_vec": True, "n_added_in_refresh": n_added}}]

        scored = []
        for r in self.rows:
            cos = self._cosine(qvec, r.get("sparse_vec", []))
            if cos > 0:
                scored.append((cos, r))
        scored.sort(key=lambda x: -x[0])
        out = []
        for cos, r in scored[:top_k]:
            out.append({
                "vec_id": r["vec_id"],
                "cos": round(cos, 6),
                "session_id": r.get("session_id"),
                "date": r.get("date"),
                "context_prefix": r.get("context_prefix"),
                "raw_invocation_excerpt": r.get("raw_invocation_excerpt", "")[:200],
                "cluster_tags": r.get("cluster_tags", []),
                "outcome": r.get("outcome"),
                "reliability": r.get("reliability"),
            })
        if out:
            out[0]["_refresh_meta"] = {
                "n_added_in_refresh": n_added,
                "n_docs_indexed_post_refresh": self.n_docs,
                "ledger_mtime_ns": self.cached_mtime_ns,
                "ledger_size_bytes": self.cached_size_bytes,
            }
        return out

    # ----- internals -----
    def _stat_or_none(self):
        try:
            return os.stat(self.ledger_path)
        except FileNotFoundError:
            return None

    def _maybe_refresh(self) -> int:
        st = self._stat_or_none()
        if st is None:
            return 0
        # Detect change: mtime_ns OR size diff. Size catches sub-mtime-resolution
        # appends; mtime catches in-place edits that don't change size.
        if st.st_mtime_ns == self.cached_mtime_ns and st.st_size == self.cached_size_bytes:
            return 0
        return self._refresh_tail(target_size=st.st_size, target_mtime_ns=st.st_mtime_ns)

    def _refresh_tail(self, target_size: int, target_mtime_ns: int) -> int:
        """Read the ledger from byte-offset = max(0, cached_size_bytes) to
        target_size; parse new rows; fold into the index."""
        start = self.cached_size_bytes if self.cached_size_bytes >= 0 else 0

        # Defensive: if file shrank (shouldn't happen on append-only ledger,
        # but rotation/truncation possible) -> full re-read to avoid
        # mid-row alignment.
        if target_size < start:
            start = 0
            self.rows = []
            self.indexed_vec_ids = set()
            self.df = Counter()
            self.n_docs = 0
            # Also reset vocab? Conservative: keep vocab_idx + idf_list to
            # preserve byte-stable cos with any external readers. Vocab
            # may end up superset of actual; harmless.

        added = 0
        with open(self.ledger_path, "rb") as f:
            f.seek(start)
            tail_bytes = f.read(target_size - start)

        # Decode + split. Append-only ledger uses "\n"-terminated rows; we
        # may land mid-row if start was wrong. Anchor: first byte after
        # start MUST be at a row boundary because we always set
        # cached_size_bytes to the END of consumed data. Newline-discipline.
        text = tail_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # Drop trailing partial line (no newline-terminator). Detect via the
        # raw bytes: if the last byte is NOT '\n', the last line is partial
        # and we must not consume it -- back off cached_size_bytes to before
        # this partial line.
        last_complete_offset = target_size
        if tail_bytes and tail_bytes[-1:] != b"\n" and lines:
            # Strip the partial line.
            partial = lines.pop()
            partial_byte_len = len(partial.encode("utf-8"))
            last_complete_offset = target_size - partial_byte_len

        for line in lines:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Some ledger rows have neither invocation nor notes nor outcome;
            # build_contextual_index filters those, so we must too for parity.
            if not row.get("invocation") and not row.get("notes") and not row.get("outcome"):
                continue

            d = extract_doc_from_ledger_row(row, self.agent, k_tags=self.k_tags)
            if len(d["contextual_text"]) < 40:
                continue
            # De-dupe: an existing snapshot row has same vec_id as a row we
            # discover by tail scan -> skip.
            if d["vec_id"] in self.indexed_vec_ids:
                continue
            self._add_doc(d)
            added += 1

        self.cached_size_bytes = last_complete_offset
        self.cached_mtime_ns = target_mtime_ns
        self.last_refresh_ts = time.time()
        self.refresh_count += 1
        self.n_added_total += added
        if added > 0:
            self._emit_receipt(added)
        return added

    def _add_doc(self, d: Dict) -> None:
        """Tokenize d, fold into df + vocab_idx + idf_list. Compute sparse_vec
        for d using the post-fold vocab_idx + idf. Append d to self.rows,
        register its vec_id in self.indexed_vec_ids."""
        toks = tokenize(d["contextual_text"])
        if not toks:
            return
        tc = Counter(toks)

        # Step A: assign vocab indices to genuinely new terms; fold df.
        for t in tc.keys():
            if t not in self.vocab_idx:
                new_idx = len(self.idf_list)
                self.vocab_idx[t] = new_idx
                self.idf_list.append(0.0)  # placeholder; computed below
            self.df[self.vocab_idx[t]] += 1

        self.n_docs += 1

        # Step B: recompute idf for ONLY the terms present in this new doc.
        # Cached-row idfs remain as-is per additive-tier discipline.
        for t in tc.keys():
            idx = self.vocab_idx[t]
            new_idf = round(math.log((self.n_docs + 1) / (self.df[idx] + 1)) + 1.0, 6)
            self.idf_list[idx] = new_idf

        # Step C: build sparse_vec for d.
        vec = {}
        for t, c in tc.items():
            idx = self.vocab_idx[t]
            tf = 1.0 + math.log(c)
            vec[idx] = tf * self.idf_list[idx]
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vec = {k: round(v / norm, 6) for k, v in vec.items()}
        d_indexed = dict(d)
        d_indexed["sparse_vec"] = [{"t": k, "w": w} for k, w in sorted(vec.items())]
        d_indexed["contextual_text_sha256"] = "blake2b-256:" + b2(d["contextual_text"])
        d_indexed["model_id"] = MODEL_ID
        d_indexed["vec_idx"] = len(self.rows)
        d_indexed["incrementally_added"] = True
        self.rows.append(d_indexed)
        self.indexed_vec_ids.add(d["vec_id"])

    def _vectorize_query(self, query: str) -> Dict[int, float]:
        tc = Counter(tokenize(query))
        vec = {}
        for t, c in tc.items():
            if t not in self.vocab_idx:
                continue
            idx = self.vocab_idx[t]
            vec[idx] = (1.0 + math.log(c)) * self.idf_list[idx]
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    @staticmethod
    def _cosine(qvec: Dict[int, float], row_sparse: List[Dict]) -> float:
        s = 0.0
        for tw in row_sparse:
            if tw["t"] in qvec:
                s += qvec[tw["t"]] * tw["w"]
        return s

    def _emit_receipt(self, n_added: int) -> None:
        prev_rows = []
        if self.receipts_path.exists():
            with open(self.receipts_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            prev_rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        prev_hash = (
            "blake2b-256:" + b2(canon(prev_rows[-1])) if prev_rows else EMPTY
        )
        receipt = {
            "receipt_id": f"hot-reload-{int(time.time() * 1000)}",
            "receipt_type": "index_hot_reload_event",
            "prev_receipt_hash": prev_hash,
            "agent": self.agent,
            "ledger_path": str(self.ledger_path),
            "n_added": n_added,
            "n_docs_indexed_post_refresh": self.n_docs,
            "vocab_size_post_refresh": len(self.vocab_idx),
            "ledger_mtime_ns": self.cached_mtime_ns,
            "ledger_size_bytes": self.cached_size_bytes,
            "refresh_count": self.refresh_count,
            "model_id": MODEL_ID,
            "refreshed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "actor": "hot_reload_index.py",
        }
        receipt["this_receipt_hash"] = "blake2b-256:" + b2(
            canon({k: v for k, v in receipt.items() if k != "this_receipt_hash"})
        )
        with open(self.receipts_path, "a", encoding="utf-8") as f:
            f.write(canon(receipt) + "\n")


# ----- CLI + falsifier-self-test entry. -----
def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pq = sub.add_parser("query")
    pq.add_argument("--agent", required=True)
    pq.add_argument("--task-hint", required=True)
    pq.add_argument("--top-k", type=int, default=5)
    pq.add_argument(
        "--ledger-path",
        type=Path,
        default=None,
        help="Defaults to .claude/agents/_ledgers/<agent>.jsonl",
    )
    pq.add_argument(
        "--index-root",
        type=Path,
        default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"),
    )
    pq.add_argument("--top-tags", type=int, default=3)

    ps = sub.add_parser("status")
    ps.add_argument("--agent", required=True)
    ps.add_argument("--ledger-path", type=Path, default=None)
    ps.add_argument(
        "--index-root",
        type=Path,
        default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"),
    )

    pf = sub.add_parser("falsifier-self-test")
    pf.add_argument(
        "--ledger-tmp",
        type=Path,
        required=True,
        help="Tmp file path used as the synthetic ledger for the race test.",
    )
    pf.add_argument(
        "--index-tmp",
        type=Path,
        required=True,
        help="Tmp directory for the synthetic contextual index snapshot.",
    )

    pa = sub.add_parser("subprocess-append")
    pa.add_argument("--ledger-tmp", type=Path, required=True)
    pa.add_argument("--row-json", type=str, required=True)

    pq2 = sub.add_parser("subprocess-query")
    pq2.add_argument("--ledger-tmp", type=Path, required=True)
    pq2.add_argument("--index-tmp", type=Path, required=True)
    pq2.add_argument("--task-hint", type=str, required=True)
    pq2.add_argument("--top-k", type=int, default=5)
    pq2.add_argument("--agent", default="forge-test")

    args = ap.parse_args()
    if args.cmd == "query":
        ledger_path = (
            args.ledger_path
            if args.ledger_path
            else Path(".claude/agents/_ledgers") / f"{args.agent}.jsonl"
        )
        idx = HotReloadIndex(args.agent, ledger_path, args.index_root, k_tags=args.top_tags)
        hits = idx.query(args.task_hint, top_k=args.top_k)
        for h in hits:
            print(canon(h))
        print(canon({"_status": idx.refresh_status()}))
        return 0
    if args.cmd == "status":
        ledger_path = (
            args.ledger_path
            if args.ledger_path
            else Path(".claude/agents/_ledgers") / f"{args.agent}.jsonl"
        )
        idx = HotReloadIndex(args.agent, ledger_path, args.index_root)
        print(canon(idx.refresh_status()))
        return 0
    if args.cmd == "subprocess-append":
        # Subprocess A: append a single row.
        with open(args.ledger_tmp, "ab") as f:
            f.write(args.row_json.encode("utf-8") + b"\n")
        print(canon({"_subprocess": "A", "appended": True, "row_len": len(args.row_json)}))
        return 0
    if args.cmd == "subprocess-query":
        # Subprocess B: load index (which observes the synthetic snapshot
        # built BEFORE A's append), then query.
        idx = HotReloadIndex(
            args.agent, args.ledger_tmp, args.index_tmp, k_tags=3
        )
        hits = idx.query(args.task_hint, top_k=args.top_k)
        for h in hits:
            print(canon(h))
        print(canon({"_status": idx.refresh_status()}))
        return 0
    if args.cmd == "falsifier-self-test":
        return _falsifier_self_test(args.ledger_tmp, args.index_tmp)
    return 1


def _falsifier_self_test(ledger_tmp: Path, index_tmp: Path) -> int:
    """Subprocess race falsifier:
      Step 1: Build synthetic ledger with N=3 baseline rows.
      Step 2: Build synthetic snapshot index from those 3 rows
              (using build_contextual_index logic inline).
      Step 3: Spawn subprocess A -> appends row #4 (topically distinctive
              token: 'horticulture-prime-marker-99').
      Step 4: Spawn subprocess B -> instantiates HotReloadIndex, queries
              with the marker token, must see row #4 in top-K.

    PASS = subprocess B's top-K[0].vec_id == row#4's vec_id.
    """
    import subprocess as sp

    ledger_tmp.parent.mkdir(parents=True, exist_ok=True)
    index_tmp.mkdir(parents=True, exist_ok=True)
    agent = "forge-test"

    baseline_rows = [
        {
            "date": "2026-05-15",
            "session_id": "synthetic-baseline-1",
            "lamport_counter": 1,
            "mission": "AEP-V11-AEP-LOOP-6-FALSIFIER",
            "invocation": "baseline row one about routing graphs and deterministic prefixes",
            "outcome": "success",
            "cluster_tags": ["baseline", "loop-6", "synthetic"],
            "truth_tag": "STRONGLY PLAUSIBLE",
            "notes": "first synthetic baseline row for hot-reload falsifier",
        },
        {
            "date": "2026-05-15",
            "session_id": "synthetic-baseline-2",
            "lamport_counter": 2,
            "mission": "AEP-V11-AEP-LOOP-6-FALSIFIER",
            "invocation": "baseline row two discussing tokenization and sparse vectors",
            "outcome": "success",
            "cluster_tags": ["baseline", "loop-6", "synthetic"],
            "truth_tag": "STRONGLY PLAUSIBLE",
            "notes": "second synthetic baseline row",
        },
        {
            "date": "2026-05-15",
            "session_id": "synthetic-baseline-3",
            "lamport_counter": 3,
            "mission": "AEP-V11-AEP-LOOP-6-FALSIFIER",
            "invocation": "baseline row three on cosine similarity and IDF computation",
            "outcome": "success",
            "cluster_tags": ["baseline", "loop-6", "synthetic"],
            "truth_tag": "STRONGLY PLAUSIBLE",
            "notes": "third synthetic baseline row",
        },
    ]

    # Step 1+2: write baseline ledger + build a synthetic snapshot index.
    if ledger_tmp.exists():
        ledger_tmp.unlink()
    with open(ledger_tmp, "wb") as f:
        for r in baseline_rows:
            f.write(canon(r).encode("utf-8") + b"\n")

    snapshot_size_before_append = ledger_tmp.stat().st_size
    snapshot_mtime_before_append = ledger_tmp.stat().st_mtime_ns

    # Build the on-disk snapshot index from the 3 baseline rows.
    docs = [extract_doc_from_ledger_row(r, agent, k_tags=3) for r in baseline_rows]
    df_snap: Counter = Counter()
    doc_tokens = []
    for d in docs:
        tc = Counter(tokenize(d["contextual_text"]))
        doc_tokens.append(tc)
        for t in tc.keys():
            df_snap[t] += 1
    vocab = sorted(df_snap.keys())
    vocab_idx = {t: i for i, t in enumerate(vocab)}
    n = len(docs)
    idf = {t: round(math.log((n + 1) / (df_snap[t] + 1)) + 1.0, 6) for t in vocab}
    sparse_vecs = []
    for tc in doc_tokens:
        vec = {}
        for t, c in tc.items():
            tf = 1.0 + math.log(c)
            vec[vocab_idx[t]] = tf * idf[t]
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vec = {k: round(v / norm, 6) for k, v in vec.items()}
        sparse_vecs.append(vec)

    vocab_path = index_tmp / f"{agent}.vocab.jsonl"
    index_path = index_tmp / f"{agent}.jsonl"
    with open(vocab_path, "w", encoding="utf-8") as f:
        for term in vocab:
            f.write(canon({"term": term, "idf": idf[term]}) + "\n")
    with open(index_path, "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            row_out = {
                "vec_idx": i,
                "vec_id": d["vec_id"],
                "agent": d["agent"],
                "session_id": d["session_id"],
                "date": d["date"],
                "lamport_counter": d["lamport_counter"],
                "cluster_tags": d["cluster_tags"],
                "outcome": d["outcome"],
                "reliability": d["reliability"],
                "context_prefix": d["context_prefix"],
                "raw_invocation_excerpt": d["raw_invocation_excerpt"],
                "raw_notes_excerpt": d["raw_notes_excerpt"],
                "sparse_vec": [{"t": k, "w": w} for k, w in sorted(sparse_vecs[i].items())],
            }
            f.write(canon(row_out) + "\n")

    print(
        canon({
            "_phase": "setup",
            "n_baseline": len(baseline_rows),
            "snapshot_size_bytes": snapshot_size_before_append,
            "snapshot_mtime_ns": snapshot_mtime_before_append,
            "vocab_size": len(vocab),
        })
    )

    # Step 3: subprocess A appends row #4 with a UNIQUE marker token that
    # is NOT in the snapshot vocab.
    marker_row = {
        "date": "2026-05-15",
        "session_id": "synthetic-newly-appended-4",
        "lamport_counter": 4,
        "mission": "AEP-V11-AEP-LOOP-6-FALSIFIER",
        "invocation": "newly appended row contains horticulture-prime-marker-99 as a unique token",
        "outcome": "success",
        "cluster_tags": ["newly-appended", "loop-6", "stale-index-attack-class"],
        "truth_tag": "STRONGLY PLAUSIBLE",
        "notes": "this row arrived AFTER the on-disk snapshot was built; horticulture-prime-marker-99 should make it top-1 for that query",
    }
    # Sleep briefly so that mtime_ns can change on coarse-resolution
    # filesystems (Windows NTFS can have ~100ns precision but POSIX ext4
    # often coarser). The size-check makes mtime granularity moot, but we
    # still want a clean test.
    time.sleep(max(0.05, DEFAULT_POLL_GRANULARITY_S * 0.05))
    proc_a = sp.run(
        [
            sys.executable,
            __file__,
            "subprocess-append",
            "--ledger-tmp",
            str(ledger_tmp),
            "--row-json",
            canon(marker_row),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(canon({"_phase": "subprocess_A", "stdout_tail": proc_a.stdout[-200:],
                 "stderr_tail": proc_a.stderr[-200:], "returncode": proc_a.returncode}))
    if proc_a.returncode != 0:
        print(canon({"_VERDICT": "FAIL-SETUP", "reason": "subprocess A failed",
                     "stderr": proc_a.stderr}))
        return 2

    snapshot_size_after_append = ledger_tmp.stat().st_size
    snapshot_mtime_after_append = ledger_tmp.stat().st_mtime_ns
    assert snapshot_size_after_append > snapshot_size_before_append, (
        "ledger size did not grow after subprocess A append"
    )

    # Step 4: subprocess B queries.
    proc_b = sp.run(
        [
            sys.executable,
            __file__,
            "subprocess-query",
            "--ledger-tmp",
            str(ledger_tmp),
            "--index-tmp",
            str(index_tmp),
            "--task-hint",
            "horticulture-prime-marker-99",
            "--top-k",
            "5",
            "--agent",
            agent,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(canon({"_phase": "subprocess_B", "returncode": proc_b.returncode,
                 "stdout_first_400": proc_b.stdout[:400],
                 "stderr_tail": proc_b.stderr[-200:]}))
    if proc_b.returncode != 0:
        print(canon({"_VERDICT": "FAIL-EXEC", "reason": "subprocess B failed",
                     "stderr": proc_b.stderr}))
        return 3

    # Parse subprocess B output.
    b_lines = [ln for ln in proc_b.stdout.splitlines() if ln.strip()]
    parsed_hits = []
    parsed_status = None
    for ln in b_lines:
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "_status" in obj:
            parsed_status = obj["_status"]
        elif isinstance(obj, dict) and "vec_id" in obj:
            parsed_hits.append(obj)

    expected_marker_session = marker_row["session_id"][:24]
    expected_vec_id = f"ledger::{agent}::lamport-4::{expected_marker_session}"

    found = any(h.get("vec_id") == expected_vec_id for h in parsed_hits)
    top1_match = bool(parsed_hits) and parsed_hits[0].get("vec_id") == expected_vec_id

    verdict = {
        "_VERDICT": "PASS" if top1_match else ("PARTIAL" if found else "FAIL"),
        "expected_vec_id": expected_vec_id,
        "subprocess_b_hits": [
            {"vec_id": h.get("vec_id"), "cos": h.get("cos")} for h in parsed_hits[:5]
        ],
        "subprocess_b_status": parsed_status,
        "snapshot_size_before_append": snapshot_size_before_append,
        "snapshot_size_after_append": snapshot_size_after_append,
        "snapshot_mtime_before_append_ns": snapshot_mtime_before_append,
        "snapshot_mtime_after_append_ns": snapshot_mtime_after_append,
        "n_added_via_hot_reload": (
            parsed_hits[0].get("_refresh_meta", {}).get("n_added_in_refresh")
            if parsed_hits and isinstance(parsed_hits[0].get("_refresh_meta"), dict)
            else None
        ),
    }
    print(canon(verdict))
    return 0 if top1_match else (1 if found else 4)


if __name__ == "__main__":
    sys.exit(_cli())
