#!/usr/bin/env python3
"""Rebuild the six synthetic-item PDFs from their Markdown sources.

Pipeline (one pipeline for every PDF):
  1. python-markdown (extensions: tables, fenced_code, sane_lists) -> HTML
     wrapped in a fixed, simple embedded stylesheet.
  2. LibreOffice headless: import with the "HTML (StarWriter)" filter (so the
     document is laid out as a normal paged Writer document, not Writer/Web)
     and export with writer_pdf_Export.
  3. Verify with pdftotext: the PDF must contain a distinctive sentence from
     the first, middle and last section of its Markdown (checked by a
     whitespace-normalised substring match), plus any extra phrases passed in
     REQUIRED_PHRASES. Page counts are printed.

Requirements: python3, `pip install markdown`, LibreOffice Writer
(`apt install libreoffice-writer-nogui` on a core-only install), poppler-utils
(pdftotext, pdfinfo).

Usage (from anywhere):
  python3 eval/build_pdfs.py            # rebuild all six and verify
  python3 eval/build_pdfs.py --check    # verify the existing PDFs only

A fresh LibreOffice user profile is created in a temporary directory for each
run so that local LibreOffice settings cannot change the output.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

EVAL = Path(__file__).resolve().parent
ITEMS = ["clinical_rpm", "payments_orchestration", "research_lakehouse"]
VERSIONS = ["design_v1", "design_v2"]

# Phrases that must appear in specific PDFs (edits made after the original
# PDF build; see research/audit/eval_fixes_applied.md D01 and D02).
REQUIRED_PHRASES = {
    ("research_lakehouse", "design_v1"): [
        "could the engineering team build each component from this document alone",
    ],
    ("research_lakehouse", "design_v2"): [
        "could the engineering team build each component from this document alone",
    ],
    ("payments_orchestration", "design_v2"): ["2026-10-01"],
}
# Phrases that must NOT appear (the pre-edit text).
FORBIDDEN_PHRASES = {
    ("research_lakehouse", "design_v1"): ["AI coding assistant"],
    ("research_lakehouse", "design_v2"): ["AI coding assistant"],
    ("payments_orchestration", "design_v2"): ["2026-10-12"],
}

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: 'Liberation Sans', Arial, sans-serif; font-size: 9.5pt; line-height: 1.3; }
h1 { font-size: 17pt; margin: 0 0 6pt 0; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 11pt; margin: 10pt 0 3pt 0; }
h4 { font-size: 10pt; margin: 8pt 0 2pt 0; }
p, li { margin: 0 0 4pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
th, td { border: 0.5pt solid #777777; padding: 2pt 3pt; vertical-align: top; font-size: 8pt; }
th { background: #e6e6e6; font-weight: bold; }
code { font-family: 'Liberation Mono', 'Courier New', monospace; font-size: 8pt; }
pre { font-family: 'Liberation Mono', 'Courier New', monospace; font-size: 6.5pt; line-height: 1.15;
      background: #f3f3f3; border: 0.5pt solid #bbbbbb; padding: 3pt; margin: 4pt 0 8pt 0; }
hr { border: 0; border-top: 0.5pt solid #999999; }
"""

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]


def md_to_html(md_text: str, title: str) -> str:
    body = markdown.markdown(md_text, extensions=MD_EXTENSIONS, output_format="html")
    # Keep short identifier cells (e.g. FR-11, NFR-AV-01, D-15) on one line;
    # LibreOffice otherwise breaks them at the hyphen in narrow ID columns.
    body = re.sub(r"<td>([A-Za-z]{1,6}(?:-[A-Za-z0-9]{1,6}){1,3})</td>", r"<td><nobr>\1</nobr></td>", body)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>\n{body}\n</body></html>\n"
    )


def soffice_bin() -> str:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("LibreOffice (soffice) not found")


def convert(html_path: Path, out_dir: Path, profile_dir: Path) -> Path:
    cmd = [
        soffice_bin(),
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--headless",
        "--norestore",
        "--infilter=HTML (StarWriter)",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(out_dir),
        str(html_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    pdf = out_dir / (html_path.stem + ".pdf")
    if not pdf.exists():
        sys.exit(f"conversion failed for {html_path}")
    return pdf


def norm(text: str) -> str:
    text = text.replace("­", "")  # soft hyphen
    text = re.sub(r"-\n(?=[a-z])", "", text)  # hyphenation at line end
    return re.sub(r"\s+", " ", text).strip()


def strip_md(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]*)\*", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return s


def _candidates(sec: str) -> list[str]:
    no_code = re.sub(r"```.*?```", "", sec, flags=re.S)
    out = []
    for line in no_code.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith(("|", "#", "-", "*", ">")) or re.match(r"^\d+\.", line):
            continue
        for sent in re.split(r"(?<=[.!?])\s+", strip_md(line)):
            if 60 <= len(sent) <= 220:
                out.append(sent)
    return out


def probe_sentences(md_text: str) -> dict[str, tuple[str, str]]:
    """Pick a distinctive prose phrase from the first, middle and last H2 section.

    Sections with no usable prose (title blocks, the table of contents) are
    skipped by walking inwards from each end. The probe is the middle eight
    words of the longest qualifying sentence, which avoids line-break and
    hyphenation artefacts at sentence edges.
    """
    sections = [s for s in re.split(r"(?m)^## ", md_text)[1:] if _candidates(s)]
    picks = {}
    for label, sec in (("first", sections[0]), ("middle", sections[len(sections) // 2]), ("last", sections[-1])):
        heading = sec.splitlines()[0].strip()
        words = max(_candidates(sec), key=len).split()
        mid = len(words) // 2
        picks[label] = (heading, " ".join(words[max(0, mid - 4): mid + 4]))
    return picks


def pdf_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], check=True, stdout=subprocess.PIPE).stdout.decode()
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def verify(item: str, version: str, md_path: Path, pdf: Path) -> bool:
    md_text = md_path.read_text(encoding="utf-8")
    text = norm(pdf_text(pdf))
    ok = True
    print(f"{item}/{version}.pdf: {page_count(pdf)} pages")
    for label, (heading, probe) in probe_sentences(md_text).items():
        hit = norm(probe) in text
        ok &= hit
        print(f"  [{'ok' if hit else 'MISSING'}] {label:6} section '{heading}': \"{probe}\"")
    for phrase in REQUIRED_PHRASES.get((item, version), []):
        hit = norm(phrase) in text
        ok &= hit
        print(f"  [{'ok' if hit else 'MISSING'}] required phrase: \"{phrase}\"")
    for phrase in FORBIDDEN_PHRASES.get((item, version), []):
        hit = norm(phrase) in text
        ok &= not hit
        print(f"  [{'ok' if not hit else 'PRESENT'}] stale phrase absent: \"{phrase}\"")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify existing PDFs without rebuilding")
    args = ap.parse_args()
    all_ok = True
    with tempfile.TemporaryDirectory(prefix="build_pdfs_") as tmp:
        tmp = Path(tmp)
        profile = tmp / "lo_profile"
        for item in ITEMS:
            for version in VERSIONS:
                md_path = EVAL / "synthetic" / item / f"{version}.md"
                pdf_path = md_path.with_suffix(".pdf")
                if not args.check:
                    html_path = tmp / f"{version}.html"
                    title = md_path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
                    html_path.write_text(md_to_html(md_path.read_text(encoding="utf-8"), title), encoding="utf-8")
                    built = convert(html_path, tmp, profile)
                    shutil.move(str(built), pdf_path)
                all_ok &= verify(item, version, md_path, pdf_path)
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
