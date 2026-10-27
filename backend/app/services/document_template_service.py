from io import BytesIO
import html
import os
from pathlib import Path
import re
import tempfile
import zipfile
# Standard ElementTree is only used for namespace registration; parsing uses defusedxml.
from xml.etree import ElementTree as StdET  # nosec B405

from defusedxml import ElementTree as ET
from flask import current_app
from jinja2.sandbox import SandboxedEnvironment, SecurityError
from jinja2.exceptions import TemplateError as JinjaTemplateError

from app.services.upload_validation import ArchiveSecurityError, validate_ooxml_container

DOCX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

WORD_TEXT_PARTS = re.compile(
    r'^word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$',
    re.IGNORECASE,
)
ANGLE_TEXT_RE = re.compile(r'<([^<>]{1,180})>')
ANGLE_XML_RE = re.compile(r'&lt;(.{1,180}?)&gt;')
JINJA_RE = re.compile(r'\{\{\s*([^{}]{1,220}?)\s*\}\}')
VALID_CONTEXT_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
JINJA_EXPRESSION_HINTS = ('|', '.', '[', ']', '(', ')', '+', '*', '/', '%', '~', '"', "'")
WORD_NAMESPACE = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_NAMESPACE = 'http://www.w3.org/XML/1998/namespace'

StdET.register_namespace('w', WORD_NAMESPACE)

PLACEHOLDER_ALIASES = {
    'date': 'date',
    'notice date': 'date',
    'generated date': 'date',
    'name of local chief executive': 'lce_name_upper',
    'local chief executive': 'lce_name_upper',
    'position of local chief executive': 'lce_position',
    'name of lgu city region': 'lgu_display',
    'name of lgu city province': 'lgu_display',
    'name of lgu province region': 'lgu_display',
    'name of lgu city municipality region': 'lgu_display',
    'subject': 'subject_line',
    'surname of lce': 'lce_surname',
    'content': 'content',
    'dilg director': 'signatory_name',
    'dilg provincial director': 'provincial_director_name',
    'director s name': 'director_name',
    'director name': 'signatory_name',
    'directors name': 'signatory_name',
    'signatory name': 'signatory_name',
    'signatory title': 'signatory_title',
    'region': 'region_name',
    'province': 'province_name',
    'regional office address': 'regional_office_address',
    'regional office official website': 'regional_office_website',
    'official website': 'regional_office_website',
    'program title': 'program_title',
    'year of program covering project': 'fiscal_year',
    'funding year': 'funding_year',
    'program year': 'fiscal_year',
    'date of notice of non compliance no 1': 'annex_m_date_display',
    'date of notice of non compliance no 1 and 2': 'prior_nnc_dates_display',
    'name of pd': 'provincial_director_name',
    'pd name': 'provincial_director_name',
    'regional director s name': 'regional_director_name',
    'full title of projects': 'project_name',
    'full title of project s': 'project_name',
    'full title of project': 'project_name',
    'indicate full title of project s': 'project_names_text',
    'indicate full title of projects': 'project_names_text',
    'list of findings or copy of aide memoire': 'findings_text',
    'list of recommendations or copy of aide memoire': 'recommendations_text',
    'indicate all findings or attach copy of aide memoire': 'findings_text',
    'indicate all recommendations or attach copy of aide memoire': 'recommendations_text',
    'allocation': 'budget_allocation_text',
    'budget allocation': 'budget_allocation_text',
    'amount as per nadai': 'budget_allocation_text',
    'indicate amount as per nadai': 'budget_allocation_text',
    'compliance period': 'compliance_period_text',
    'indicate exact date as per aide memoire': 'compliance_period_text',
    'exact date as per aide memoire': 'compliance_period_text',
    'exact date based on aided memoire': 'aide_memoire_date_display',
    'exact date based on aide memoire': 'aide_memoire_date_display',
}

