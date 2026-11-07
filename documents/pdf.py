"""Signed, branded PDF rendering for documents.

WeasyPrint is not used here on purpose: it depends on native GTK/Pango
libraries that are not guaranteed to be present on every deployment host. The
project already ships ReportLab (pure Python), which gives deterministic
layout, real page numbers and correct handling of transparent PNG signature
and stamp assets.

The renderer is intentionally generic: it reads the document, its line items
and the singleton :class:`documents.models.DocumentSettings`, so new document
types only need a new ``DocumentType`` row.
"""
import io
import os
from decimal import Decimal

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape

from .models import DocumentSettings

PAGE_W, PAGE_H = A4
LEFT = RIGHT = 16 * mm
TOP = 30 * mm
BOTTOM = 24 * mm
CONTENT_W = PAGE_W - LEFT - RIGHT

INK = colors.HexColor('#0F172A')
BODY = colors.HexColor('#475569')
MUTED = colors.HexColor('#94A3B8')
LINE = colors.HexColor('#E2E8F0')
SOFT = colors.HexColor('#F8FAFC')

CURRENCY_SYMBOLS = {'USD': '$', 'EUR': '\u20ac', 'GBP': '\u00a3', 'CAD': 'C$', 'AUD': 'A$'}


def money(amount, currency='USD'):
    amount = Decimal(amount or 0)
    symbol = CURRENCY_SYMBOLS.get((currency or '').upper())
    if symbol:
        return f'{symbol}{amount:,.2f}'
    return f'{currency} {amount:,.2f}'


def _hex(value, default='#4F46E5'):
    value = (value or '').strip()
    if len(value) == 7 and value.startswith('#'):
        try:
            return colors.HexColor(value)
        except Exception:
            pass
    return colors.HexColor(default)


def _text(value):
    return escape(str(value or '')).replace('\n', '<br/>')


def _file_path(field_file):
    if not field_file:
        return None
    try:
        path = field_file.path
    except (NotImplementedError, ValueError):
        return None
    return path if path and os.path.exists(path) else None


def _image(path, max_w, max_h):
    if not path:
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as image:
            width, height = image.size
        if not width or not height:
            return None
        ratio = min(max_w / float(width), max_h / float(height))
        return Image(path, width=width * ratio, height=height * ratio, mask='auto')
    except Exception:
        return None


class _NumberedCanvas(rl_canvas.Canvas):
    """Adds "Page X of Y" to the footer after the total is known."""

    def __init__(self, *args, **kwargs):
        self._footer_cb = kwargs.pop('footer_cb', None)
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._footer_cb:
                self._footer_cb(self, total)
            super().showPage()
        super().save()


def _styles(accent):
    base = ParagraphStyle(
        'doc-base', fontName='Helvetica', fontSize=9, leading=12.6, textColor=BODY,
    )
    return {
        'base': base,
        'small': ParagraphStyle('doc-small', parent=base, fontSize=7.8, leading=10.5, textColor=MUTED),
        'tiny': ParagraphStyle('doc-tiny', parent=base, fontSize=6.8, leading=9, textColor=MUTED),
        'label': ParagraphStyle(
            'doc-label', parent=base, fontSize=7, leading=9, textColor=MUTED,
            fontName='Helvetica-Bold', spaceAfter=2,
        ),
        'strong': ParagraphStyle('doc-strong', parent=base, textColor=INK, fontName='Helvetica-Bold'),
        'h1': ParagraphStyle(
            'doc-h1', parent=base, fontSize=24, leading=27, textColor=INK,
            fontName='Helvetica-Bold', alignment=TA_RIGHT,
        ),
        'h2': ParagraphStyle(
            'doc-h2', parent=base, fontSize=12, leading=15, textColor=INK,
            fontName='Helvetica-Bold', spaceAfter=4,
        ),
        'client': ParagraphStyle(
            'doc-client', parent=base, fontSize=10, leading=14, textColor=INK,
            fontName='Helvetica-Bold',
        ),
        'table_head': ParagraphStyle(
            'doc-th', parent=base, fontSize=7.5, leading=9.5, textColor=colors.white,
            fontName='Helvetica-Bold',
        ),
        'table_cell': ParagraphStyle('doc-td', parent=base, fontSize=8.4, leading=11.2),
        'table_num': ParagraphStyle(
            'doc-tdn', parent=base, fontSize=8.4, leading=11.2, alignment=TA_RIGHT,
        ),
        'total_label': ParagraphStyle('doc-tl', parent=base, fontSize=8.6, leading=12, alignment=TA_RIGHT),
        'total_value': ParagraphStyle(
            'doc-tv', parent=base, fontSize=8.6, leading=12, alignment=TA_RIGHT, textColor=INK,
        ),
        'total_grand': ParagraphStyle(
            'doc-tg', parent=base, fontSize=10.5, leading=13, alignment=TA_RIGHT,
            textColor=INK, fontName='Helvetica-Bold',
        ),
        'accent': ParagraphStyle('doc-accent', parent=base, textColor=accent, fontName='Helvetica-Bold'),
    }


