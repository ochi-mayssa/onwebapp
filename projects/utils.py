from django.template.loader import get_template
from django.core.files.base import ContentFile
from django.conf import settings
import os

try:
    import weasyprint
except (ImportError, OSError) as e:
    weasyprint = None
    print(f"Warning: WeasyPrint not fully available: {e}")

def render_to_pdf(template_src, context_dict):
    """
    Render a Django template to PDF using WeasyPrint.
    Returns the PDF content as bytes.
    """
    if not weasyprint:
        print("WeasyPrint not installed or configured. Skipping PDF generation.")
        return None

    template = get_template(template_src)
    html  = template.render(context_dict)
    
    # Create a PDF
    try:
        base_url = settings.BASE_DIR
        pdf_file = weasyprint.HTML(string=html, base_url=str(base_url)).write_pdf()
        return pdf_file
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        return None