KEY_LABELS = {
    'date': 'Date',
    'lce_name_upper': 'Name of Local Chief Executive',
    'lce_position': 'Position of Local Chief Executive',
    'lgu_display': 'Name of LGU, City, Region',
    'subject_line': 'Subject',
    'lce_surname': 'Surname of LCE',
    'content': 'Content',
    'province_name': 'Province',
    'director_name': 'Director Name',
    'director_title': 'Director Title',
    'provincial_director_name': 'DILG Provincial Director',
    'provincial_director_title': 'Provincial Director Title',
    'regional_director_name': "Regional Director's Name",
    'regional_director_title': 'Regional Director Title',
    'office_name': 'Office Name',
    'prepared_by_name': 'Prepared By Name',
    'prepared_by_title': 'Prepared By Title',
    'signatory_name': 'DILG Director',
    'signatory_title': 'Signatory Title',
    'region_name': 'Region',
    'regional_office_address': 'Regional Office Address',
    'regional_office_website': 'Regional Office Official Website',
    'program_title': 'Program Title',
    'fiscal_year': 'Year of Program Covering Project',
    'funding_year': 'Funding Year',
    'annex_m_date_display': 'Date of Notice of Non-Compliance No. 1',
    'annex_n_date_display': 'Date of Notice of Non-Compliance No. 2',
    'prior_nnc_dates_display': 'Dates of Notice of Non-Compliance No. 1 and 2',
    'project_name': 'Full Title of Project/s',
    'project_names_text': 'Full Title of Project/s',
    'findings_text': 'List of Findings or Copy of Aide Memoire',
    'recommendations_text': 'List of Recommendations or Copy of Aide Memoire',
    'budget_allocation_text': 'Allocation',
    'compliance_period_text': 'Compliance Period',
    'aide_memoire_date_display': 'Exact Date Based on Aide Memoire',
}


class DocumentTemplateError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class CometDocxSandboxedEnvironment(SandboxedEnvironment):
    """Restricted SandboxedEnvironment for docxtpl rendering that blocks all dangerous attributes,
    dunder traversal, dangerous callables, and arbitrary Python execution.
    """
    def is_safe_attribute(self, obj, attr, value):
        if attr.startswith('_'):
            return False
        if attr in (
            'format', 'format_map',
            'mro', 'subclasses', 'bases',
            'globals', 'builtins', 'code',
            'func_globals', 'func_code', 'func_closure',
            'gi_frame', 'gi_code', 'cr_frame', 'cr_code',
        ):
            return False
        return super().is_safe_attribute(obj, attr, value)

    def is_safe_callable(self, obj):
        if isinstance(obj, type):
            return False
        if getattr(obj, '__module__', '').startswith(('os', 'subprocess', 'sys', 'builtins', 'posix', 'nt')):
            return False
        return super().is_safe_callable(obj)


PROHIBITED_TEMPLATE_TOKENS = re.compile(
    r'__[a-zA-Z]|\bimport\b|\bos\.|\bsubprocess\b|\bsystem\b|\beval\b|\bexec\b|\bbuiltins\b|\bglobals\b|\blipsum\b|\bcycler\b|\bjoiner\b|\bnamespace\b',
    re.IGNORECASE,
)


def _validate_docx_template_safety(path_or_file):
    """Inspects XML contents of a DOCX archive to ensure no active code or dangerous Jinja expressions exist."""
    source = path_or_file
    if isinstance(path_or_file, (bytes, bytearray)):
        source = BytesIO(path_or_file)
    elif hasattr(path_or_file, 'stream'):
        source = path_or_file.stream

    try:
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if WORD_TEXT_PARTS.match(name):
                    xml_content = archive.read(name).decode('utf-8', errors='ignore')
                    if PROHIBITED_TEMPLATE_TOKENS.search(xml_content):
                        raise DocumentTemplateError(
                            'Uploaded document template contains prohibited expression or active code.',
                            422,
                        )
    except DocumentTemplateError:
        raise
    except Exception as exc:
        raise DocumentTemplateError(f'Document template validation error: {exc}', 422) from exc


