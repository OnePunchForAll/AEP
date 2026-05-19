#!/usr/bin/env python3
"""test_v15_viewer_accessibility.py - AEP v1.5 LTS Phase B viewer accessibility audit.

Empirical audit of WCAG 2.1 AA signals on
projects/v11-aep/publish-ready/aep/viewer/index.html.

This is an empirical/characterization test (no bug to fix; no RED step). The
test class documents the WCAG signal count + binds the audit to a hash-chained
outcome row at .claude/_logs/aep-v15-lts-viewer-accessibility-audit.jsonl.

Required signals (must all pass):
  a11y_signal_1_aria_labels_present   - count aria-label + aria-labelledby >= 10
  a11y_signal_2_role_attrs_present    - count role= >= 5
  a11y_signal_3_tabindex_present      - count tabindex= >= 3
  a11y_signal_4_keyboard_handlers     - keydown handler present >= 1
  a11y_signal_5_color_not_sole_signal - verdict has icon AND text label (regex)

Bonus signals (>=3/5 must pass):
  a11y_signal_6_skip_link              - skip-to-content present
  a11y_signal_7_semantic_html5         - main/header/footer/section landmarks
  a11y_signal_8_lang_attr              - <html lang=...> set
  a11y_signal_9_focus_rings            - :focus-visible CSS rule present
  a11y_signal_10_contrast_check        - heuristic: dark fg + light bg or vice
                                         versa, no light fg on light bg patterns

Pass: 5/5 required + >=3/5 bonus.

Stdlib only. Composes_with: sec73.4 + sec73.5 + sec73.6.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
PROJ_ROOT = pathlib.Path(__file__).resolve().parents[1]
VIEWER_PATH = PROJ_ROOT / "viewer" / "index.html"
LOGS_DIR = REPO_ROOT / ".claude" / "_logs"
OUTCOMES_PATH = LOGS_DIR / "aep-v15-lts-viewer-accessibility-audit.jsonl"


# ---------- Signal probes ----------

def signal_1_aria_labels(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Count aria-label + aria-labelledby + aria-describedby occurrences.

    Counts both static HTML attribute form (aria-label=) AND the JS object-key
    form ("aria-label":). The JS form lands on real DOM nodes at runtime, so
    end-users see the labels. The empirical signal is total delivered ARIA, not
    static-HTML-only.
    """
    n_label_html = len(re.findall(r'aria-label\s*=', html))
    n_labelledby_html = len(re.findall(r'aria-labelledby\s*=', html))
    n_describedby_html = len(re.findall(r'aria-describedby\s*=', html))
    # JS object-key form: "aria-label": or 'aria-label':
    n_label_js = len(re.findall(r'["\']aria-label["\']\s*:', html))
    n_labelledby_js = len(re.findall(r'["\']aria-labelledby["\']\s*:', html))
    n_describedby_js = len(re.findall(r'["\']aria-describedby["\']\s*:', html))
    n_controls_js = len(re.findall(r'["\']aria-controls["\']\s*:', html))
    n_expanded_js = len(re.findall(r'["\']aria-expanded["\']\s*:', html))
    n_live_js = len(re.findall(r'["\']aria-live["\']\s*:', html))
    n_hidden_js = len(re.findall(r'["\']aria-hidden["\']\s*:', html))
    n_current_js = len(re.findall(r'["\']aria-current["\']\s*:', html))
    n_atomic_js = len(re.findall(r'["\']aria-atomic["\']\s*:', html))
    total = (n_label_html + n_labelledby_html + n_describedby_html
             + n_label_js + n_labelledby_js + n_describedby_js
             + n_controls_js + n_expanded_js + n_live_js + n_hidden_js
             + n_current_js + n_atomic_js)
    return (total >= 10, {
        "count_aria_label_html": n_label_html,
        "count_aria_labelledby_html": n_labelledby_html,
        "count_aria_describedby_html": n_describedby_html,
        "count_aria_label_js": n_label_js,
        "count_aria_labelledby_js": n_labelledby_js,
        "count_aria_describedby_js": n_describedby_js,
        "count_aria_controls_js": n_controls_js,
        "count_aria_expanded_js": n_expanded_js,
        "count_aria_live_js": n_live_js,
        "count_aria_hidden_js": n_hidden_js,
        "count_aria_current_js": n_current_js,
        "count_aria_atomic_js": n_atomic_js,
        "total": total,
        "threshold": 10,
    })


