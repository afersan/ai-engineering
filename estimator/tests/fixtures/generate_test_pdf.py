"""Generate a simple test PDF with known content."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def create_test_pdf():
    output_path = Path(__file__).parent / "sample.pdf"
    c = canvas.Canvas(str(output_path), pagesize=letter)
    c.drawString(100, 750, "Test PDF Document")
    c.drawString(100, 730, "This project requires React and PostgreSQL.")
    c.drawString(100, 710, "Expected timeline: 3 months.")
    c.save()
    print(f"Created: {output_path}")

if __name__ == "__main__":
    create_test_pdf()