def extract_docx_placeholders(path):
    try:
        validate_ooxml_container(path, expected_kind='docx')
        _validate_docx_template_safety(path)
    except (ArchiveSecurityError, DocumentTemplateError) as exc:
        message = getattr(exc, 'message', str(exc))
        raise DocumentTemplateError(message, 422) from exc

    placeholders = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not WORD_TEXT_PARTS.match(name):
                    continue
                text = _extract_text_from_xml(archive.read(name))
                placeholders.extend(_scan_text_placeholders(text))
    except (OSError, zipfile.BadZipFile) as exc:
        raise DocumentTemplateError('Uploaded document template could not be scanned.', 422) from exc

    return _dedupe_placeholders(placeholders)


def render_docx_template(template_path, context):
    try:
        validate_ooxml_container(template_path, expected_kind='docx')
        _validate_docx_template_safety(template_path)
    except (ArchiveSecurityError, DocumentTemplateError) as exc:
        message = getattr(exc, 'message', str(exc))
        raise DocumentTemplateError(message, 422) from exc

    normalized_context = expand_context_aliases(context or {})
    template_bytes = _normalize_template_bytes(template_path)
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix='.docx')
        with os.fdopen(fd, 'wb') as handle:
            handle.write(template_bytes)

        DocxTemplate = _import_docxtemplate()
        template = DocxTemplate(temp_path)
        sandboxed_env = CometDocxSandboxedEnvironment()
        try:
            template.render(normalized_context, jinja_env=sandboxed_env)
        except (SecurityError, JinjaTemplateError) as exc:
            raise DocumentTemplateError(f'Template security violation: {exc}', 422) from exc

        buffer = BytesIO()
        template.save(buffer)
        buffer.seek(0)
        return repair_docx_styles(replace_placeholders_in_docx(buffer.read(), normalized_context))
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def replace_placeholders_in_docx(content, context):
    normalized_context = expand_context_aliases(context or {})
    source = BytesIO(content)
    target = BytesIO()
    try:
        with zipfile.ZipFile(source, 'r') as zin, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                    text = data.decode('utf-8')
                    text = ANGLE_XML_RE.sub(lambda match: _xml_placeholder_value(match.group(1), normalized_context), text)
                    text = JINJA_RE.sub(lambda match: _jinja_placeholder_value(match, normalized_context), text)
                    text = _replace_split_placeholders_in_xml(text, normalized_context)
                    data = text.encode('utf-8')
                zout.writestr(item, data)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError):
        return content
    target.seek(0)
    return target.read()


def repair_docx_styles(content):
    source = BytesIO(content)
    target = BytesIO()
    changed = False
    try:
        with zipfile.ZipFile(source, 'r') as zin, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/styles.xml':
                    repaired = _repair_styles_xml(data)
                    changed = changed or repaired != data
                    data = repaired
                zout.writestr(item, data)
    except (OSError, zipfile.BadZipFile):
        return content
    if not changed:
        return content
    target.seek(0)
    return target.read()


def build_template_variables(template_info, context, placeholder_overrides=None):
    normalized_context = expand_context_aliases(context or {})
    overrides = _nonblank_placeholder_values(placeholder_overrides)
    definitions = _template_placeholder_definitions(template_info)
    variables = []
    for definition in definitions:
        key = definition.get('key')
        if not key:
            continue
        value = overrides.get(key, normalized_context.get(key, ''))
        variables.append({
            'key': key,
            'label': definition.get('label') or label_for_key(key),
            'value': '' if value is None else str(value),
            'source': 'override' if key in overrides else 'system',
            'syntax': definition.get('syntax') or [],
        })
    return variables


def _nonblank_placeholder_values(values):
    if not isinstance(values, dict):
        return {}
    cleaned = {}
    for key, value in values.items():
        cleaned_key = str(key).strip()
        if not cleaned_key or value is None:
            continue
        cleaned_value = str(value)
        if not cleaned_value.strip():
            continue
        cleaned[cleaned_key] = cleaned_value
    return cleaned


