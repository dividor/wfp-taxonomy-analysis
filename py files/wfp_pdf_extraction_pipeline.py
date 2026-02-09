# WFP PDF Extraction Pipeline
# Filename: wfp_pdf_extraction_pipeline.py
# Purpose: Walk a master folder with subfolders per topic, extract text+layout from each PDF,
# clean text, detect sections via heading heuristics, save JSON per report and metadata CSV.

# NOTE: This script is intended to be run in a Jupyter notebook or as a Python script.
# It was designed to be robust and to run offline. It tries to detect scanned PDFs and
# will attempt to call `ocrmypdf` if present on the host system.

# Requirements:
# pip install pymupdf pdfplumber tqdm pandas python-dateutil
# Optional: ocrmypdf (system package) and camelot for table extraction

import os
import re
import json
import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
import subprocess

# ----------------------------- Configuration -----------------------------
INPUT_MASTER = Path('reports')          # master folder with subfolders by topic
OUTPUT_EXTRACTED = Path('extracted')   # JSON per report
BASE_PATH = Path('/Users/madhu/Desktop/WFP/wfp-taxonomy-analysis/data')
METADATA_CSV = BASE_PATH / 'metadata.csv'  # DataFrame summary
OCRMYPDF_CMD = 'ocrmypdf'              # command for ocrmypdf if available

# Create output folder
OUTPUT_EXTRACTED.mkdir(parents=True, exist_ok=True)

# ----------------------------- Utility functions -----------------------------

def is_scanned_pdf(path: Path, char_threshold=50):
    """Check if PDF appears scanned by extracting a small sample of text.
    If extracted text is very small, assume scanned.
    """
    try:
        doc = fitz.open(path)
        text = ""
        # sample first two pages
        for i in range(min(2, doc.page_count)):
            text += doc[i].get_text("text") or ""
        doc.close()
        return len(text.strip()) < char_threshold
    except Exception:
        return False


def run_ocr(input_pdf: Path, output_pdf: Path):
    """Call ocrmypdf if installed. Returns True on success, False otherwise."""
    try:
        subprocess.run([OCRMYPDF_CMD, '--skip-text', str(input_pdf), str(output_pdf)], check=True)
        return True
    except Exception as e:
        print(f"OCR failed or ocrmypdf not installed: {e}")
        return False


# cleaning functions
def fix_unicode_artifacts(text: str) -> str:
    # replace replacement characters, weird ligatures, and common mojibake
    text = text.replace('\ufffd', '')
    text = text.replace('�', '')
    # common mojibake sequences — add more rules if you see others
    text = text.replace('\xad', '')  # soft hyphen
    return text


def fix_hyphenation(text: str) -> str:
    # remove hyphenation like "nutri-\ntion" -> "nutrition"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace('-\n', '')
    return text


def normalize_whitespace(text: str) -> str:
    # collapse multiple whitespace characters into single space and strip
    text = re.sub(r"[ \t\f\r]+", ' ', text)
    text = re.sub(r"\n{2,}", '\n\n', text)
    return text.strip()


def clean_text(text: str) -> str:
    text = fix_unicode_artifacts(text)
    text = fix_hyphenation(text)
    text = normalize_whitespace(text)
    return text


# ----------------------------- Extraction helpers -----------------------------

def extract_page_blocks_fitz(page):
    """Return blocks with bbox and spans from PyMuPDF page"""
    blocks = []
    # get_text('dict') gives blocks with lines and spans (with fonts and sizes)
    try:
        j = page.get_text('dict')
    except Exception:
        return blocks

    for b in j.get('blocks', []):
        if 'lines' not in b:
            continue
        text = ''
        max_size = 0
        for line in b.get('lines', []):
            for span in line.get('spans', []):
                txt = span.get('text', '')
                size = span.get('size', 0)
                text += txt
                if size > max_size:
                    max_size = size
        bbox = b.get('bbox', [0, 0, 0, 0])
        blocks.append({'text': text.strip(), 'bbox': bbox, 'font_size': max_size})
    return blocks


