"""Plain text from an uploaded CV: PDF, Word (.docx) or text."""
import re
import zipfile
from pathlib import Path


def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        text = "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    elif suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
    elif suffix in (".txt", ".md"):
        text = path.read_text(errors="replace")
    else:
        raise ValueError("Upload your CV as PDF, Word (.docx) or plain text.")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 200:
        raise ValueError("Could not read enough text from that file. If it is a scanned PDF, upload a Word or text version.")
    return text