def preview_docx_text(content, max_chars=6000):
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            parts = []
            for name in archive.namelist():
                if not WORD_TEXT_PARTS.match(name):
                    continue
                parts.extend(_extract_paragraphs_from_xml(archive.read(name)))
    except (OSError, zipfile.BadZipFile):
        return ''

    text = '\n'.join(part for part in parts if part.strip())
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text[:max_chars]


def preview_docx_document(content, max_blocks=140, max_chars=18000):
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if 'word/document.xml' not in archive.namelist():
                return {'blocks': [], 'truncated': False}
            part_names = [
                *sorted(name for name in archive.namelist() if re.match(r'^word/header\d+\.xml$', name)),
                'word/document.xml',
                *sorted(name for name in archive.namelist() if re.match(r'^word/footer\d+\.xml$', name)),
            ]
            blocks = []
            truncated = False
            for name in part_names:
                if len(blocks) >= max_blocks:
                    truncated = True
                    break
                part_blocks, part_truncated = _extract_preview_blocks_from_xml(
                    archive.read(name),
                    max_blocks=max_blocks - len(blocks),
                    max_chars=max_chars - _preview_blocks_char_count(blocks),
                )
                blocks.extend(part_blocks)
                if part_truncated:
                    truncated = True
                    break
    except (OSError, zipfile.BadZipFile):
        return {'blocks': [], 'truncated': False}

    return {
        'blocks': blocks,
        'truncated': truncated,
    }


def expand_context_aliases(context):
    expanded = {
        str(key): '' if value is None else value
        for key, value in (context or {}).items()
    }
    if 'date' not in expanded:
        expanded['date'] = expanded.get('notice_date_display') or expanded.get('generated_at_display') or ''
    if 'subject' not in expanded:
        expanded['subject'] = expanded.get('subject_line') or expanded.get('report_title') or expanded.get('notice_title') or ''
    if 'content' not in expanded:
        pieces = [
            expanded.get('default_body_text'),
            expanded.get('custom_body_text'),
            expanded.get('revision_rows_text'),
        ]
        expanded['content'] = '\n\n'.join(str(item) for item in pieces if item)
    if 'name_of_local_chief_executive' not in expanded:
        expanded['name_of_local_chief_executive'] = expanded.get('lce_name_upper') or expanded.get('lce_name') or ''
    if 'dilg_director' not in expanded:
        expanded['dilg_director'] = expanded.get('signatory_name') or expanded.get('director_name') or ''
    if 'province' not in expanded:
        expanded['province'] = expanded.get('province_name') or ''
    if 'funding_year' not in expanded:
        expanded['funding_year'] = expanded.get('fiscal_year') or ''
    if 'dilg_provincial_director' not in expanded:
        expanded['dilg_provincial_director'] = (
            expanded.get('provincial_director_name')
            or expanded.get('signatory_name')
            or expanded.get('director_name')
            or ''
        )
    if 'name_of_pd' not in expanded:
        expanded['name_of_pd'] = expanded.get('provincial_director_name') or ''
    if 'regional_directors_name' not in expanded:
        expanded['regional_directors_name'] = expanded.get('regional_director_name') or ''
    if 'director_name' in expanded and 'signatory_name' not in expanded:
        expanded['signatory_name'] = expanded['director_name']
    if 'director_title' in expanded and 'signatory_title' not in expanded:
        expanded['signatory_title'] = expanded['director_title']
    return expanded


def placeholder_key(label):
    cleaned = _clean_label(label)
    canonical = _canonical_label(cleaned)
    if '_' in cleaned and VALID_CONTEXT_KEY_RE.match(cleaned):
        return cleaned
    if canonical in PLACEHOLDER_ALIASES:
        return PLACEHOLDER_ALIASES[canonical]
    if VALID_CONTEXT_KEY_RE.match(cleaned):
        return cleaned
    return _slug_label(cleaned)


def label_for_key(key):
    return KEY_LABELS.get(key) or str(key or '').replace('_', ' ').strip().title()


