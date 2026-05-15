"""views.py — Apache-2.0 — AEP v0.7-rc1 view derivation engine.

Implements visual-judge review cycle findings: deterministic view projections derived
from canonical AEP packet data. Three view types ship in v0.7-rc1:

  - views/claim-ledger.html — claim/source/span table view
  - views/integrity-tree.svg — Merkle tree visualization of state_hash + manifest_hash + assets_merkle_root
  - views/provenance-graph.mmd — Mermaid directed graph of claim→basis→source→span

View-determinism invariant: same canonical bytes → same view bytes. Both
Python verifier (this module) and TS verifier (SP-R8-02, staged) MUST produce
identical view bytes for the same packet. View hash is stored in
integrity.views_merkle_root (when present) for tamper detection.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# --- Helpers ----------------------------------------------------------------


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read JSONL file into list of dicts; skip blank/malformed lines."""
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _read_manifest(packet_root: Path) -> Dict[str, Any]:
    aepkg = packet_root / "aepkg.json"
    if aepkg.exists():
        return json.loads(aepkg.read_text(encoding="utf-8"))
    return {}


def _short_hash(h: str, n: int = 16) -> str:
    """Return shortened hash for display: 'sha256:abcd1234...wxyz'."""
    if not h:
        return ""
    if ":" in h:
        prefix, _, hex_part = h.partition(":")
        return f"{prefix}:{hex_part[:n]}…"
    return f"{h[:n]}…"


# --- Claim Ledger HTML (visual-judge Pattern 1) -----------------------------


def derive_claim_ledger_html(packet_root: Path) -> str:
    """Build deterministic HTML table from data/claims.jsonl + data/sources.jsonl + data/spans.jsonl.

    Returns the rendered HTML as a string. Sort order: claims by id lexicographic.
    No timestamps in output. View-determinism: same canonical bytes → same HTML bytes.
    """
    manifest = _read_manifest(packet_root)
    claims = sorted(_read_jsonl(packet_root / "data" / "claims.jsonl"), key=lambda c: c.get("id", ""))
    sources = {s.get("id", ""): s for s in _read_jsonl(packet_root / "data" / "sources.jsonl")}
    spans = {s.get("id", ""): s for s in _read_jsonl(packet_root / "data" / "spans.jsonl")}

    def esc(x: Any) -> str:
        return html.escape(str(x) if x is not None else "")

    rows: List[str] = []
    for c in claims:
        basis_html = ""
        basis = c.get("basis", [])
        if isinstance(basis, list):
            cites: List[str] = []
            for b in basis:
                if isinstance(b, dict):
                    if "claim_id" in b:
                        cites.append(f'<code>{esc(b["claim_id"])}</code>')
                    elif "source_id" in b:
                        s = sources.get(b["source_id"], {})
                        title = s.get("title", b["source_id"])
                        cites.append(f'<span title="{esc(b["source_id"])}">{esc(title)}</span>')
                    elif "span_id" in b:
                        cites.append(f'<code>{esc(b["span_id"])}</code>')
            basis_html = " · ".join(cites)
        rows.append(
            "<tr>"
            f"<td><code>{esc(c.get('id'))}</code></td>"
            f"<td>{esc(c.get('reliability'))}</td>"
            f"<td>{esc(c.get('axis_b_action'))}</td>"
            f"<td>{esc(c.get('scope'))}</td>"
            f"<td>{esc(c.get('status'))}</td>"
            f"<td>{esc(c.get('text', c.get('claim_text', '')))}</td>"
            f"<td>{basis_html}</td>"
            "</tr>"
        )

    packet_id = esc(manifest.get("packet_id", "<unknown>"))
    profile = esc(manifest.get("profile", ""))
    title = esc(manifest.get("title", ""))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        f"<title>AEP claim ledger — {packet_id}</title>\n"
        '<style>body{font-family:system-ui;max-width:1100px;margin:2em auto;padding:0 1em}'
        "table{border-collapse:collapse;width:100%;font-size:0.9em}"
        "th,td{border:1px solid #ccc;padding:0.4em;text-align:left;vertical-align:top}"
        "th{background:#f4f4f4}code{background:#f0f0f0;padding:1px 4px;border-radius:3px}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{title}</h1>\n"
        f"<p><strong>packet_id</strong>: <code>{packet_id}</code> · "
        f"<strong>profile</strong>: <code>{profile}</code> · "
        f"<strong>claims</strong>: {len(claims)} · "
        f"<strong>sources</strong>: {len(sources)} · "
        f"<strong>spans</strong>: {len(spans)}</p>\n"
        "<h2>Claim ledger</h2>\n"
        "<table>\n"
        "<thead><tr><th>id</th><th>reliability</th><th>axis_b</th><th>scope</th><th>status</th><th>text</th><th>basis</th></tr></thead>\n"
        "<tbody>\n"
        + "\n".join(rows)
        + "\n</tbody>\n</table>\n"
        '<p><em>Derived from canonical aepkg packet. Re-derivable via <code>python -m aep.views &lt;packet&gt;</code>.</em></p>\n'
        "</body>\n</html>\n"
    )


