from __future__ import annotations

import csv
from io import BytesIO, StringIO

from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_csv_export(rows: list[dict[str, str]], filename: str) -> HttpResponse:
    output = StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def build_excel_export(rows: list[dict[str, str]], filename: str) -> HttpResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "SEO Monitoring"

    if rows:
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header, "") for header in headers])

    stream = BytesIO()
    workbook.save(stream)
    response = HttpResponse(
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def build_pdf_export(
    *,
    rows: list[dict[str, str]],
    filename: str,
    title: str,
    subtitle: str,
) -> HttpResponse:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    pdf.setFillColor(colors.HexColor("#0F172A"))
    pdf.rect(0, height - 30 * mm, width, 30 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(15 * mm, height - 18 * mm, title)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(15 * mm, height - 24 * mm, subtitle)

    y = height - 38 * mm
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(15 * mm, y, "Monitoring History Export")
    y -= 8 * mm

    if not rows:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(15 * mm, y, "No monitoring snapshots match the selected filters.")
    else:
        columns = [
            "Date",
            "Analysis Type",
            "Domain",
            "Health Score",
            "Visibility Score",
            "Broken Links",
            "Redirects",
            "Issues Count",
        ]
        x_positions = [15 * mm, 40 * mm, 75 * mm, 120 * mm, 145 * mm, 170 * mm, 188 * mm, 205 * mm]
        pdf.setFont("Helvetica-Bold", 8)
        for column, x in zip(columns, x_positions):
            pdf.drawString(x, y, column)
        y -= 5 * mm
        pdf.setLineWidth(0.3)
        pdf.line(15 * mm, y, 195 * mm, y)
        y -= 4 * mm

        pdf.setFont("Helvetica", 7)
        for row in rows[:35]:
            values = [
                row.get("Date", ""),
                row.get("Analysis Type", ""),
                row.get("Domain", ""),
                row.get("Health Score", ""),
                row.get("Visibility Score", ""),
                row.get("Broken Links", ""),
                row.get("Redirects", ""),
                row.get("Issues Count", ""),
            ]
            for value, x in zip(values, x_positions):
                pdf.drawString(x, y, str(value)[:24])
            y -= 5 * mm
            if y < 20 * mm:
                pdf.showPage()
                y = height - 20 * mm
                pdf.setFont("Helvetica", 7)

    pdf.showPage()
    pdf.save()
    response = HttpResponse(stream.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