def _normalize_template_bytes(template_path):
    source = BytesIO()
    zin_target = BytesIO(template_path) if isinstance(template_path, (bytes, bytearray)) else template_path
    with zipfile.ZipFile(zin_target, 'r') as zin, zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                text = data.decode('utf-8')
                text = ANGLE_XML_RE.sub(lambda match: f'{{{{ {placeholder_key(match.group(1))} }}}}', text)
                text = JINJA_RE.sub(_normalize_jinja_placeholder, text)
                text = _replace_split_placeholders_in_xml(text, normalize=True)
                data = text.encode('utf-8')
            zout.writestr(item, data)
    source.seek(0)
    return source.read()


def _normalize_jinja_placeholder(match):
    expression = _clean_label(match.group(1))
    if _looks_like_jinja_expression(expression):
        return match.group(0)
    key = placeholder_key(expression)
    if key and key != expression:
        return f'{{{{ {key} }}}}'
    return match.group(0)


def _repair_styles_xml(xml_bytes):
    try:
        xml_text = xml_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return xml_bytes

    changed = False

    def replace_self_closing_style(match):
        nonlocal changed
        tag = match.group(0)
        style_id_m = re.search(r'w:styleId="([^"]+)"', tag)
        style_id = style_id_m.group(1) if style_id_m else 'Recovered Style'
        open_tag = tag[:-2].strip() + '>'
        changed = True
        return f'{open_tag}<w:name w:val="{style_id}"/></w:style>'

    xml_text = re.sub(r'<w:style\b[^>]*?/>', replace_self_closing_style, xml_text)

    def replace_style_block(match):
        nonlocal changed
        full_block = match.group(0)
        open_tag = match.group(1)
        inner = match.group(2)
        if '<w:name' not in inner:
            style_id_m = re.search(r'w:styleId="([^"]+)"', open_tag)
            style_id = style_id_m.group(1) if style_id_m else 'Recovered Style'
            changed = True
            return f'{open_tag}<w:name w:val="{style_id}"/>{inner}</w:style>'
        empty_name_m = re.search(r'<w:name\s+w:val=""\s*/>', inner)
        if empty_name_m:
            style_id_m = re.search(r'w:styleId="([^"]+)"', open_tag)
            style_id = style_id_m.group(1) if style_id_m else 'Recovered Style'
            inner = inner.replace(empty_name_m.group(0), f'<w:name w:val="{style_id}"/>')
            changed = True
            return f'{open_tag}{inner}</w:style>'
        return full_block

    repaired_text = re.sub(r'(<w:style\b[^>]*>)([\s\S]*?)</w:style>', replace_style_block, xml_text)
    if not changed:
        return xml_bytes
    return repaired_text.encode('utf-8')


def _looks_like_jinja_expression(expression):
    if any(marker in expression for marker in JINJA_EXPRESSION_HINTS):
        return True
    words = expression.split()
    if len(words) > 1 and all(VALID_CONTEXT_KEY_RE.match(word) for word in words):
        return False
    return False


def _jinja_placeholder_value(match, context):
    expression = _clean_label(match.group(1))
    if _looks_like_jinja_expression(expression):
        return match.group(0)
    key = placeholder_key(expression)
    if key not in context:
        return match.group(0)
    return html.escape(str(context.get(key) or ''), quote=False)


def _xml_placeholder_value(label, context):
    key = placeholder_key(label)
    if key not in context:
        return f'&lt;{html.escape(label, quote=False)}&gt;'
    return html.escape(str(context.get(key) or ''), quote=False)


def _extract_text_from_xml(xml_bytes):
    return '\n'.join(_extract_paragraphs_from_xml(xml_bytes))


def _extract_paragraphs_from_xml(xml_bytes):
    namespace = {'w': WORD_NAMESPACE}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    paragraphs = []
    for paragraph in root.findall('.//w:p', namespace):
        text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace))
        if text:
            paragraphs.append(text)
    if not paragraphs:
        text = ''.join(node.text or '' for node in root.findall('.//w:t', namespace))
        if text:
            paragraphs.append(text)
    return paragraphs