# --- Integrity Merkle-Tree SVG (visual-judge Pattern 2) ---------------------


def derive_integrity_tree_svg(packet_root: Path) -> str:
    """Build deterministic SVG of integrity envelope showing disjoint hash bases.

    Three rooted subtrees: state_hash (over data/*), manifest_hash (over aepkg.json
    minus manifest_hash field), assets_merkle_root (over assets/). Visible
    disjointness proves body/envelope split per §3.2.1.
    """
    manifest = _read_manifest(packet_root)
    integrity = manifest.get("integrity", {}) if isinstance(manifest.get("integrity"), dict) else {}
    canonical_files = manifest.get("canonical_files", [])

    def safe_short(key: str) -> str:
        return _short_hash(integrity.get(key, ""), 12)

    state_h = safe_short("state_hash")
    manifest_h = safe_short("manifest_hash")
    assets_h = safe_short("assets_merkle_root")
    context_h = safe_short("context_hash") if integrity.get("context_hash") else ""
    index_h = safe_short("index_hash") if integrity.get("index_hash") else ""

    width, height = 900, 520

    # Three columns: state | manifest | assets
    col_x = [200, 450, 700]
    root_y = 80

    # Render canonical_files leaves under state_hash
    leaves_state = sorted(canonical_files)
    leaves_assets: List[str] = []
    assets_dir = packet_root / "assets"
    if assets_dir.exists():
        for p in sorted(assets_dir.rglob("*")):
            if p.is_file():
                leaves_assets.append(str(p.relative_to(packet_root)).replace("\\", "/"))

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'viewBox="0 0 900 520" font-family="system-ui" font-size="11">\n'
    )
    parts.append('<style>'
                 '.body-node{fill:#dfecff;stroke:#3a6ea5}'
                 '.envelope-node{fill:#ffe6c7;stroke:#a06600}'
                 '.assets-node{fill:#d8f5d8;stroke:#3a7e3a}'
                 '.derived-node{fill:#eee;stroke:#999;stroke-dasharray:3,3}'
                 '.hash-text{font-family:monospace;font-size:10px;fill:#333}'
                 '.edge{stroke:#888;fill:none;stroke-width:1}'
                 'text{text-anchor:middle}'
                 '</style>\n')
    parts.append('<text x="450" y="20" font-weight="bold" font-size="14">AEP integrity envelope — §3.2.1 disjoint hash bases</text>\n')

    # Column headers
    parts.append(f'<text x="{col_x[0]}" y="50" font-weight="bold">BODY (data/*)</text>\n')
    parts.append(f'<text x="{col_x[1]}" y="50" font-weight="bold">ENVELOPE (aepkg.json)</text>\n')
    parts.append(f'<text x="{col_x[2]}" y="50" font-weight="bold">ASSETS</text>\n')

    # Root nodes
    parts.append(f'<rect class="body-node" x="{col_x[0]-90}" y="{root_y-15}" width="180" height="30" rx="4"/>')
    parts.append(f'<text x="{col_x[0]}" y="{root_y-2}">state_hash</text>')
    parts.append(f'<text class="hash-text" x="{col_x[0]}" y="{root_y+10}">{state_h}</text>')

    parts.append(f'<rect class="envelope-node" x="{col_x[1]-90}" y="{root_y-15}" width="180" height="30" rx="4"/>')
    parts.append(f'<text x="{col_x[1]}" y="{root_y-2}">manifest_hash</text>')
    parts.append(f'<text class="hash-text" x="{col_x[1]}" y="{root_y+10}">{manifest_h}</text>')

    parts.append(f'<rect class="assets-node" x="{col_x[2]-90}" y="{root_y-15}" width="180" height="30" rx="4"/>')
    parts.append(f'<text x="{col_x[2]}" y="{root_y-2}">assets_merkle_root</text>')
    parts.append(f'<text class="hash-text" x="{col_x[2]}" y="{root_y+10}">{assets_h}</text>')

    # Body leaves
    y = root_y + 60
    for leaf in leaves_state[:10]:
        parts.append(f'<rect class="body-node" x="{col_x[0]-90}" y="{y-12}" width="180" height="24" rx="3"/>')
        leaf_short = leaf if len(leaf) <= 26 else leaf[:11] + "…" + leaf[-12:]
        parts.append(f'<text x="{col_x[0]}" y="{y+4}">{leaf_short}</text>')
        parts.append(f'<line class="edge" x1="{col_x[0]}" y1="{root_y+15}" x2="{col_x[0]}" y2="{y-12}"/>')
        y += 32

    # Envelope sub-nodes (context_hash + index_hash derived)
    env_subs: List[Tuple[str, str]] = []
    if context_h:
        env_subs.append(("context_hash", context_h))
    if index_h:
        env_subs.append(("index_hash", index_h))
    env_subs.append(("canonical_files[]", f"{len(canonical_files)} entries"))
    env_subs.append(("packet_id", manifest.get("packet_id", "?")[:30]))
    yenv = root_y + 60
    for label, val in env_subs:
        parts.append(f'<rect class="derived-node" x="{col_x[1]-90}" y="{yenv-12}" width="180" height="24" rx="3"/>')
        parts.append(f'<text x="{col_x[1]}" y="{yenv}">{label}</text>')
        parts.append(f'<text class="hash-text" x="{col_x[1]}" y="{yenv+10}">{val}</text>')
        parts.append(f'<line class="edge" x1="{col_x[1]}" y1="{root_y+15}" x2="{col_x[1]}" y2="{yenv-12}"/>')
        yenv += 32

    # Assets leaves
    yas = root_y + 60
    if leaves_assets:
        for leaf in leaves_assets[:10]:
            parts.append(f'<rect class="assets-node" x="{col_x[2]-90}" y="{yas-12}" width="180" height="24" rx="3"/>')
            leaf_short = leaf if len(leaf) <= 26 else leaf[:11] + "…" + leaf[-12:]
            parts.append(f'<text x="{col_x[2]}" y="{yas+4}">{leaf_short}</text>')
            parts.append(f'<line class="edge" x1="{col_x[2]}" y1="{root_y+15}" x2="{col_x[2]}" y2="{yas-12}"/>')
            yas += 32
    else:
        parts.append(f'<rect class="assets-node" x="{col_x[2]-90}" y="{yas-12}" width="180" height="24" rx="3" opacity="0.4"/>')
        parts.append(f'<text x="{col_x[2]}" y="{yas+4}" opacity="0.6">(no assets)</text>')

    # Footer: invariant note
    parts.append('<text x="450" y="495" font-size="11" fill="#555">'
                 'Invariant §3.2.1: state_hash MUST NOT reference envelope fields (no self-reference circles)'
                 '</text>')
    parts.append("</svg>\n")
    return "".join(parts)