def reorder_blocks_two_column(blocks, page_width):
    """Heuristic to reorder blocks on two-column pages. Splits by vertical midpoint.
    Returns concatenated left column then right column in reading order.
    """
    if not blocks:
        return blocks
    midpoint = page_width / 2.0
    left = [b for b in blocks if (b['bbox'][0] + b['bbox'][2]) / 2.0 < midpoint]
    right = [b for b in blocks if (b['bbox'][0] + b['bbox'][2]) / 2.0 >= midpoint]
    left_sorted = sorted(left, key=lambda x: (x['bbox'][1], x['bbox'][0]))
    right_sorted = sorted(right, key=lambda x: (x['bbox'][1], x['bbox'][0]))
    return left_sorted + right_sorted


def detect_repeated_headers(pages_blocks, top_lines=2, bottom_lines=2, threshold=0.5):
    """Detect repeated header/footer text across pages and return sets to remove.
    pages_blocks: list of lists (blocks per page)
    returns: header_candidates, footer_candidates (sets of text strings)
    """
    header_counts = {}
    footer_counts = {}
    N = len(pages_blocks)
    for p_idx, blocks in enumerate(pages_blocks):
        # collect top N lines (smallest bbox y)
        if not blocks:
            continue
        sorted_by_y = sorted(blocks, key=lambda x: x['bbox'][1])
        for b in sorted_by_y[:top_lines]:
            header_counts[b['text']] = header_counts.get(b['text'], 0) + 1
        bottom_sorted = sorted(blocks, key=lambda x: x['bbox'][3], reverse=True)
        for b in bottom_sorted[:bottom_lines]:
            footer_counts[b['text']] = footer_counts.get(b['text'], 0) + 1
    header_candidates = {t for t, c in header_counts.items() if c / max(1, N) >= threshold}
    footer_candidates = {t for t, c in footer_counts.items() if c / max(1, N) >= threshold}
    return header_candidates, footer_candidates


# ----------------------------- Main processor -----------------------------