def _extract_preview_blocks_from_xml(xml_bytes, max_blocks, max_chars):
    if max_blocks <= 0 or max_chars <= 0:
        return [], True
    namespace = {'w': WORD_NAMESPACE}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return [], False

    body = root.find('.//w:body', namespace)
    container = body if body is not None else root

    blocks = []
    char_count = 0
    truncated = False
    for child in list(container):
        if len(blocks) >= max_blocks or char_count >= max_chars:
            truncated = True
            break

        if child.tag == _word_tag('p'):
            text = _paragraph_preview_text(child).strip()
            if not text:
                continue
            block = {
                'type': 'paragraph',
                'text': text[:max_chars - char_count],
                'align': _paragraph_alignment(child),
                'style': _paragraph_style(child),
            }
            char_count += len(block['text'])
            blocks.append(block)
        elif child.tag == _word_tag('tbl'):
            table = _table_preview_block(child, max_chars - char_count)
            if not table:
                continue
            char_count += sum(
                len(cell.get('text') or '')
                for row in table['rows']
                for cell in row
            )
            blocks.append(table)

    return blocks, truncated


def _preview_blocks_char_count(blocks):
    count = 0
    for block in blocks or []:
        if block.get('type') == 'table':
            count += sum(
                len(cell.get('text') or '')
                for row in block.get('rows') or []
                for cell in row
            )
        else:
            count += len(block.get('text') or '')
    return count


def _word_tag(name):
    return f'{{{WORD_NAMESPACE}}}{name}'


def _paragraph_preview_text(paragraph):
    pieces = []
    for node in paragraph.iter():
        if node.tag == _word_tag('t'):
            pieces.append(node.text or '')
        elif node.tag == _word_tag('tab'):
            pieces.append('\t')
        elif node.tag in {_word_tag('br'), _word_tag('cr')}:
            pieces.append('\n')
    return ''.join(pieces)


def _paragraph_alignment(paragraph):
    namespace = {'w': WORD_NAMESPACE}
    justification = paragraph.find('./w:pPr/w:jc', namespace)
    value = justification.get(_word_tag('val')) if justification is not None else None
    if value in {'center', 'right', 'both'}:
        return 'justify' if value == 'both' else value
    return 'left'


def _paragraph_style(paragraph):
    namespace = {'w': WORD_NAMESPACE}
    style = paragraph.find('./w:pPr/w:pStyle', namespace)
    value = style.get(_word_tag('val')) if style is not None else ''
    return value or ''


def _table_preview_block(table, remaining_chars):
    namespace = {'w': WORD_NAMESPACE}
    rows = []
    char_count = 0
    for row in table.findall('./w:tr', namespace):
        cells = []
        for cell in row.findall('./w:tc', namespace):
            paragraphs = [
                _paragraph_preview_text(paragraph).strip()
                for paragraph in cell.findall('.//w:p', namespace)
            ]
            text = '\n'.join(item for item in paragraphs if item)
            if char_count + len(text) > remaining_chars:
                text = text[:max(0, remaining_chars - char_count)]
            char_count += len(text)
            cells.append({'text': text})
        if cells:
            rows.append(cells)
        if char_count >= remaining_chars:
            break
    if not rows:
        return None
    return {
        'type': 'table',
        'rows': rows,
    }


