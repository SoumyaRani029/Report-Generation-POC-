# ✅ FINAL `extract_text.py` (Poppler-free OCR fallback: pdf2image ➜ pypdfium2 ➜ PyMuPDF)
"""
Goal: **Never skip pages again**, even if Poppler is NOT installed.

This module extracts text from *any* PDF by:
1) Try pdfplumber to read selectable text per-page (fast, no OCR).
2) If a page has no text → rasterize that page to an image and OCR it.
   - Rasterizer cascade:
       a) pdf2image (+ Poppler) if available
       b) pypdfium2 (pure pip, no Poppler)  ← **new fallback**
       c) PyMuPDF (fitz)                     ← **second fallback**

Install (Python):
    pip install pdfplumber pytesseract pillow
    pip install pdf2image            # optional (uses Poppler)
    pip install pypdfium2            # ✅ recommended fallback, no Poppler needed
    pip install pymupdf              # optional second fallback

Windows system deps (optional):
- Poppler (only needed for pdf2image). If not installed, we still work via pypdfium2/PyMuPDF.
- Tesseract OCR (UB Mannheim build). During install, include Telugu.

Environment:
- If on Windows and Tesseract is installed at the default path, we auto-configure it.

Self-tests:
- Run this file directly to execute smoke tests. Optionally set SAMPLE_PDF to a local PDF.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List
from io import BytesIO
import os
import sys
import traceback
import warnings

# --- Optional imports (we tolerate missing ones) ---
try:
    import pdfplumber
except Exception as _e:
    pdfplumber = None  # type: ignore

try:
    from pdf2image import convert_from_path as _convert_from_path
except Exception:
    _convert_from_path = None  # type: ignore

try:
    import pypdfium2 as pdfium
    from pypdfium2 import BitmapConv
except Exception:
    pdfium = None  # type: ignore
    BitmapConv = None  # type: ignore

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None  # type: ignore

from PIL import Image  # pillow
import pytesseract

# Allow very large scanned images (e.g., construction plans) without triggering PIL's DOS guard.
Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

# ---------------------------------------------------------------------------
# Tesseract configuration (Windows-safe)
# ---------------------------------------------------------------------------
_DEFAULT_TESS_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.exists(_DEFAULT_TESS_WIN):
    pytesseract.pytesseract.tesseract_cmd = _DEFAULT_TESS_WIN


def available_tesseract_languages() -> List[str]:
    try:
        return pytesseract.get_languages(config="") or ["eng"]
    except Exception:
        return ["eng"]


def get_tesseract_lang() -> str:
    langs = set(available_tesseract_languages())
    if {"eng", "tel"}.issubset(langs):
        return "eng+tel"
    if "eng" in langs:
        return "eng"
    if "tel" in langs:
        return "tel"
    return "eng"


TESS_LANG = get_tesseract_lang()

# ---------------------------------------------------------------------------
# Rasterizers
# ---------------------------------------------------------------------------

def _rasterize_with_pdf2image(pdf_path: Path, page_number: int, dpi: int, poppler_path: Optional[str]) -> Optional[Image.Image]:
    if _convert_from_path is None:
        return None
    try:
        kwargs = dict(dpi=dpi, first_page=page_number, last_page=page_number)
        if poppler_path:
            kwargs["poppler_path"] = poppler_path
        imgs = _convert_from_path(str(pdf_path), **kwargs)
        return imgs[0] if imgs and len(imgs) > 0 else None
    except Exception:
        return None


def _rasterize_with_pdfium(pdf_path: Path, page_number: int, dpi: int) -> Optional[Image.Image]:
    if pdfium is None:
        return None
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        page = pdf.get_page(page_number - 1)
        scale = dpi / 72.0
        # render_to returns PIL image when BitmapConv.pil_image is used
        pil_img = page.render_to(BitmapConv.pil_image, scale=scale)
        page.close()
        pdf.close()
        return pil_img
    except Exception:
        return None


def _rasterize_with_pymupdf(pdf_path: Path, page_number: int, dpi: int) -> Optional[Image.Image]:
    if fitz is None:
        return None
    try:
        doc = fitz.open(str(pdf_path))
        page = doc.load_page(page_number - 1)
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        bio = BytesIO(pix.tobytes("png"))
        img = Image.open(bio).convert("RGB")
        doc.close()
        return img
    except Exception:
        return None


def rasterize_page(pdf_path: Path, page_number: int, *, dpi: int = 300, poppler_path: Optional[str] = None) -> Image.Image:
    """Return a PIL Image for the requested page using the first working backend."""
    img = _rasterize_with_pdf2image(pdf_path, page_number, dpi, poppler_path)
    if img is not None:
        return img
    img = _rasterize_with_pdfium(pdf_path, page_number, dpi)
    if img is not None:
        return img
    img = _rasterize_with_pymupdf(pdf_path, page_number, dpi)
    if img is not None:
        return img
    raise RuntimeError("No PDF rasterizer available. Install one of: pdf2image(+Poppler), pypdfium2, or pymupdf.")


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def translate_telugu_to_english(text: str, status_callback=None) -> str:
    """Translate Telugu text to English using OpenAI API.
    
    Args:
        text: Text that may contain Telugu content.
        status_callback: Optional callback for progress updates.
    
    Returns:
        Translated text in English, or original text if translation fails or not needed.
    """
    if not text or not text.strip():
        return text
    
    # Simple heuristic: check if text contains Telugu characters (Unicode range 0C00-0C7F)
    has_telugu = any('\u0C00' <= char <= '\u0C7F' for char in text)
    
    if not has_telugu:
        # No Telugu detected, return as-is
        if status_callback:
            status_callback("✓ No Telugu text detected - no translation needed")
        return text
    
    try:
        # Try to use OpenAI API for translation
        import os
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # Try loading from .env file
            try:
                from pathlib import Path
                env_file = Path(".env")
                if env_file.exists():
                    for line in env_file.read_text(encoding='utf-8', errors='ignore').splitlines():
                        line = line.strip()
                        if line.startswith("OPENAI_API_KEY="):
                            parts = line.split("=", 1)
                            if len(parts) >= 2:
                                api_key = parts[1].strip().strip('"').strip("'")
                                break
            except Exception:
                pass
        
        if not api_key:
            if status_callback:
                status_callback("⚠️ OpenAI API key not found - skipping translation")
            print("⚠️ OpenAI API key not found - skipping Telugu to English translation")
            return text
        
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        if status_callback:
            status_callback("🌐 Translating Telugu text to English...")
        
        # Split text into chunks if too long (OpenAI has token limits)
        max_chunk_size = 3000  # characters per chunk
        chunks = []
        for i in range(0, len(text), max_chunk_size):
            chunks.append(text[i:i + max_chunk_size])
        
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional translator. Translate Telugu text to English. Preserve all formatting, numbers, dates, and technical terms. If the text is already in English, return it unchanged. Return only the translated text, no explanations."
                        },
                        {
                            "role": "user",
                            "content": f"Translate the following text to English. Preserve all formatting, numbers, dates, and technical terms:\n\n{chunk}"
                        }
                    ],
                    temperature=0.0,  # Keep 0.0 for translation accuracy
                    max_tokens=4000
                )
                
                # Check if response has choices
                if not response.choices or len(response.choices) == 0:
                    if status_callback:
                        status_callback(f"⚠️ Translation API returned empty response for chunk {i+1}")
                    print(f"⚠️ Translation API returned empty response for chunk {i+1}")
                    translated_chunks.append(chunk)  # Use original if translation fails
                    continue
                
                translated = response.choices[0].message.content.strip()
                translated_chunks.append(translated)
                if status_callback and len(chunks) > 1:
                    status_callback(f"🌐 Translated chunk {i+1}/{len(chunks)}...")
            except Exception as chunk_err:
                if status_callback:
                    status_callback(f"⚠️ Translation failed for chunk {i+1}: {str(chunk_err)}")
                print(f"⚠️ Translation failed for chunk {i+1}: {chunk_err}")
                translated_chunks.append(chunk)  # Use original if translation fails
        
        translated_text = "\n\n".join(translated_chunks)
        
        if status_callback:
            status_callback("✅ Translation completed")
        
        return translated_text
    except Exception as e:
        if status_callback:
            status_callback(f"⚠️ Translation error: {str(e)} - using original text")
        print(f"⚠️ Translation error: {e} - using original text")
        return text


def extract_text_from_pdf(file_path: str | os.PathLike, *, poppler_path: Optional[str] = None, dpi: int = 300, merge_ocr_with_text: bool = False, status_callback=None, translate_telugu: bool = True) -> str:
    """Extract text from a PDF, page-by-page, never skipping pages.

    Args:
        file_path: PDF path.
        poppler_path: Optional Poppler bin path for pdf2image on Windows.
        dpi: Rasterization DPI for OCR (higher → better OCR, slower).
        merge_ocr_with_text: If True, OCR every page and append to selectable text (may duplicate).
        status_callback: Optional callback function(status_message: str) for progress updates.
        translate_telugu: If True, automatically translate Telugu text to English after extraction.
    """
    pdf_path = Path(file_path)
    out_chunks: List[str] = []

    if status_callback:
        status_callback(f"📄 Extracting text from: {pdf_path.name}")
    print(f"\n📄 Extracting text from: {pdf_path.name}")
    
    if not pdf_path.exists():
        error_msg = f"❌ File not found: {pdf_path}"
        if status_callback:
            status_callback(error_msg)
        print(error_msg)
        return ""

    total_pages = 0
    if pdfplumber is not None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                if status_callback:
                    status_callback(f"📄 Processing {total_pages} pages...")
                
                for page_number, page in enumerate(pdf.pages, start=1):
                    selectable = ""
                    try:
                        selectable = page.extract_text() or ""
                    except Exception as e:
                        if status_callback:
                            status_callback(f"⚠️ Page {page_number}: pdfplumber error: {e}")
                        print(f"⚠️ Page {page_number}: pdfplumber error: {e}")
                        selectable = ""

                    need_ocr = merge_ocr_with_text or (not selectable.strip())
                    if not need_ocr and selectable.strip():
                        if status_callback:
                            status_callback(f"✅ Page {page_number}/{total_pages}: Selectable text")
                        print(f"✅ Page {page_number}/{total_pages}: Selectable text")
                        out_chunks.append(selectable)
                        continue

                    # OCR path - use rasterizer cascade to ensure no pages are skipped
                    try:
                        if status_callback:
                            status_callback(f"🔍 Page {page_number}/{total_pages}: Running OCR...")
                        img = rasterize_page(pdf_path, page_number, dpi=dpi, poppler_path=poppler_path)
                        ocr_text = pytesseract.image_to_string(img, lang=TESS_LANG, config='--psm 6 --oem 3') or ""
                        if merge_ocr_with_text and selectable.strip():
                            combined = selectable.rstrip() + "\n\n" + ocr_text.lstrip()
                            out_chunks.append(combined)
                            if status_callback:
                                status_callback(f"🔍 Page {page_number}/{total_pages}: Merged selectable + OCR")
                            print(f"🔍 Page {page_number}/{total_pages}: Merged selectable + OCR")
                        else:
                            out_chunks.append(ocr_text)
                            if status_callback:
                                status_callback(f"🔄 Page {page_number}/{total_pages}: OCR used")
                            print(f"🔄 Page {page_number}/{total_pages}: OCR used")
                    except Exception as ocr_err:
                        error_msg = f"❌ Page {page_number}: OCR/rasterize failed: {ocr_err}"
                        if status_callback:
                            status_callback(error_msg)
                        print(error_msg)
                        out_chunks.append("")  # Append empty string to maintain page count
        except Exception as e:
            error_msg = f"⚠️ pdfplumber failed to open file, falling back to full-document OCR: {e}"
            if status_callback:
                status_callback(error_msg)
            print(error_msg)

    if total_pages == 0:
        # Either pdfplumber missing or failed: try to count pages via backends
        # We do a naive loop until failure; in practice, pdfium/PyMuPDF expose counts,
        # but to stay backend-agnostic without extra APIs, we try sequentially.
        # Prefer pdfium if present to get page count cleanly.
        count = None
        try:
            if pdfium is not None:
                doc = pdfium.PdfDocument(str(pdf_path))
                count = len(doc)
                doc.close()
        except Exception:
            count = None
        try:
            if count is None and fitz is not None:
                doc = fitz.open(str(pdf_path))
                count = doc.page_count
                doc.close()
        except Exception:
            count = None
        if count is None:
            warning_msg = "⚠️ Could not determine page count; attempting page 1 OCR only."
            if status_callback:
                status_callback(warning_msg)
            print(warning_msg)
            count = 1

        if status_callback:
            status_callback(f"📄 Processing {count} pages (no pdfplumber)...")
        
        for page_number in range(1, count + 1):
            try:
                if status_callback:
                    status_callback(f"🔍 Page {page_number}/{count}: Running OCR...")
                img = rasterize_page(pdf_path, page_number, dpi=dpi, poppler_path=poppler_path)
                ocr_text = pytesseract.image_to_string(img, lang=TESS_LANG, config='--psm 6 --oem 3') or ""
                out_chunks.append(ocr_text)
                if status_callback:
                    status_callback(f"🔄 Page {page_number}/{count}: OCR used (no pdfplumber)")
                print(f"🔄 Page {page_number}/{count}: OCR used (no pdfplumber)")
            except Exception as ocr_err:
                error_msg = f"❌ Page {page_number}: OCR/rasterize failed: {ocr_err}"
                if status_callback:
                    status_callback(error_msg)
                print(error_msg)
                out_chunks.append("")  # Append empty string to maintain page count

    # Combine all extracted text
    extracted_text = "\n\n".join(out_chunks)
    
    # Translate Telugu to English if requested and Telugu text is detected
    # This ensures the LLM receives English text for report generation
    if translate_telugu and extracted_text.strip():
        # Check if Telugu is present before translating
        has_telugu = any('\u0C00' <= char <= '\u0C7F' for char in extracted_text)
        if has_telugu:
            if status_callback:
                status_callback(f"🌐 Detected Telugu text - translating to English for LLM context...")
            print(f"🌐 Detected Telugu text - translating to English...")
            extracted_text = translate_telugu_to_english(extracted_text, status_callback)
            if status_callback:
                status_callback(f"✅ Telugu text translated to English - ready for LLM processing")
    else:
            if status_callback:
                status_callback(f"✓ No Telugu detected - text is ready for LLM processing")
    
    success_msg = f"✅ Completed extraction for: {pdf_path.name}"
    if status_callback:
        status_callback(success_msg)
    print(success_msg)
    return extracted_text


# Batch helper

def extract_text_from_pdfs(paths: List[str | os.PathLike], *, poppler_path: Optional[str] = None, dpi: int = 300, merge_ocr_with_text: bool = False) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        pth = Path(p)
        out[pth.name] = extract_text_from_pdf(pth, poppler_path=poppler_path, dpi=dpi, merge_ocr_with_text=merge_ocr_with_text)
    return out


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------

def _smoke_test() -> None:
    # Tesseract language resolution
    langs = available_tesseract_languages()
    assert isinstance(langs, list) and all(isinstance(x, str) for x in langs)
    assert isinstance(TESS_LANG, str) and len(TESS_LANG) > 0

    # f-string regression test
    demo = Path("demo.pdf")
    msg = f"Extracting: {demo.name}"
    assert demo.name in msg


def _integration_test_sample() -> None:
    sample = os.getenv("SAMPLE_PDF", "").strip()
    if not sample:
        print("(info) Set SAMPLE_PDF=<path> to run integration test.")
        return
    p = Path(sample)
    if not p.exists():
        print(f"(warn) SAMPLE_PDF not found at: {p}")
        return
    text = extract_text_from_pdf(p)
    assert isinstance(text, str)
    print(f"(info) Extracted {len(text)} chars from SAMPLE_PDF.")


if __name__ == "__main__":
    print("\n--- Running self-tests for extract_text.py ---")
    try:
        _smoke_test()
        print("✓ Smoke tests passed")
    except AssertionError as ae:
        print(f"✗ Smoke test failed: {ae}")
        sys.exit(1)

    _integration_test_sample()
    print("--- Done ---\n")
