#!/usr/bin/env python3
"""
check_watermarks.py — Scan generated PDFs and YAML files for AI provenance marks.

Runs AFTER resume/cover-letter generation (Step 2/3 compilation) and BEFORE
the pipeline declares success. Checks three layers:

  Layer A — Invisible Unicode in YAML text (zero-width, bidi, tag chars, etc.)
  Layer B — C2PA / Content Credentials / AI metadata in PDF binary (JUMBF, XMP)
  Layer C — PDF metadata fields for AI vendor strings (Claude, OpenAI, SynthID)

Exit codes:
  0 — clean (no marks found)
  1 — marks found (prints report, does NOT delete or modify anything)
  2 — usage error / file not found

Usage:
  python check_watermarks.py <file1> [file2] [file3] ...
  python check_watermarks.py Resume.yaml SAGAR_MARTHANDAN_Resume.pdf
  python check_watermarks.py --dir "/path/to/application folder/"
  python check_watermarks.py --json Resume.yaml SAGAR_MARTHANDAN_Resume.pdf

Detection logic adapted from the remove-ai-marks skill (inspect_file.py,
container_meta.py, image_meta.py, text_unicode.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# ── Layer A: Invisible Unicode codepoints ────────────────────────────────────
# Adapted from remove-ai-marks/scripts/text_unicode.py

STRIP_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x00AD,  # soft hyphen
        0x034F,  # combining grapheme joiner
        0x061C,  # Arabic letter mark
        0x115F,  # Hangul choseong filler
        0x1160,  # Hangul jungseong filler
        0x17B4,  # Khmer vowel inherent AQ
        0x17B5,  # Khmer vowel inherent AA
        0x180B,  # Mongolian free variation selector-1
        0x180C, 0x180D, 0x180E,  # Mongolian vowel separator
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0x200E,  # LRM
        0x200F,  # RLM
        0x202A,  # LRE
        0x202B,  # RLE
        0x202C,  # PDF
        0x202D,  # LRO
        0x202E,  # RLO
        0x2060,  # word joiner
        0x2061,  # function application
        0x2062,  # invisible times
        0x2063,  # invisible separator
        0x2064,  # invisible plus
        0x2066,  # LRI
        0x2067,  # RLI
        0x2068,  # FSI
        0x2069,  # PDI
        0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,  # deprecated format chars
        0xFEFF,  # BOM / ZWNBSP
        0xFFF9, 0xFFFA, 0xFFFB,  # interlinear annotation
    }
) | frozenset(range(0xFE00, 0xFE10))  # variation selectors VS1-VS16

_VS_SUPPLEMENT = range(0xE0100, 0xE01F0)  # VS17–VS256
_TAG_CHARS = range(0xE0001, 0xE0080)      # U+E0001–U+E007F

_BIDI_CPS: frozenset[int] = frozenset({
    0x061C, 0x200E, 0x200F,
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
})

_ZW_FAMILY: frozenset[int] = frozenset({
    0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E,
})

SPACE_HOMOGLYPHS: dict[int, str] = {
    0x00A0: " ", 0x1680: " ", 0x2000: " ", 0x2001: " ",
    0x2002: " ", 0x2003: " ", 0x2004: " ", 0x2005: " ",
    0x2006: " ", 0x2007: " ", 0x2008: " ", 0x2009: " ",
    0x200A: " ", 0x202F: " ", 0x205F: " ", 0x3000: " ",
}


def _is_strip_cp(cp: int) -> bool:
    if cp in STRIP_CODEPOINTS:
        return True
    if cp in _VS_SUPPLEMENT:
        return True
    if cp in _TAG_CHARS:
        return True
    return False


def _strip_kind(cp: int) -> str:
    if cp in _TAG_CHARS:
        return "tag_chars"
    if cp in _VS_SUPPLEMENT or 0xFE00 <= cp <= 0xFE0F or 0x180B <= cp <= 0x180D:
        return "variation_selector"
    if cp in _BIDI_CPS:
        return "bidi"
    if cp in _ZW_FAMILY:
        return "zwj_family"
    return "strip"


@dataclass
class UnicodeHit:
    codepoint: int
    label: str
    count: int
    kind: str
    sample_offsets: list[int] = field(default_factory=list)


def inspect_text_unicode(text: str) -> list[UnicodeHit]:
    """Scan text for invisible/suspicious Unicode codepoints."""
    buckets: dict[tuple[int, str], list[int]] = {}
    for i, ch in enumerate(text):
        cp = ord(ch)
        kind: str | None = None
        if _is_strip_cp(cp):
            kind = _strip_kind(cp)
        elif cp in SPACE_HOMOGLYPHS:
            kind = "space"
        else:
            cat = unicodedata.category(ch)
            if cat == "Cf" and cp != 0x00AD:
                kind = "other_cf"
        if kind is None:
            continue
        buckets.setdefault((cp, kind), []).append(i)

    hits: list[UnicodeHit] = []
    for (cp, kind), offsets in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0][0])):
        ch = chr(cp)
        name = unicodedata.name(ch, "UNKNOWN")
        hits.append(UnicodeHit(
            codepoint=cp,
            label=f"U+{cp:04X} {name} ({unicodedata.category(ch)})",
            count=len(offsets),
            kind=kind,
            sample_offsets=offsets[:10],
        ))
    return hits


# ── Layer B+C: PDF binary / metadata markers ─────────────────────────────────
# Adapted from remove-ai-marks/scripts/image_meta.py + container_meta.py

C2PA_MARKERS: tuple[bytes, ...] = (
    b"c2pa", b"C2PA",
    b"jumb", b"JUMB",
    b"c2ma",
    b"contentcredentials", b"contentauth",
    b"cai:",
    b"http://ns.adobe.com/xmp/InstanceID/",
)

AI_META_HINTS: tuple[bytes, ...] = (
    b"c2pa", b"C2PA",
    b"contentcredentials", b"ContentCredentials",
    b"digitalSourceType",
    b"trainedAlgorithmicMedia",
    b"compositeWithTrainedAlgorithmicMedia",
    b"algorithmicMedia",
    b"AIGC", b"aigc",
    b"AI generated", b"Generated by",
    b"Claude", b"Anthropic",
    b"OpenAI",
    b"SynthID", b"synthid",
    b"dcterms:provenance",
)

# XMP packet markers — these indicate real XMP metadata, not random byte matches
XMP_PACKET_MARKERS: tuple[bytes, ...] = (
    b"<?xpacket",
    b"<x:xmpmeta",
    b"<?adobexptr",
    b"<rdf:RDF",
)

# Patterns that only count as AI-provenance when inside an XMP packet
_XMP_AI_PATTERNS = re.compile(
    rb"digitalSourceType|trainedAlgorithmicMedia|SoftwareAgent|c2pa|"
    rb"algorithmicMedia|AI generated|ContentCredentials",
    re.IGNORECASE,
)


def _extract_pdf_non_stream(data: bytes) -> bytes:
    """Extract the non-stream portions of a PDF (metadata, dict keys, trailer).

    PDF content streams (FlateDecode image data, etc.) can contain arbitrary
    byte sequences that match C2PA markers by coincidence. We strip everything
    between 'stream' and 'endstream' keywords to avoid false positives.
    XMP packets live outside streams (in /Metadata objects), so they survive.
    """
    # Split on stream/endstream boundaries, keep only non-stream segments
    parts: list[bytes] = []
    pos = 0
    while True:
        stream_start = data.find(b"stream", pos)
        if stream_start == -1:
            parts.append(data[pos:])
            break
        # Keep everything before the stream keyword
        parts.append(data[pos:stream_start])
        # Find the matching endstream
        endstream = data.find(b"endstream", stream_start)
        if endstream == -1:
            break
        pos = endstream + len(b"endstream")
    return b"".join(parts)


def _scan_pdf_binary(data: bytes) -> list[str]:
    """Scan raw PDF bytes for C2PA/AI markers and real XMP packets.

    C2PA/AI markers are only checked in non-stream portions to avoid false
    positives from compressed image data. XMP packets are checked in full data
    since they're always outside streams.
    """
    findings: list[str] = []

    # Strip content streams to avoid false positives from compressed image data
    non_stream = _extract_pdf_non_stream(data)
    non_stream_lower = non_stream.lower()

    # C2PA hard markers (JUMBF, c2pa, contentcredentials) — non-stream only
    for n in C2PA_MARKERS:
        if n.lower() in non_stream_lower:
            findings.append(f"c2pa_marker:{n.decode('ascii', errors='replace')}")

    # AI metadata hints — non-stream only
    for n in AI_META_HINTS:
        if n.lower() in non_stream_lower:
            label = n.decode("ascii", errors="replace")
            if f"ai_hint:{label}" not in findings:
                findings.append(f"ai_hint:{label}")

    # Real XMP packet detection (XMP lives outside streams, but check full data
    # for robustness — the packet markers are specific enough to not false-positive)
    has_xmp_packet = any(m in data for m in XMP_PACKET_MARKERS)
    if has_xmp_packet:
        findings.append("xmp_packet_present")
        # Check for AI-specific XMP content in non-stream data
        if _XMP_AI_PATTERNS.search(non_stream):
            findings.append("xmp_ai_provenance")

    return findings


def _scan_pdf_metadata(path: Path) -> list[str]:
    """Check PDF metadata fields for AI vendor strings using pypdf."""
    findings: list[str] = []
    try:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        meta = r.metadata
        if not meta:
            return findings

        vendor_patterns = [
            (b"claude", "Claude"),
            (b"anthropic", "Anthropic"),
            (b"openai", "OpenAI"),
            (b"synthid", "SynthID"),
            (b"ai generated", "AI generated"),
            (b"content credentials", "Content Credentials"),
            (b"c2pa", "C2PA"),
        ]

        for key, value in meta.items():
            val_str = str(value).lower()
            for pattern, label in vendor_patterns:
                if pattern.decode() in val_str:
                    findings.append(f"metadata:{key}={value} (contains {label})")

        # Check root for /Metadata stream (XMP)
        root = r.trailer.get("/Root", {})
        if "/Metadata" in root:
            findings.append("metadata:xmp_stream_in_root")

    except Exception as e:
        findings.append(f"metadata_error:{e}")

    return findings


def _scan_yaml_text(path: Path) -> list[str]:
    """Scan YAML file text for invisible Unicode (Layer A)."""
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"read_error:{e}"]

    hits = inspect_text_unicode(text)
    for h in hits:
        findings.append(
            f"unicode:{h.label} count={h.count} kind={h.kind} "
            f"offsets={h.sample_offsets[:5]}"
        )
    return findings


# ── Report ───────────────────────────────────────────────────────────────────

@dataclass
class FileReport:
    path: str
    file_type: str  # yaml, pdf, tex, other
    clean: bool
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "file_type": self.file_type,
            "clean": self.clean,
            "findings": self.findings,
        }


def scan_file(path: Path) -> FileReport:
    """Scan a single file for AI watermarks/provenance marks."""
    if not path.is_file():
        return FileReport(str(path), "missing", False, ["file_not_found"])

    ext = path.suffix.lower()
    findings: list[str] = []

    if ext in (".yaml", ".yml"):
        # Layer A: invisible Unicode in text
        findings.extend(_scan_yaml_text(path))

    elif ext == ".pdf":
        # Layer B: binary C2PA/XMP markers
        data = path.read_bytes()
        findings.extend(_scan_pdf_binary(data))
        # Layer C: PDF metadata fields
        findings.extend(_scan_pdf_metadata(path))

    elif ext == ".tex":
        # LaTeX source — check for invisible Unicode
        findings.extend(_scan_yaml_text(path))

    else:
        # Unknown type — do a basic binary scan
        data = path.read_bytes()
        binary_findings = _scan_pdf_binary(data)
        if binary_findings:
            findings.extend(binary_findings)

    return FileReport(
        path=str(path),
        file_type=ext.lstrip(".") or "unknown",
        clean=len(findings) == 0,
        findings=findings,
    )


def scan_directory(dir_path: Path) -> list[FileReport]:
    """Scan all YAML and PDF files in a directory."""
    reports: list[FileReport] = []
    for p in sorted(dir_path.iterdir()):
        if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".pdf", ".tex"):
            reports.append(scan_file(p))
    return reports


def print_report(reports: list[FileReport]) -> None:
    """Print human-readable report."""
    total = len(reports)
    clean_count = sum(1 for r in reports if r.clean)
    flagged = [r for r in reports if not r.clean]

    print("=" * 70)
    print("AI Watermark & Provenance Check")
    print("=" * 70)
    print(f"Files scanned: {total} | Clean: {clean_count} | Flagged: {len(flagged)}")
    print()

    if not flagged:
        print("✓ All files clean — no AI watermarks, C2PA, or provenance marks found.")
        return

    print("⚠  FLAGGED FILES:")
    print("-" * 70)
    for r in flagged:
        print(f"\n  {r.path} ({r.file_type})")
        for f in r.findings:
            print(f"    • {f}")

    print()
    print("-" * 70)
    print("Layers checked:")
    print("  A — Invisible Unicode (zero-width, bidi, tag chars, homoglyphs)")
    print("  B — C2PA/Content Credentials binary markers (JUMBF, XMP packets)")
    print("  C — PDF metadata vendor strings (Claude, OpenAI, SynthID, etc.)")
    print()
    print("NOTE: This script detects marks only — it does NOT modify files.")
    print("      To remove marks, use the remove-ai-marks skill or clean_file.py.")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", type=Path, help="Files to scan")
    p.add_argument("--dir", type=Path, dest="directory",
                   help="Scan all YAML/PDF/TEX files in this directory")
    p.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = p.parse_args()

    if args.directory:
        if not args.directory.is_dir():
            print(f"Error: not a directory: {args.directory}", file=sys.stderr)
            return 2
        reports = scan_directory(args.directory)
    elif args.files:
        reports = [scan_file(f) for f in args.files]
    else:
        p.print_help()
        return 2

    if args.json:
        output = {
            "total": len(reports),
            "clean": sum(1 for r in reports if r.clean),
            "flagged": sum(1 for r in reports if not r.clean),
            "files": [r.to_dict() for r in reports],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(reports)

    # Exit 1 if any file has marks
    return 0 if all(r.clean for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