def _replace_split_placeholders_in_xml(xml_text, context=None, normalize=False):
    if '<w:t' not in xml_text and '<ns0:t' not in xml_text:
        return xml_text
    if not any(marker in xml_text for marker in ('&lt;', '{{')):
        return xml_text

    namespace = {'w': WORD_NAMESPACE}
    try:
        root = ET.fromstring(xml_text.encode('utf-8'))
    except ET.ParseError:
        return xml_text

    changed = False
    for paragraph in root.findall('.//w:p', namespace):
        text_nodes = paragraph.findall('.//w:t', namespace)
        if len(text_nodes) < 2:
            continue
        combined = ''.join(node.text or '' for node in text_nodes)
        if not combined or not (ANGLE_TEXT_RE.search(combined) or JINJA_RE.search(combined)):
            continue

        if normalize:
            replacement = ANGLE_TEXT_RE.sub(lambda match: f'{{{{ {placeholder_key(match.group(1))} }}}}', combined)
            replacement = JINJA_RE.sub(_normalize_jinja_placeholder, replacement)
        else:
            normalized_context = context or {}
            replacement = ANGLE_TEXT_RE.sub(
                lambda match: _plain_placeholder_value(match.group(1), normalized_context),
                combined,
            )
            replacement = JINJA_RE.sub(
                lambda match: html.unescape(_jinja_placeholder_value(match, normalized_context)),
                replacement,
            )

        if replacement == combined:
            continue
        text_nodes[0].text = replacement
        text_nodes[0].set(f'{{{XML_NAMESPACE}}}space', 'preserve')
        for node in text_nodes[1:]:
            node.text = ''
        changed = True

    if not changed:
        return xml_text
    return ET.tostring(root, encoding='unicode')


def _plain_placeholder_value(label, context):
    key = placeholder_key(label)
    if key not in context:
        return f'<{label}>'
    return str(context.get(key) or '')


def _scan_text_placeholders(text):
    placeholders = []
    for match in ANGLE_TEXT_RE.finditer(text or ''):
        label = _clean_label(match.group(1))
        if label:
            placeholders.append(_placeholder_definition(label, 'angle'))
    for match in JINJA_RE.finditer(text or ''):
        expression = _clean_label(match.group(1))
        if not expression:
            continue
        if _looks_like_jinja_expression(expression):
            key_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\b', expression)
            if not key_match:
                continue
            label = key_match.group(1)
        else:
            label = expression
        placeholders.append(_placeholder_definition(label, 'curly'))
    return placeholders


def _placeholder_definition(label, syntax):
    key = placeholder_key(label)
    return {
        'key': key,
        'label': label_for_key(key) if key in KEY_LABELS else label,
        'syntax': [syntax],
    }


def _dedupe_placeholders(placeholders):
    ordered = []
    by_key = {}
    for item in placeholders:
        key = item.get('key')
        if not key:
            continue
        if key not in by_key:
            by_key[key] = {
                'key': key,
                'label': item.get('label') or label_for_key(key),
                'syntax': [],
            }
            ordered.append(by_key[key])
        for syntax in item.get('syntax') or []:
            if syntax not in by_key[key]['syntax']:
                by_key[key]['syntax'].append(syntax)
    return ordered


def _template_placeholder_definitions(template_info):
    definitions = []
    if template_info:
        definitions = template_info.get('placeholder_definitions') or []
    normalized = []
    seen = set()
    for item in definitions:
        if isinstance(item, str):
            key = placeholder_key(item)
            definition = {'key': key, 'label': label_for_key(key), 'syntax': []}
        elif isinstance(item, dict):
            key = item.get('key') or placeholder_key(item.get('label') or '')
            definition = {
                'key': key,
                'label': item.get('label') or label_for_key(key),
                'syntax': item.get('syntax') or [],
            }
        else:
            continue
        if definition['key'] and definition['key'] not in seen:
            seen.add(definition['key'])
            normalized.append(definition)
    return normalized


def _clean_label(label):
    value = html.unescape(str(label or '')).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', value).strip()


def _canonical_label(label):
    value = _clean_label(label).casefold()
    value = re.sub(r'[/\\]+', ' ', value)
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _slug_label(label):
    value = _canonical_label(label)
    return re.sub(r'[^a-z0-9]+', '_', value).strip('_')


def _import_docxtemplate():
    try:
        from docxtpl import DocxTemplate
    except Exception as exc:
        raise DocumentTemplateError(f'docxtpl is required for DOCX template rendering: {exc}', 500)
    return DocxTemplate


GENERAL_TEMPLATE_FILENAME = 'General Template.docx'