def _paragraph(text, style):
    return Paragraph(_text(text), style)


def _logo_path():
    path = None
    try:
        path = finders.find('img/logo.png')
    except Exception:
        path = None
    if not path:
        fallback = os.path.join(str(settings.BASE_DIR), 'static', 'img', 'logo.png')
        path = fallback if os.path.exists(fallback) else None
    return path


def _draw_header(cv, doc, document, cfg, accent, styles, first_page):
    cv.saveState()
    cv.setFillColor(accent)
    cv.rect(0, PAGE_H - 7 * mm, PAGE_W, 7 * mm, stroke=0, fill=1)

    top_y = PAGE_H - 17 * mm
    logo = _logo_path()
    x = LEFT
    if logo:
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo) as image:
                width, height = image.size
            ratio = min((34 * mm) / float(width), (12 * mm) / float(height))
            logo_w, logo_h = width * ratio, height * ratio
            cv.drawImage(
                logo, x, top_y - logo_h + 2 * mm,
                width=logo_w, height=logo_h, mask='auto', preserveAspectRatio=True,
            )
            x += logo_w + 4 * mm
        except Exception:
            pass

    cv.setFillColor(INK)
    cv.setFont('Helvetica-Bold', 14)
    cv.drawString(x, top_y - 3 * mm, cfg.company_name or 'OnWebApp')
    cv.setFont('Helvetica', 7.5)
    cv.setFillColor(MUTED)
    cv.drawString(x, top_y - 8 * mm, (cfg.company_legal_name or cfg.company_website or '')[:70])

    # Right side: company contact block.
    right_lines = []
    if cfg.company_address:
        right_lines.extend([line for line in cfg.company_address.splitlines() if line.strip()][:3])
    contact = '  |  '.join(
        part for part in [
            cfg.company_email,
            cfg.company_phone,
            cfg.company_website,
        ] if part
    )
    if contact:
        right_lines.append(contact)
    if cfg.company_tax_id:
        right_lines.append(f'Tax ID: {cfg.company_tax_id}')

    y = top_y - 1 * mm
    for line in right_lines[:5]:
        cv.setFont('Helvetica', 7.2)
        cv.setFillColor(BODY)
        cv.drawRightString(PAGE_W - RIGHT, y, line[:90])
        y -= 3.6 * mm

    cv.setStrokeColor(LINE)
    cv.setLineWidth(0.7)
    cv.line(LEFT, PAGE_H - 34 * mm, PAGE_W - RIGHT, PAGE_H - 34 * mm)

    cv.restoreState()


def _draw_footer(cv, total, document, cfg, styles, draft, legal_note):
    cv.saveState()
    if draft:
        cv.setFont('Helvetica-Bold', 70)
        cv.setFillColor(colors.Color(0.5, 0.5, 0.5, alpha=0.06))
        cv.translate(PAGE_W / 2, PAGE_H / 2)
        cv.rotate(45)
        cv.drawCentredString(0, 0, 'DRAFT')
        cv.rotate(-45)
        cv.translate(-PAGE_W / 2, -PAGE_H / 2)

    cv.setStrokeColor(LINE)
    cv.setLineWidth(0.6)
    cv.line(LEFT, 18 * mm, PAGE_W - RIGHT, 18 * mm)

    cv.setFont('Helvetica', 7)
    cv.setFillColor(MUTED)
    left = '  \u00b7  '.join(
        part for part in [cfg.company_name, cfg.company_email, cfg.company_website] if part
    )
    cv.drawString(LEFT, 14 * mm, left[:95])
    cv.drawRightString(PAGE_W - RIGHT, 14 * mm, f'{document.reference}  \u00b7  v{document.version}')
    cv.drawCentredString(PAGE_W / 2, 14 * mm, f'Page {cv._pageNumber} of {total}')

    cv.setFont('Helvetica', 6.3)
    cv.setFillColor(MUTED)
    cv.drawString(LEFT, 10 * mm, legal_note[:150])
    cv.restoreState()