# --- Provenance Graph Mermaid (visual-judge Pattern 5) ----------------------


def derive_provenance_graph_mmd(packet_root: Path) -> str:
    """Build deterministic Mermaid directed-graph of claim→basis→source→span.

    Node order by id lexicographic. Edge ordering deterministic.
    """
    claims = sorted(_read_jsonl(packet_root / "data" / "claims.jsonl"), key=lambda c: c.get("id", ""))
    sources = sorted(_read_jsonl(packet_root / "data" / "sources.jsonl"), key=lambda s: s.get("id", ""))
    spans = sorted(_read_jsonl(packet_root / "data" / "spans.jsonl"), key=lambda s: s.get("id", ""))
    relations = sorted(_read_jsonl(packet_root / "data" / "relations.jsonl"), key=lambda r: r.get("id", ""))

    lines: List[str] = ["graph LR"]

    def nid(s: str) -> str:
        """Convert id to mermaid-safe node id."""
        return s.replace(":", "_").replace("-", "_").replace(".", "_").replace("/", "_")

    # Claim nodes (filled by reliability)
    rel_style = {
        "PROVEN_RELIABLE": "fill:#2ecc71,color:#fff",
        "STRONGLY_PLAUSIBLE": "fill:#27ae60,color:#fff",
        "PLAUSIBLE": "fill:#f1c40f",
        "EXPERIMENTAL": "fill:#e67e22,color:#fff",
        "ASSUMPTION": "fill:#95a5a6,color:#fff",
        "SPECULATIVE_FRONTIER": "fill:#9b59b6,color:#fff",
        "CONFLICTED": "fill:#e74c3c,color:#fff",
        "GOVERNANCE_RULE": "fill:#3498db,color:#fff",
        "DANGEROUS_NOT_WORTH_DOING": "fill:#c0392b,color:#fff",
        "UNKNOWN": "fill:#7f8c8d,color:#fff",
    }
    for c in claims:
        cid = c.get("id", "")
        label = (c.get("text", c.get("claim_text", "")) or cid)[:40]
        lines.append(f'  {nid(cid)}["{cid}<br/>{label}"]')
        style = rel_style.get(c.get("reliability", ""), "")
        if style:
            lines.append(f'  style {nid(cid)} {style}')

    # Source nodes (square)
    for s in sources:
        sid = s.get("id", "")
        title = (s.get("title", "") or sid)[:40]
        lines.append(f'  {nid(sid)}[("{title}")]')

    # Span nodes (rhombus)
    for sp in spans:
        sid = sp.get("id", "")
        lines.append(f'  {nid(sid)}{{"{sid}"}}')

    # Edges from claim.basis[] to source_id / claim_id / span_id
    for c in claims:
        cid = c.get("id", "")
        basis = c.get("basis", [])
        if isinstance(basis, list):
            for b in basis:
                if isinstance(b, dict):
                    if "source_id" in b:
                        lines.append(f'  {nid(cid)} -->|basis| {nid(b["source_id"])}')
                    elif "claim_id" in b:
                        lines.append(f'  {nid(cid)} -.->|cites| {nid(b["claim_id"])}')
                    elif "span_id" in b:
                        lines.append(f'  {nid(cid)} -->|span| {nid(b["span_id"])}')

    # Relation edges (dashed)
    for r in relations:
        subj = r.get("subject", "")
        obj = r.get("object", "")
        pred = r.get("predicate", r.get("relation_type", ""))[:20]
        if subj and obj:
            lines.append(f'  {nid(subj)} -.->|{pred}| {nid(obj)}')

    return "\n".join(lines) + "\n"