def get_general_template_path() -> Path | None:
    """Return the validated canonical Path to General Template.docx, or None if unavailable.

    Verifies that the template exists and passes OOXML container and template safety checks.
    """
    candidates = []
    try:
        if current_app:
            app_root = Path(current_app.root_path).resolve()
            candidates.append(app_root.parent / 'seed_assets' / 'reference_templates' / GENERAL_TEMPLATE_FILENAME)
            candidates.append(app_root / 'seed_assets' / 'reference_templates' / GENERAL_TEMPLATE_FILENAME)
    except Exception:
        pass

    pkg_root = Path(__file__).resolve().parents[2]
    candidates.append(pkg_root / 'seed_assets' / 'reference_templates' / GENERAL_TEMPLATE_FILENAME)
    candidates.append(Path('/app/seed_assets/reference_templates') / GENERAL_TEMPLATE_FILENAME)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            try:
                validate_ooxml_container(candidate, expected_kind='docx')
                _validate_docx_template_safety(candidate)
                return candidate
            except Exception:
                continue
    return None


def resolve_document_template(
    document_type: str,
    template_id: str | None = None,
    allow_general_fallback: bool = True,
) -> dict | None:
    """Resolve a document template according to the 4-tier hierarchy:
    Tier 1: Administrator-configured feature-specific template (Settings catalog / SystemConfig)
    Tier 2: Official / feature-specific seeded template on disk
    Tier 3: Approved General Template fallback (General Template.docx)
    Tier 4: None (Caller falls back to emergency raw programmatic builder)
    """
    # Tier 1: Configured template in Settings
    try:
        from app.services import settings_service
        configured = settings_service.get_document_template(document_type, template_id=template_id)
        if configured and configured.get('path'):
            path = Path(configured['path'])
            if path.exists() and path.is_file():
                validate_ooxml_container(path, expected_kind='docx')
                _validate_docx_template_safety(path)
                return {
                    'tier': 'configured',
                    'document_type': document_type,
                    'path': path,
                    'template_id': configured.get('id'),
                    'label': configured.get('label') or configured.get('file_name'),
                    'file_name': configured.get('file_name') or path.name,
                    'is_fallback': False,
                    'template_info': configured,
                }
    except Exception:
        pass

    # Tier 2: Official / feature-specific seeded template on disk
    seed_dirs = []
    try:
        if current_app:
            seed_dirs.append(Path(current_app.root_path).parent / 'seed_assets' / 'reference_templates')
            seed_dirs.append(Path(current_app.root_path) / 'seed_assets' / 'reference_templates')
    except Exception:
        pass
    seed_dirs.append(Path(__file__).resolve().parents[2] / 'seed_assets' / 'reference_templates')
    seed_dirs.append(Path('/app/seed_assets/reference_templates'))

    specific_filenames = {
        'annex_m': 'Annex M - Notice of Non-Compliance No. 1.docx',
        'annex_n': 'Annex N - Notice of Non-Compliance No. 2.docx',
        'annex_o': 'Annex O - Notice of Non-Compliance No. 3.docx',
        'project_revision_report': 'project_revision_report.docx',
    }.get(document_type)

    if specific_filenames:
        for sdir in seed_dirs:
            candidate = sdir / specific_filenames
            if candidate.exists() and candidate.is_file():
                try:
                    validate_ooxml_container(candidate, expected_kind='docx')
                    _validate_docx_template_safety(candidate)
                    return {
                        'tier': 'seeded',
                        'document_type': document_type,
                        'path': candidate,
                        'template_id': None,
                        'label': candidate.stem,
                        'file_name': candidate.name,
                        'is_fallback': False,
                        'template_info': None,
                    }
                except Exception:
                    continue

    # Tier 3: Approved General Template Fallback
    if allow_general_fallback:
        general_path = get_general_template_path()
        if general_path:
            return {
                'tier': 'general_fallback',
                'document_type': document_type,
                'path': general_path,
                'template_id': None,
                'label': 'DILG Laguna General Letterhead Template',
                'file_name': GENERAL_TEMPLATE_FILENAME,
                'is_fallback': True,
                'template_info': None,
            }

    # Tier 4: Caller fallback
    return None