def _signature_cell(document, cfg, styles, accent, *, client=False):
    """Return a list of flowables for one signature block."""
    cell = []
    signature = document.latest_signature if client else None
    if client and signature:
        image = _image(_file_path(signature.signature_image), 150, 55)
        if image:
            cell.append(image)
        elif signature.typed_signature:
            r, g, b = accent.rgb()
            accent_hex = '#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))
            cell.append(Paragraph(
                f'<font name="Helvetica-Oblique" size="16" color="{accent_hex}">'
                f'{_text(signature.typed_signature)}</font>',
                styles['base'],
            ))
        cell.append(Spacer(1, 1.5 * mm))
        cell.append(HRFlowable(width='100%', thickness=0.7, color=MUTED, spaceBefore=0, spaceAfter=2))
        cell.append(_paragraph(signature.signer_name, styles['strong']))
        role_line = signature.signer_role or 'Client'
        cell.append(_paragraph(role_line, styles['small']))
        cell.append(_paragraph(signature.signer_email, styles['small']))
        cell.append(_paragraph(
            f'Signed electronically on {timezone.localtime(signature.signed_at):%d %b %Y at %H:%M}',
            styles['tiny'],
        ))
        return cell

    image = None if client else _image(_file_path(cfg.signature_image), 150, 55)
    if image:
        cell.append(image)
    else:
        cell.append(Spacer(1, 16 * mm))
    cell.append(Spacer(1, 1.5 * mm))
    cell.append(HRFlowable(width='100%', thickness=0.7, color=MUTED, spaceBefore=0, spaceAfter=2))
    if client:
        cell.append(_paragraph('Client signature', styles['strong']))
        cell.append(_paragraph('Name / position', styles['small']))
    else:
        cell.append(_paragraph(cfg.signatory_name or 'Authorized signatory', styles['strong']))
        cell.append(_paragraph(cfg.signatory_position or 'On behalf of the company', styles['small']))
        cell.append(_paragraph(cfg.company_name or 'OnWebApp', styles['small']))
    return cell


def _stamp_cell(cfg, styles):
    image = _image(_file_path(cfg.stamp_image), 92, 92)
    cell = []
    if image:
        cell.append(image)
        cell.append(Spacer(1, 1 * mm))
    else:
        cell.append(Spacer(1, 24 * mm))
    cell.append(_paragraph('Company stamp', styles['tiny']))
    return cell


def _signature_tables(document, cfg, styles, accent):
    tables = []
    company_table = Table(
        [[_signature_cell(document, cfg, styles, accent), _stamp_cell(cfg, styles)]],
        colWidths=[CONTENT_W * 0.62, CONTENT_W * 0.38],
    )
    company_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    tables.append(company_table)

    if document.doc_type.requires_signature:
        tables.append(Spacer(1, 8 * mm))
        client_table = Table(
            [[_signature_cell(document, cfg, styles, accent, client=True), '']],
            colWidths=[CONTENT_W * 0.62, CONTENT_W * 0.38],
        )
        client_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        tables.append(client_table)
    return tables


def _line_items_table(document, styles, accent):
    header = [
        _paragraph('Description', styles['table_head']),
        _paragraph('Qty', styles['table_head']),
        _paragraph('Unit price', styles['table_head']),
        _paragraph('Amount', styles['table_head']),
    ]
    rows = [header]
    items = list(document.items.all())
    if not items:
        rows.append([
            _paragraph('No line items recorded.', styles['table_cell']),
            '', '', '',
        ])
    for item in items:
        description = _text(item.description)
        if item.details:
            description += f'<br/><font size="7" color="#94A3B8">{_text(item.details)}</font>'
        rows.append([
            Paragraph(description, styles['table_cell']),
            Paragraph(f'{item.quantity:,.2f}'.rstrip('0').rstrip('.'), styles['table_num']),
            Paragraph(money(item.unit_price, document.currency), styles['table_num']),
            Paragraph(money(item.line_total, document.currency), styles['table_num']),
        ])

    table = Table(rows, colWidths=[CONTENT_W - 80 * mm, 20 * mm, 30 * mm, 30 * mm], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), accent),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINE),
        ('BOX', (0, 0), (-1, -1), 0.5, LINE),
    ]
    for index in range(1, len(rows)):
        if index % 2 == 0:
            style.append(('BACKGROUND', (0, index), (-1, index), SOFT))
    table.setStyle(TableStyle(style))
    return table