def process_pdf(path: Path, clean=True, ocr_if_needed=True, two_column_midpoint=True):
    """Process a single PDF. Returns structured dict and full_text string.
    The structured dict contains per-page blocks, then sections inferred by headings.
    """
    result = {
        'report_id': path.stem,
        'file_path': str(path.resolve()),
        'pages': [],
        'sections': [],
        'num_pages': 0,
    }

    # Handle scanned PDF with OCR fallback
    use_path = path
    if ocr_if_needed and is_scanned_pdf(path):
        tmp_ocr = path.with_name(path.stem + '_ocr.pdf')
        ok = run_ocr(path, tmp_ocr)
        if ok:
            use_path = tmp_ocr

    # Open with fitz and extract page blocks
    try:
        doc = fitz.open(use_path)
    except Exception as e:
        print(f"Failed to open {use_path}: {e}")
        return result, ''

    pages_blocks = []
    for page in doc:
        blocks = extract_page_blocks_fitz(page)
        # reorder two-column heuristics
        if two_column_midpoint:
            width = page.rect.width
            blocks = reorder_blocks_two_column(blocks, width)
        pages_blocks.append(blocks)
    doc.close()

    pages_blocks.append(blocks)


    # detect headers/footers to remove
    headers, footers = detect_repeated_headers(pages_blocks)

    # assemble pages and compute full text
    full_text_parts = []
    all_font_sizes = []
    for p_idx, blocks in enumerate(pages_blocks):
        page_text = []
        for b in blocks:
            txt = b['text']
            if not txt:
                continue
            # skip header/footer if matched
            if txt in headers or txt in footers:
                continue
            page_text.append(txt)
            if b.get('font_size'):
                all_font_sizes.append(b.get('font_size'))
        page_text_joined = '\n'.join(page_text)
        result['pages'].append({'page_number': p_idx+1, 'text': page_text_joined})
        full_text_parts.append(page_text_joined)

    full_text = '\n\n'.join(full_text_parts)

    # Clean text if requested
    if clean:
        full_text = clean_text(full_text)
        # also clean page-level text
        for p in result['pages']:
            p['text'] = clean_text(p['text'])

    result['num_pages'] = len(result['pages'])

    # Heading detection: heuristics based on font sizes from spans
    # If no font info, fallback to looking for short lines with titlecase or uppercase
    heading_threshold = None
    if all_font_sizes:
        median_size = float(pd.Series(all_font_sizes).median())
        heading_threshold = median_size + 1.0

    sections = []
    current_section = {'heading': 'Introduction', 'text': '', 'pages': []}
    for p in result['pages']:
        page_num = p['page_number']
        # split into lines
        lines = [ln.strip() for ln in p['text'].split('\n') if ln.strip()]
        for ln in lines:
            # crude heading detection
            is_heading = False
            # if font info exists in page blocks, find matching block font size
            # fallback checks
            if heading_threshold is not None:
                # check if this line appears as a block with larger size in original pages_blocks
                for b in pages_blocks[page_num-1]:
                    if b['text'].strip().startswith(ln[:40]) and b.get('font_size', 0) >= heading_threshold:
                        is_heading = True
                        break
            else:
                # uppercase or title-case heuristic for headings
                if len(ln.split()) <= 8 and (ln.isupper() or ln.istitle()):
                    is_heading = True

            if is_heading:
                # start a new section
                if current_section['text'].strip():
                    sections.append(current_section)
                current_section = {'heading': ln, 'text': '', 'pages': [page_num]}
            else:
                # append to current section
                if current_section['pages'] and current_section['pages'][-1] != page_num:
                    current_section['pages'].append(page_num)
                current_section['text'] += ln + '\n'

    # flush last
    if current_section and current_section['text'].strip():
        sections.append(current_section)

    # If no sections found, make a single full-text section
    if not sections:
        sections = [{'heading': 'Full Text', 'text': full_text, 'pages': list(range(1, result['num_pages']+1))}]

    # final clean of section text
    for s in sections:
        s['text'] = normalize_whitespace(s['text'])

    result['sections'] = sections

    return result, full_text


# ----------------------------- Orchestration -----------------------------

def process_master_folder(input_master=INPUT_MASTER, output_extracted=OUTPUT_EXTRACTED, metadata_csv=METADATA_CSV):
    records = []
    # walk subfolders — each subfolder name is topic
    input_master = Path('/Users/madhu/Desktop/WFP/wfp_reports/wfp_reports')  # replace with your path here
    
    # Walk subfolders — each subfolder name is topic
    topics = [p for p in input_master.iterdir() if p.is_dir()]
    pdf_files = []
    for t in topics:
        for pdf in t.glob('**/*.pdf'):
            pdf_files.append((pdf, t.name))

    # progress bar
    for pdf, topic in tqdm(pdf_files, desc='Processing PDFs'):
        try:
            structured, full_text = process_pdf(pdf, clean=True, ocr_if_needed=False)

            # build metadata
            rec = {
                'report_id': structured.get('report_id'),
                'report_name': pdf.name,
                'topic': topic,
                'json_path': str((output_extracted / (structured.get('report_id') + '.json')).resolve()),
                'file_path': str(pdf.resolve()),
                'pages': structured.get('num_pages', 0),
                'text_length': len(full_text)
            }
            records.append(rec)

            # save JSON
            out_json = output_extracted / (structured.get('report_id') + '.json')
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(structured, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to process {pdf}: {e}")

    # write metadata CSV
    df = pd.DataFrame(records)
    df.to_csv(metadata_csv, index=False)
    return df


# ----------------------------- Quick test run on uploaded example -----------------------------
if __name__ == '__main__':
    # If running interactively in notebook, comment the following and call process_master_folder() manually.
    print('Starting extraction...')
    df = process_master_folder()
    print('Extraction complete. Metadata saved to', METADATA_CSV)
    print(df.head())