# --- View Determinism + Merkle root -----------------------------------------


def view_sha256(text: str) -> str:
    """Deterministic sha256 of view bytes (utf-8 encoded)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_all_views(packet_root: Path) -> Dict[str, Tuple[str, str]]:
    """Build all v0.7 view projections.

    Returns {filename: (content, sha256_hash)}.
    """
    claim_ledger = derive_claim_ledger_html(packet_root)
    integrity_tree = derive_integrity_tree_svg(packet_root)
    provenance_graph = derive_provenance_graph_mmd(packet_root)
    return {
        "views/claim-ledger.html": (claim_ledger, view_sha256(claim_ledger)),
        "views/integrity-tree.svg": (integrity_tree, view_sha256(integrity_tree)),
        "views/provenance-graph.mmd": (provenance_graph, view_sha256(provenance_graph)),
    }


def write_all_views(packet_root: Path) -> Dict[str, str]:
    """Write all v0.7 views into packet_root/views/. Returns {filename: hash}."""
    views = derive_all_views(packet_root)
    out_hashes: Dict[str, str] = {}
    views_dir = packet_root / "views"
    views_dir.mkdir(exist_ok=True)
    for rel, (content, h) in views.items():
        (packet_root / rel).write_text(content, encoding="utf-8", newline="\n")
        out_hashes[rel] = h
    return out_hashes


def views_merkle_root(packet_root: Path) -> str:
    """Compute deterministic Merkle root over view files.

    Concatenates sha256(content) for each view in sorted-relpath order, then
    hashes the concatenation. Returns "sha256:<hex>".
    """
    views = derive_all_views(packet_root)
    h = hashlib.sha256()
    for rel in sorted(views.keys()):
        h.update(views[rel][1].encode("utf-8"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


def verify_views(packet_root: Path) -> Tuple[bool, Dict[str, str]]:
    """Verify each views/*.{html,svg,mmd} file matches its deterministic re-derivation.

    Returns (all_match, {rel: 'OK' | 'MISMATCH' | 'MISSING'}).
    """
    views = derive_all_views(packet_root)
    out: Dict[str, str] = {}
    all_match = True
    for rel, (content, _) in views.items():
        target = packet_root / rel
        if not target.exists():
            out[rel] = "MISSING"
            all_match = False
            continue
        actual = target.read_text(encoding="utf-8")
        if actual == content:
            out[rel] = "OK"
        else:
            out[rel] = "MISMATCH"
            all_match = False
    return all_match, out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m aep.views <packet_root>")
        sys.exit(2)
    root = Path(sys.argv[1])
    hashes = write_all_views(root)
    for rel, h in hashes.items():
        print(f"  {rel}: {h}")
    merkle = views_merkle_root(root)
    print(f"  views_merkle_root: {merkle}")