def _totals_table(document, styles, accent):
    rows = [
        [_paragraph('Subtotal', styles['total_label']),
         _paragraph(money(document.subtotal, document.currency), styles['total_value'])],
    ]
    if document.discount_amount:
        rows.append([
            _paragraph('Discount', styles['total_label']),
            _paragraph(f'-{money(document.discount_amount, document.currency)}', styles['total_value']),
        ])
    if document.tax_rate:
        rows.append([
            _paragraph(f'{_text(document.tax_label)} ({document.tax_rate:g}%)', styles['total_label']),
            _paragraph(money(document.tax_amount, document.currency), styles['total_value']),
        ])
    rows.append([
        _paragraph('Total', styles['total_grand']),
        _paragraph(money(document.total, document.currency), styles['total_grand']),
    ])
    table = Table(rows, colWidths=[42 * mm, 38 * mm], hAlign='RIGHT')
    table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, accent),
        ('LINEBELOW', (0, -1), (-1, -1), 0.8, accent),
    ]))
    return table


def _certificate_page(document, cfg, styles, accent):
    story = [PageBreak()]
    story.append(Paragraph('Signature &amp; audit certificate', ParagraphStyle(
        'cert-h', parent=styles['h2'], fontSize=16, leading=20, spaceAfter=6,
    )))
    story.append(_paragraph(
        'This certificate records how this document was issued and, where applicable, '
        'electronically signed. It is generated from the document audit trail.',
        styles['base'],
    ))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ('Document reference', document.reference),
        ('Document type', document.doc_type.name),
        ('Version', str(document.version)),
        ('Status', document.get_status_display()),
        ('Issued by', cfg.company_name or 'OnWebApp'),
        ('Generated at', timezone.localtime(timezone.now()).strftime('%d %b %Y %H:%M %Z')),
        ('PDF SHA-256', document.pdf_sha256 or 'Not generated'),
    ]
    meta_rows = [[
        _paragraph(label, styles['label']),
        _paragraph(value, styles['base']),
    ] for label, value in meta]
    meta_table = Table(meta_rows, colWidths=[45 * mm, CONTENT_W - 45 * mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, LINE),
    ]))
    story.append(meta_table)

    signature = document.latest_signature
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('Client e-signature', styles['h2']))
    if signature:
        rows = [
            ('Signed by', signature.signer_name),
            ('Email', signature.signer_email),
            ('Role', signature.signer_role or 'Client'),
            ('Signed at', timezone.localtime(signature.signed_at).strftime('%d %b %Y %H:%M:%S %Z')),
            ('Document version', str(signature.document_version)),
            ('Signed PDF SHA-256', signature.pdf_sha256 or 'Recorded at signing'),
            ('IP address', signature.ip_address or 'Not recorded'),
            ('Consent', signature.consent_text),
        ]
        sig_rows = [[
            _paragraph(label, styles['label']),
            _paragraph(value, styles['base']),
        ] for label, value in rows]
        sig_table = Table(sig_rows, colWidths=[45 * mm, CONTENT_W - 45 * mm])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, LINE),
        ]))
        story.append(sig_table)
    else:
        story.append(_paragraph(
            'No client e-signature is recorded for this document. The company '
            'signature and stamp above are authorized company assets; they are not '
            'a client signature.',
            styles['base'],
        ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph('Audit trail', styles['h2']))
    event_rows = [[
        _paragraph('When', styles['table_head']),
        _paragraph('Event', styles['table_head']),
        _paragraph('Actor', styles['table_head']),
        _paragraph('IP', styles['table_head']),
    ]]
    for event in document.events.all()[:60]:
        event_rows.append([
            _paragraph(timezone.localtime(event.created_at).strftime('%d %b %Y %H:%M'), styles['tiny']),
            _paragraph(event.get_event_display(), styles['tiny']),
            _paragraph(event.actor_email or (event.actor.get_username() if event.actor else 'System'), styles['tiny']),
            _paragraph(event.ip_address or '-', styles['tiny']),
        ])
    event_table = Table(
        event_rows,
        colWidths=[34 * mm, 45 * mm, CONTENT_W - 34 * mm - 45 * mm - 28 * mm, 28 * mm],
        repeatRows=1,
    )
    event_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), accent),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, LINE),
        ('BOX', (0, 0), (-1, -1), 0.4, LINE),
    ]))
    story.append(event_table)

    story.append(Spacer(1, 6 * mm))
    story.append(_paragraph(
        'Company signature and stamp are applied by authorized OnWebApp administrators. '
        'A document is only shown as signed when a client signature record exists above.',
        styles['tiny'],
    ))
    return story