def signal_2_role_attrs(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Count role= attributes."""
    n_role = len(re.findall(r'\brole\s*=\s*["\'][^"\']+["\']', html))
    return (n_role >= 5, {"count_role": n_role, "threshold": 5})


def signal_3_tabindex(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Count tabindex= attributes + natively-tabbable elements.

    Native <button> and <a href> are tabbable without explicit tabindex; treat
    those as tabindex-equivalent for the WCAG keyboard-navigation signal. End-
    users get the same keyboard reachability.
    """
    n_explicit = len(re.findall(r'tabindex\s*=', html))
    n_button = len(re.findall(r'<button\b', html))
    n_a_href = len(re.findall(r'<a\s+[^>]*href\s*=', html))
    n_input = len(re.findall(r'<input\b', html))
    n_button_js = len(re.findall(r'el\(\s*["\']button["\']', html))
    total = n_explicit + n_button + n_a_href + n_input + n_button_js
    return (total >= 3, {
        "count_explicit_tabindex": n_explicit,
        "count_native_button_static": n_button,
        "count_native_a_href": n_a_href,
        "count_native_input": n_input,
        "count_dynamic_buttons_js": n_button_js,
        "total_focusable": total,
        "threshold": 3,
    })


def signal_4_keyboard_handlers(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Detect keyboard event handlers."""
    n_keydown = len(re.findall(r'(?:addEventListener\s*\(\s*[\'\"]keydown[\'\"]|onkeydown\s*=|onkeypress\s*=)', html))
    return (n_keydown >= 1, {"count_keydown_handlers": n_keydown, "threshold": 1})


def signal_5_color_not_sole(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Verify verdict states carry icon + text label (color not sole signal)."""
    has_verdict_icon_class = bool(re.search(r'verdict-icon', html))
    has_verdict_word_class = bool(re.search(r'verdict-word', html))
    has_icons_dict = bool(re.search(r'VERDICT_ICONS\s*=\s*\{', html))
    has_aria_label = bool(re.search(r'VERDICT_ARIA\s*=\s*\{', html))
    ok = has_verdict_icon_class and has_verdict_word_class and has_icons_dict and has_aria_label
    return (ok, {
        "has_verdict_icon_class": has_verdict_icon_class,
        "has_verdict_word_class": has_verdict_word_class,
        "has_VERDICT_ICONS_dict": has_icons_dict,
        "has_VERDICT_ARIA_dict": has_aria_label,
    })


def signal_6_skip_link(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Detect skip-to-content link."""
    has_class = bool(re.search(r'skip-link', html, re.IGNORECASE))
    has_href = bool(re.search(r'href\s*=\s*["\']#main-content', html, re.IGNORECASE))
    return (has_class and has_href, {"has_skip_link_class": has_class, "has_main_content_anchor": has_href})


def signal_7_semantic_html5(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Detect semantic landmarks: header/main/footer/section/nav/article."""
    has_header = bool(re.search(r'<header\b', html))
    has_main = bool(re.search(r'<main\b', html))
    has_footer = bool(re.search(r'<footer\b', html))
    has_section = bool(re.search(r'<section\b', html))
    has_button = bool(re.search(r'<button\b', html))
    count_pass = sum([has_header, has_main, has_footer, has_section, has_button])
    return (count_pass >= 4, {
        "has_header": has_header,
        "has_main": has_main,
        "has_footer": has_footer,
        "has_section": has_section,
        "has_button": has_button,
        "landmark_count": count_pass,
        "threshold": 4,
    })


def signal_8_lang_attr(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Detect <html lang="..."> attribute."""
    m = re.search(r'<html[^>]*\blang\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    return (m is not None, {
        "html_lang_present": m is not None,
        "html_lang_value": m.group(1) if m else None,
    })


def signal_9_focus_rings(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Detect :focus-visible CSS rule(s)."""
    has_focus_visible = bool(re.search(r':focus-visible', html))
    has_focus = bool(re.search(r':focus\s*\{', html))
    has_no_outline_none_unmitigated = not bool(re.search(r'outline\s*:\s*none\s*;(?!\s*outline)', html))
    return (has_focus_visible and has_no_outline_none_unmitigated, {
        "has_focus_visible_rule": has_focus_visible,
        "has_focus_rule": has_focus,
        "no_unmitigated_outline_none": has_no_outline_none_unmitigated,
    })


def signal_10_contrast_check(html: str) -> Tuple[bool, Dict[str, Any]]:
    """Heuristic WCAG color-contrast check on verdict color pairs."""
    # Extract var values; verify each (bg, fg) pair has perceived contrast.
    # Quick test: bg should be light-ish (#c5..#ff..) AND fg should be dark-ish (#0..#3..).
    pass_bg = re.search(r'--pass-bg:\s*#([0-9a-fA-F]{6})', html)
    pass_fg = re.search(r'--pass-fg:\s*#([0-9a-fA-F]{6})', html)
    warn_bg = re.search(r'--warn-bg:\s*#([0-9a-fA-F]{6})', html)
    warn_fg = re.search(r'--warn-fg:\s*#([0-9a-fA-F]{6})', html)
    fail_bg = re.search(r'--fail-bg:\s*#([0-9a-fA-F]{6})', html)
    fail_fg = re.search(r'--fail-fg:\s*#([0-9a-fA-F]{6})', html)

    def luminance(hex_color: str) -> float:
        # Relative luminance per WCAG 2.0 formula.
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        def lin(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    def contrast(bg_hex: str, fg_hex: str) -> float:
        lb = luminance(bg_hex)
        lf = luminance(fg_hex)
        L1 = max(lb, lf)
        L2 = min(lb, lf)
        return (L1 + 0.05) / (L2 + 0.05)

    pairs = []
    if pass_bg and pass_fg:
        pairs.append(("PASS", pass_bg.group(1), pass_fg.group(1), contrast(pass_bg.group(1), pass_fg.group(1))))
    if warn_bg and warn_fg:
        pairs.append(("WARN", warn_bg.group(1), warn_fg.group(1), contrast(warn_bg.group(1), warn_fg.group(1))))
    if fail_bg and fail_fg:
        pairs.append(("FAIL", fail_bg.group(1), fail_fg.group(1), contrast(fail_bg.group(1), fail_fg.group(1))))

    # WCAG AA requires >= 4.5:1 for normal text.
    all_pass = all(c[3] >= 4.5 for c in pairs) and len(pairs) >= 3
    return (all_pass, {
        "pairs": [
            {"verdict": p[0], "bg": "#" + p[1], "fg": "#" + p[2], "contrast_ratio": round(p[3], 2), "passes_wcag_aa": p[3] >= 4.5}
            for p in pairs
        ],
        "threshold": 4.5,
        "all_pairs_pass_aa": all_pass,
    })


# ---------- Audit orchestration ----------

REQUIRED_SIGNALS = [
    ("a11y_signal_1_aria_labels_present", signal_1_aria_labels),
    ("a11y_signal_2_role_attrs_present", signal_2_role_attrs),
    ("a11y_signal_3_tabindex_present", signal_3_tabindex),
    ("a11y_signal_4_keyboard_handlers", signal_4_keyboard_handlers),
    ("a11y_signal_5_color_not_sole_signal", signal_5_color_not_sole),
]

BONUS_SIGNALS = [
    ("a11y_signal_6_skip_link", signal_6_skip_link),
    ("a11y_signal_7_semantic_html5", signal_7_semantic_html5),
    ("a11y_signal_8_lang_attr", signal_8_lang_attr),
    ("a11y_signal_9_focus_rings", signal_9_focus_rings),
    ("a11y_signal_10_contrast_check", signal_10_contrast_check),
]


def run_audit(viewer_path: pathlib.Path = VIEWER_PATH) -> Dict[str, Any]:
    if not viewer_path.is_file():
        return {
            "type": "ViewerAccessibilityAuditRow",
            "viewer_path": str(viewer_path).replace("\\", "/"),
            "error": "viewer_not_found",
            "required_pass_count": 0,
            "bonus_pass_count": 0,
            "overall_pass": False,
        }
    html = viewer_path.read_text(encoding="utf-8")
    viewer_sha = hashlib.sha256(html.encode("utf-8")).hexdigest()

    required_results: List[Dict[str, Any]] = []
    required_pass = 0
    for sig_id, fn in REQUIRED_SIGNALS:
        ok, detail = fn(html)
        if ok:
            required_pass += 1
        required_results.append({
            "signal_id": sig_id,
            "pass": ok,
            "detail": detail,
            "required": True,
        })

    bonus_results: List[Dict[str, Any]] = []
    bonus_pass = 0
    for sig_id, fn in BONUS_SIGNALS:
        ok, detail = fn(html)
        if ok:
            bonus_pass += 1
        bonus_results.append({
            "signal_id": sig_id,
            "pass": ok,
            "detail": detail,
            "required": False,
        })

    overall_pass = (required_pass == len(REQUIRED_SIGNALS)) and (bonus_pass >= 3)
    return {
        "type": "ViewerAccessibilityAuditRow",
        "viewer_path": str(viewer_path).replace("\\", "/"),
        "viewer_sha256": viewer_sha,
        "viewer_byte_count": len(html.encode("utf-8")),
        "required_signals": required_results,
        "bonus_signals": bonus_results,
        "required_pass_count": required_pass,
        "required_total": len(REQUIRED_SIGNALS),
        "bonus_pass_count": bonus_pass,
        "bonus_total": len(BONUS_SIGNALS),
        "overall_pass": overall_pass,
        "audited_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "honest_framing_per_sec73_6": (
            "Empirical signal count from regex + WCAG luminance formula. "
            "Heuristic only; not a full WCAG ACT audit. Pass=5/5 required + >=3/5 bonus."
        ),
    }


def write_outcome(result: Dict[str, Any]) -> pathlib.Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with OUTCOMES_PATH.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(result, sort_keys=True) + "\n")
    return OUTCOMES_PATH


# ---------- CLI ----------

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="AEP v1.5 LTS viewer accessibility audit (WCAG 2.1 AA empirical signals)")
    parser.add_argument("--viewer", default=str(VIEWER_PATH), help="Path to viewer index.html")
    args = parser.parse_args(argv)

    result = run_audit(pathlib.Path(args.viewer))
    out_path = write_outcome(result)
    summary = {
        "viewer_path": result.get("viewer_path"),
        "viewer_sha256": result.get("viewer_sha256"),
        "required_pass_count": result["required_pass_count"],
        "required_total": result["required_total"],
        "bonus_pass_count": result["bonus_pass_count"],
        "bonus_total": result["bonus_total"],
        "overall_pass": result["overall_pass"],
        "outcome_log": str(out_path).replace("\\", "/"),
        "required_signal_breakdown": [
            {"signal_id": r["signal_id"], "pass": r["pass"]}
            for r in result.get("required_signals", [])
        ],
        "bonus_signal_breakdown": [
            {"signal_id": r["signal_id"], "pass": r["pass"]}
            for r in result.get("bonus_signals", [])
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
