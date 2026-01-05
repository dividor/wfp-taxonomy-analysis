import re
import unicodedata
from nltk.tokenize import sent_tokenize
import nltk
nltk.download('punkt_tab')

EXCLUDED_SECTIONS = {
    "annex",
    "data notes",
    "figures and indicators",
    "beneficiaries by",
    "financial overview"
}

def normalize_text(text) -> str:
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()



def is_structural_junk(line: str) -> bool:
    s = line.strip()

    if len(s) < 5:
        return True

    # ToC leader dots
    if re.search(r"\.{3,}", s):
        return True

    # Page numbers
    if re.fullmatch(r"\d{1,3}", s):
        return True

    # Bullet-only
    if set(s) <= set(".·•-–—"):
        return True

    return False


def split_sentences(text: str):
    return sent_tokenize(text)

def sentence_quality_filter(s: str) -> bool:
    s = s.strip()

    # Length
    if len(s) < 15:
        return False

    # Punctuation-only
    if set(s) <= set(".·•-–—"):
        return False

    # Alphabetic ratio
    alpha_ratio = sum(c.isalpha() for c in s) / len(s)
    if alpha_ratio < 0.3:
        return False

    # Numeric-heavy (tables, charts)
    digit_ratio = sum(c.isdigit() for c in s) / len(s)
    if digit_ratio > 0.4:
        return False

    # No verbs → often table headers
    if not re.search(r"\b(is|are|was|were|has|have|had|will|can|may)\b", s.lower()):
        return False

    return True



def section_allowed(section_title: str) -> bool:
    title = section_title.lower()
    return not any(x in title for x in EXCLUDED_SECTIONS)
    

def sentence_quality_filter_debug(s: str):
    reasons = []

    if len(s) < 15:
        reasons.append("too_short")

    if set(s) <= set(".·•-–—"):
        reasons.append("punct_only")

    alpha_ratio = sum(c.isalpha() for c in s) / max(len(s), 1)
    if alpha_ratio < 0.3:
        reasons.append("low_alpha")

    digit_ratio = sum(c.isdigit() for c in s) / max(len(s), 1)
    if digit_ratio > 0.4:
        reasons.append("numeric_heavy")

    # if not re.search(r"\b(is|are|was|were|has|have|had|will|can|may)\b", s.lower()):
    #     reasons.append("no_aux_verb")

    return reasons



def clean_document(raw_blocks, report_id, row_id=None, debug=False):
    records = []
    debug_log = []

    for block_idx, block in enumerate(raw_blocks):
        texts = extract_texts_from_block(block)

        for text_idx, text in enumerate(texts):
            text = normalize_text(text)
            if not text:
                continue

            if is_structural_junk(text):
                continue

            for sent_idx, s in enumerate(sent_tokenize(text)):
                if debug:
                    reasons = sentence_quality_filter_debug(s)
                    if not reasons:
                        records.append({
                            "row_id": row_id,
                            "block_idx": block_idx,
                            "text_idx": text_idx,
                            "sent_idx": sent_idx,
                            "clean_sentence": s,
                            "report_id": report_id
                        })
                    else:
                        debug_log.append((s, reasons))
                else:
                    if sentence_quality_filter(s):
                        records.append({
                            "row_id": row_id,
                            "block_idx": block_idx,
                            "text_idx": text_idx,
                            "sent_idx": sent_idx,
                            "clean_sentence": s,
                            "report_id": report_id
                        })
              
    if not records:
        records.append({
            "row_id": row_id,
            "block_idx": None,
            "text_idx": None,
            "sent_idx": None,
            "clean_sentence": None,
            "report_id": report_id
        })
    
    if debug:
        return records, debug_log
    return records


    if debug:
        return records, debug_log
    return records



def extract_texts_from_block(block):
    texts = []

    if not isinstance(block, dict):
        return texts

    for key in ["text", "content", "paragraph", "lines", "sentences"]:
        if key not in block:
            continue

        val = block[key]

        if isinstance(val, str):
            texts.append(val)

        elif isinstance(val, list):
            texts.extend([v for v in val if isinstance(v, str)])

    return texts