def render_document_pdf(document):
    """Render ``document`` to PDF bytes. Never raises for missing images."""
    from .models import Document

    cfg = DocumentSettings.load()
    accent = _hex(cfg.accent_color)
    styles = _styles(accent)
    draft = document.status == Document.STATUS_DRAFT

    legal_note = (
        'Issued electronically by OnWebApp. Company signature and stamp are authorized '
        'company assets applied by an administrator.'
    )

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title=f'{document.doc_type.name} {document.reference}',
        author=cfg.company_name or 'OnWebApp',
        subject=document.title_display,
        creator='OnWebApp Documents',
    )

    def on_first(cv, _doc):
        _draw_header(cv, _doc, document, cfg, accent, styles, True)

    def on_later(cv, _doc):
        _draw_header(cv, _doc, document, cfg, accent, styles, False)

    def footer(cv, total):
        _draw_footer(cv, total, document, cfg, styles, draft, legal_note)

    story = []
    story.append(Spacer(1, 6 * mm))

    # Title + client block ---------------------------------------------------
    client_lines = [
        _paragraph('BILL TO' if document.doc_type.code in {'invoice', 'receipt'} else 'PREPARED FOR', styles['label']),
        _paragraph(document.client_display_name, styles['client']),
    ]
    if document.client_company and document.client_company != document.client_name:
        client_lines.append(_paragraph(document.client_name, styles['small']))
    if document.client_address:
        client_lines.append(_paragraph(document.client_address, styles['small']))
    if document.client_email:
        client_lines.append(_paragraph(document.client_email, styles['small']))
    if document.client_tax_id:
        client_lines.append(_paragraph(f'Tax ID: {document.client_tax_id}', styles['small']))

    meta_lines = [
        _paragraph(str(document.doc_type.name).upper(), styles['h1']),
        Spacer(1, 1 * mm),
        _paragraph(f'Reference {document.reference}', ParagraphStyle(
            'ref', parent=styles['base'], alignment=TA_RIGHT, fontName='Helvetica-Bold', textColor=accent,
        )),
    ]
    dates = [('Issue date', document.issue_date)]
    if document.due_date:
        dates.append(('Due date', document.due_date))
    if document.valid_until:
        dates.append(('Valid until', document.valid_until))
    for label, value in dates:
        meta_lines.append(_paragraph(
            f'{label}: {value:%d %b %Y}',
            ParagraphStyle('meta', parent=styles['small'], alignment=TA_RIGHT),
        ))

    header_table = Table(
        [[client_lines, meta_lines]],
        colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    if document.title:
        story.append(_paragraph(document.title, styles['h2']))
        story.append(Spacer(1, 2 * mm))

    # Line items -------------------------------------------------------------
    story.append(_line_items_table(document, styles, accent))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals_table(document, styles, accent))

    # Notes / terms ----------------------------------------------------------
    if document.notes:
        story.append(Spacer(1, 6 * mm))
        story.append(KeepTogether([
            _paragraph('Notes', styles['h2']),
            _paragraph(document.notes, styles['base']),
        ]))

    terms = document.terms or cfg.default_payment_terms
    if terms or cfg.bank_details or document.doc_type.code in {'invoice', 'receipt'}:
        story.append(Spacer(1, 6 * mm))
        block = [_paragraph('Payment terms & conditions', styles['h2'])]
        if terms:
            block.append(_paragraph(terms, styles['base']))
        if cfg.bank_details:
            block.append(Spacer(1, 2 * mm))
            block.append(_paragraph('Payment details', styles['label']))
            block.append(_paragraph(cfg.bank_details, styles['base']))
        story.append(KeepTogether(block))

    # Signature + stamp ------------------------------------------------------
    story.append(Spacer(1, 10 * mm))
    story.append(KeepTogether(_signature_tables(document, cfg, styles, accent)))

    if document.doc_type.requires_signature and not document.latest_signature:
        story.append(Spacer(1, 3 * mm))
        story.append(_paragraph(
            'This contract is not executed until the client signs it electronically. '
            'The company signature and stamp show authorized company intent only.',
            styles['small'],
        ))

    if cfg.footer_note:
        story.append(Spacer(1, 6 * mm))
        story.append(_paragraph(cfg.footer_note, styles['small']))

    # Audit certificate ------------------------------------------------------
    story.extend(_certificate_page(document, cfg, styles, accent))

    pdf.build(
        story,
        onFirstPage=on_first,
        onLaterPages=on_later,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(*args, footer_cb=footer, **kwargs),
    )
    return buffer.getvalue()
