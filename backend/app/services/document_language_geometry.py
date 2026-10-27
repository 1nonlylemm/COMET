"""Fail-closed PDF character geometry for language issues; no heuristic boxes."""
import re
import unicodedata

import pdfplumber
from pdfminer.pdfexceptions import PDFException


def _normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value or '').casefold() if c.isalnum())


def _pattern(value):
    return r'(?<!\w)' + r'\s+'.join(re.escape(s) for s in unicodedata.normalize('NFKC', value).split()) + r'(?!\w)'


def issue_anchors(text, issues, *, page_count=None, limit=20):
    """Offsets refer to the exact stripped text submitted to LanguageTool."""
    text = (text or '').strip()
    output = []
    for index, issue in enumerate(issues[:limit]):
        target = str(issue.get('matched_text') or '')
        try:
            start, length = int(issue['offset']), int(issue['length'])
            valid = start >= 0 and length > 0 and text[start:start + length].strip() == target.strip()
        except (KeyError, TypeError, ValueError):
            start, length, valid = None, None, False
        before = text[max(0, start - 48):start] if valid else ''
        after = text[start + length:start + length + 48] if valid else ''
        occurrence = len(list(re.finditer(_pattern(target), unicodedata.normalize('NFKC', text[:start]), re.I))) if valid and target.strip() else None
        page = 1 if page_count == 1 else None
        output.append({
            'issue_index': index, 'text': target, 'matched_text': target,
            'context_before': before, 'context_after': after,
            'occurrence_index': occurrence, 'char_start': start, 'char_end': start + length if valid else None,
            'offset': start, 'length': length, 'anchor_valid': valid,
            'page': page, 'resolution_state': 'page_marker' if page else 'none',
            'bbox': None, 'bbox_type': 'page_marker', 'renderable': False,
        })
    return output


def _box(chars, page):
    x0, y0, x1, y1 = page.cropbox or page.bbox
    box = {'x': (min(c['x0'] for c in chars) - x0) / (x1 - x0),
           'y': (min(c['top'] for c in chars) - y0) / (y1 - y0),
           'width': (max(c['x1'] for c in chars) - min(c['x0'] for c in chars)) / (x1 - x0),
           'height': (max(c['bottom'] for c in chars) - min(c['top'] for c in chars)) / (y1 - y0)}
    if min(box.values()) < 0 or box['width'] <= 0 or box['height'] <= 0 or box['x'] + box['width'] > 1 or box['y'] + box['height'] > 1:
        return None
    return box


def _fragments(chars, page):
    groups = []
    for char in chars:
        axis = 'top' if char.get('upright', True) else 'x0'
        if not groups or abs(groups[-1][-1][axis] - char[axis]) > 2:
            groups.append([])
        groups[-1].append(char)
    return [_box(group, page) for group in groups]


def resolve_language_geometry(anchors, file_path, *, max_pages=20):
    """Require unique context AND the declared occurrence; ambiguity stays a marker.

    Character unions come from pdfplumber, normalized to the displayed CropBox.
    Different extraction orders, missing offsets, scans, or parse errors never
    fall back to estimated coordinates. No document text leaves this process.
    """
    output = [dict(anchor) for anchor in anchors]
    try:
        with pdfplumber.open(file_path) as pdf:
            pages = list(pdf.pages[:max_pages])
            for anchor in output:
                if not anchor.get('matched_text', '').strip():
                    continue
                pattern = _pattern(anchor['matched_text'])
                candidates = []
                for number, page in enumerate(pages, 1):
                    text = page.extract_text() or ''
                    spans = list(re.finditer(pattern, text, re.I))
                    matches = page.search(pattern, case=False, return_chars=True) or []
                    if len(spans) != len(matches):
                        continue
                    for span, match in zip(spans, matches):
                        before, after = _normalized(anchor['context_before']), _normalized(anchor['context_after'])
                        context_matches = (not before or _normalized(text[:span.start()]).endswith(before[-24:])) and (not after or _normalized(text[span.end():]).startswith(after[:24]))
                        candidates.append({'page': number, 'bbox': _box(match['chars'], page),
                            'boxes': _fragments(match['chars'], page), 'context_matches': context_matches})
                candidate_pages = {candidate['page'] for candidate in candidates}
                if len(candidate_pages) == 1:
                    anchor['page'] = next(iter(candidate_pages))
                anchor['resolution_state'] = 'page_marker' if anchor.get('page') else 'none'
                valid = [candidate for candidate in candidates if candidate['context_matches']]
                occurrence = anchor.get('occurrence_index')
                if (anchor.get('anchor_valid') and len(valid) == 1 and isinstance(occurrence, int)
                        and occurrence < len(candidates) and candidates[occurrence] is valid[0]
                        and valid[0]['bbox'] and all(valid[0]['boxes'])):
                    selected = valid[0]
                    anchor.update(page=selected['page'], bbox=selected['bbox'], boxes=selected['boxes'],
                        geometry_source='pdfplumber', resolution_state='verified_box',
                        bbox_type='verified_text', renderable=True)
    except (OSError, ValueError, TypeError, PDFException):
        # Keep the trustworthy page metadata, never invent a rectangle.
        pass
    return output
