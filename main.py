import os, json
import re
import shutil
import tempfile
import sqlite3
from pathlib import Path
from openai import OpenAI
from report_builder import build_report_pdf
from prompts import get_property_extraction_prompt
from data_parser import build_structured_data as build_fallback_structured_data
from comparables import merge_comparables
import sqlite3

# Import performance tracking
try:
    from performance_tracker import log_capture, track_time
    PERFORMANCE_TRACKING_ENABLED = True
except ImportError:
    PERFORMANCE_TRACKING_ENABLED = False
    # Create dummy functions if not available
    class DummyLogCapture:
        def log(self, msg, level="INFO"): pass
        def enable(self): pass
        def disable(self): pass
    log_capture = DummyLogCapture()
    def track_time(name=None):
        def decorator(func):
            return func
        return decorator

# Patch print to also log to dashboard
_original_print = print
def print(*args, **kwargs):
    """Enhanced print that also logs to dashboard."""
    _original_print(*args, **kwargs)
    if PERFORMANCE_TRACKING_ENABLED:
        # Determine log level from message
        message = ' '.join(str(arg) for arg in args)
        level = "INFO"
        silent = False  # By default, print to terminal
        
        if "[ERROR]" in message or "❌" in message:
            level = "ERROR"
        elif "[WARN]" in message or "⚠️" in message:
            level = "WARNING"
        elif "✅" in message or "[SUCCESS]" in message:
            level = "SUCCESS"
        elif "⏱️" in message or "[TIMING]" in message or "Starting:" in message or "Completed:" in message:
            level = "TIMING"
            silent = True  # Don't print timing messages to terminal, only dashboard
        
        log_capture.log(message, level, silent=silent)

def _load_env_file_if_present():
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                # Safe split - check length before unpacking
                parts = line.split("=", 1)
                if len(parts) < 2:
                    continue
                k, v = parts[0], parts[1]
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

_load_env_file_if_present()

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Set it in the environment or provide a .env file with OPENAI_API_KEY=..."
    )

# Validate API key format
_api_key_clean = _api_key.strip()
if not _api_key_clean.startswith("sk-"):
    print("⚠️ WARNING: API key should start with 'sk-'. Your key format may be incorrect.")
elif _api_key_clean.startswith("sk-proj-"):
    print("⚠️ WARNING: API key starts with 'sk-proj-' which may be a project key, not an API key.")
    print("⚠️ Please ensure you're using a valid API key from https://platform.openai.com/account/api-keys")
elif len(_api_key_clean) < 20:
    print("⚠️ WARNING: API key appears too short. Valid OpenAI API keys are typically 51+ characters.")

client = OpenAI(api_key=_api_key_clean)

# SQLite database path (in code folder)
SQLITE_DB_PATH = Path(__file__).parent / "property_valuations.db"


@track_time("save_to_sqlite_database")
def save_to_sqlite_database(structured_data: dict, status_callback=None):
    """
    Save structured data to SQLite database (property_valuations.db) using comprehensive structure.
    
    IMPORTANT: This function is ONLY called when users upload property documents.
    The database is ONLY populated through this function - never automatically from JSON files.
    
    Flow:
    1. User uploads property documents
    2. Text is extracted from documents
    3. LLM processes text/images and returns structured JSON
    4. This function is called with the LLM JSON data
    5. Creates/initializes all 10 database tables if they don't exist (empty tables only)
    6. Saves LLM JSON data to all appropriate tables:
       - property (main table)
       - property_area_details
       - property_setback_details
       - property_projection_details
       - property_construction_details
       - comparables (if present in JSON)
       - market_value_details
       - pricing_additional_charges
       - documents_list
       - audit_trail
    7. Returns the property_id for reference
    
    The database is NEVER automatically populated from existing JSON files.
    """
    try:
        # Import comprehensive database functions
        from create_comprehensive_database import init_database, insert_property_data, DB_PATH
        
        if status_callback:
            status_callback(f"📊 Initializing database: {DB_PATH.name}")
            status_callback(f"   📁 Database Path: {DB_PATH.absolute()}")
            status_callback(f"   → Creating/verifying all 10 tables...")
        
        # Initialize database if not exists (creates all 10 tables)
        init_database(drop_existing=False)
        
        if status_callback:
            status_callback(f"✅ Database tables ready")
            status_callback(f"   📁 Database File: {DB_PATH.name}")
            status_callback(f"   → Saving property data to all tables...")
        
        # Insert property data into all tables
        property_id = insert_property_data(structured_data)
        
        if status_callback:
            status_callback(f"💾 Saved to SQLite DB (Property ID: {property_id})")
            status_callback(f"   📁 Database File: {DB_PATH.name}")
            status_callback(f"   📂 Full Path: {DB_PATH.absolute()}")
            status_callback(f"   ✅ Data saved to all 10 tables")
        print(f"[SQLite DB] Saved property to {SQLITE_DB_PATH} (Property ID: {property_id})")
        print(f"[SQLite DB] Database file: {DB_PATH.name}")
        print(f"[SQLite DB] Database location: {DB_PATH.absolute()}")
        
        return property_id
        
    except Exception as e:
        print(f"[SQLite DB] Error saving: {e}")
        import traceback
        traceback.print_exc()
        if status_callback:
            status_callback(f"❌ Database save error: {str(e)}")
        raise


@track_time("select_best_images_with_llm")
def select_best_images_with_llm(image_paths: list, status_callback=None) -> tuple:
    """Use LLM to analyze all images and select the best 5 matching required categories."""
    from openai import APIError, AuthenticationError
    import base64
    
    if status_callback:
        status_callback("🔍 Analyzing images to select the best 5 for the report...")
    
    if len(image_paths) <= 5:
        # If 5 or fewer images, use them all in order, try to find location map
        location_map = None
        # Simple heuristic: look for map-related keywords in filenames
        # Prioritize Google Maps, satellite, and location-related keywords
        location_map_keywords = ['map', 'location', 'google', 'satellite', 'street', 'gps', 'maps', 'road', 'address', 'area', 'loc', 'coordinate', 'lat', 'long']
        for img in image_paths:
            img_name_lower = Path(img).name.lower()
            if any(keyword in img_name_lower for keyword in location_map_keywords):
                location_map = Path(img)
                break
        return [Path(img) for img in image_paths[:5]], location_map
    
    # Prepare images as base64 for Vision API
    image_contents = []
    image_map = {}  # Map image index to path
    
    try:
        for idx, img_path in enumerate(image_paths):
            img_path_obj = Path(img_path)
            # Read and encode image
            with open(img_path_obj, "rb") as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
                
            # Determine MIME type from extension
            ext = img_path_obj.suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}"
                }
            })
            image_map[idx] = str(img_path)
    except Exception as e:
        error_msg = f"Error encoding images: {str(e)}"
        raise ValueError(error_msg)
    
    # Import prompt from prompts file
    from prompts import get_image_selection_prompt
    
    # Get the prompt for image selection
    prompt = get_image_selection_prompt(len(image_paths))
    
    try:
        # Build content with text prompt followed by all images
        content = [{"type": "text", "text": prompt}] + image_contents

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "user", "content": content}
            ],
            max_tokens=1000,
            temperature=0.7,
            timeout=120  # 2 minute timeout for image selection
        )
        
        # Check if response has choices
        if not response.choices or len(response.choices) == 0:
            raise Exception("OpenAI API returned empty response - no choices available")
        
        text = response.choices[0].message.content
        start = text.find("{")
        end = text.rfind("}") + 1
        try:
            result = json.loads(text[start:end])
            
            # Map selected image indices back to image paths in correct order
            selected_paths = [None] * 5  # Pre-allocate for 5 images
            selected_items = result.get("selected_images", [])
            
            if status_callback:
                status_callback(f"📋 LLM selected {len(selected_items)} images for categories")
            
            # Sort by category to ensure order (1, 2, 3, 4, 5)
            selected_items.sort(key=lambda x: x.get("category", 0))
            
            used_indices = set()  # Track used indices to prevent duplicates
            for item in selected_items:
                category = item.get("category", 0)
                img_idx = item.get("image_index")
                
                if status_callback:
                    status_callback(f"  Category {category}: image_index {img_idx}")
                
                if 1 <= category <= 5 and img_idx is not None:
                    # Validate index range
                    if 0 <= img_idx < len(image_paths):
                        if img_idx in image_map and img_idx not in used_indices:
                            selected_paths[category - 1] = Path(image_map[img_idx])
                            used_indices.add(img_idx)
                            if status_callback:
                                status_callback(f"    ✓ Mapped to: {Path(image_map[img_idx]).name}")
                        elif img_idx in used_indices:
                            if status_callback:
                                status_callback(f"    ⚠️ Image index {img_idx} already used for another category")
                    else:
                        if status_callback:
                            status_callback(f"    ✗ Invalid image_index {img_idx} (must be 0-{len(image_paths)-1})")
                else:
                    if status_callback:
                        status_callback(f"    ✗ Invalid category {category} or missing image_index")
            
            # Fill any missing categories with fallback images (only if LLM didn't provide valid mapping)
            missing_categories = [i for i in range(5) if selected_paths[i] is None]
            if missing_categories:
                if status_callback:
                    status_callback(f"⚠️ {len(missing_categories)} categories missing, using fallback images")
                
                used_paths = set(str(p) for p in selected_paths if p is not None)
                used_indices_set = set()
                
                for i in missing_categories:
                    # Find an unused image
                    found = False
                    for idx in range(len(image_paths)):
                        if idx not in used_indices_set:
                            candidate_path = image_paths[idx]
                            candidate_str = str(candidate_path)
                            if candidate_str not in used_paths:
                                selected_paths[i] = Path(candidate_path)
                                used_paths.add(candidate_str)
                                used_indices_set.add(idx)
                                if status_callback:
                                    status_callback(f"  Fallback: Category {i+1} -> {Path(candidate_path).name}")
                                found = True
                                break
                    
                    if not found:
                        # Last resort: use any available image
                        for idx in range(len(image_paths)):
                            if idx not in used_indices_set:
                                selected_paths[i] = Path(image_paths[idx])
                                used_indices_set.add(idx)
                                break
            
            # Verify we have exactly 5 images in correct order
            if len([p for p in selected_paths if p is not None]) < 5:
                if status_callback:
                    status_callback(f"⚠️ Only {len([p for p in selected_paths if p is not None])} valid images selected, filling remaining...")
            
            # Ensure all 5 categories have images
            final_selected = []
            for i in range(5):
                if selected_paths[i] is not None:
                    final_selected.append(selected_paths[i])
                else:
                    # Emergency fallback: use remaining images
                    for img_path in image_paths:
                        img_path_obj = Path(img_path)
                        if img_path_obj not in final_selected:
                            final_selected.append(img_path_obj)
                            break
            
            # CRITICAL: Ensure we have at least some images, even if less than 5
            if len(final_selected) == 0:
                # Last resort: use all available images
                final_selected = [Path(img) for img in image_paths[:min(5, len(image_paths))]]
            
            selected_paths = final_selected[:5] if len(final_selected) > 0 else []
            
            # CRITICAL: If still empty, this is a fatal error - we need at least 1 image
            if len(selected_paths) == 0:
                raise ValueError(f"No images available for selection. Total images provided: {len(image_paths)}")
            
            if status_callback:
                status_callback(f"✓ Final selection: {len(selected_paths)} images for report")
                for i, img_path in enumerate(selected_paths, 1):
                    status_callback(f"  Photo {i}: {Path(img_path).name}")
            
            # Get location map if identified
            location_map_idx = result.get("location_map_index")
            location_map_path = None
            if location_map_idx is not None and 0 <= location_map_idx < len(image_paths):
                if location_map_idx in image_map:
                    location_map_path = Path(image_map[location_map_idx])
                    # Ensure location map is not in the selected 5 images
                    selected_paths_str = [str(p) for p in selected_paths]
                    if str(location_map_path) in selected_paths_str:
                        # Remove location map from selected images
                        selected_paths = [p for p in selected_paths if str(p) != str(location_map_path)]
                        
                        # CRITICAL: Ensure we don't end up with empty list
                        if len(selected_paths) == 0:
                            # If removing location map left us empty, add it back and skip location map
                            selected_paths = [location_map_path]
                            location_map_path = None
                            if status_callback:
                                status_callback("⚠️ Location map was the only image - using it as regular image")
                        else:
                            # Add another image if we removed one (ensure we always have at least 5)
                            while len(selected_paths) < 5 and len(selected_paths) < len(image_paths):
                                found_replacement = False
                                for img_path in image_paths:
                                    img_path_str = str(img_path)
                                    if img_path_str not in [str(p) for p in selected_paths] and img_path_str != str(location_map_path):
                                        selected_paths.append(Path(img_path))
                                        found_replacement = True
                                        break
                                if not found_replacement:
                                    # No more images available, break to avoid infinite loop
                                    break
                    if status_callback:
                        status_callback(f"🗺️ Location map identified: {location_map_path.name}")
            else:
                # Fallback: try to find location map by filename
                if status_callback:
                    status_callback("🔍 LLM didn't identify location map, checking filenames...")
                location_map_keywords = ['map', 'location', 'google', 'satellite', 'street', 'gps', 'maps', 'road', 'address', 'area', 'loc', 'coordinate', 'lat', 'long']
                for img_path in image_paths:
                    img_name_lower = Path(img_path).name.lower()
                    if any(keyword in img_name_lower for keyword in location_map_keywords):
                        location_map_path = Path(img_path)
                        # Ensure it's not in selected images
                        selected_paths_str = [str(p) for p in selected_paths]
                        if str(location_map_path) not in selected_paths_str:
                            if status_callback:
                                status_callback(f"🗺️ Location map found by filename: {location_map_path.name}")
                            break
            
            # CRITICAL: Final safety check - ensure we never return empty list
            if len(selected_paths) == 0:
                if status_callback:
                    status_callback("⚠️ Selected paths is empty, using fallback")
                selected_paths = [Path(img) for img in image_paths[:min(5, len(image_paths))]]
            
            if len(selected_paths) == 0:
                raise ValueError(f"Cannot select images: No valid images available. Total provided: {len(image_paths)}")
            
            return selected_paths[:5], location_map_path
        except Exception as e:
            print(f"⚠️ LLM image selection failed, using first 5 images: {e}")
            # Fallback: use first 5 images, try to find location map by filename
            location_map_path = None
            location_map_keywords = ['map', 'location', 'google', 'satellite', 'street', 'gps', 'maps', 'road', 'address', 'area', 'loc', 'coordinate', 'lat', 'long']
            for img_path in image_paths:
                img_name_lower = Path(img_path).name.lower()
                if any(keyword in img_name_lower for keyword in location_map_keywords):
                    location_map_path = Path(img_path)
                    break
            
            # CRITICAL: Ensure fallback also never returns empty
            fallback_images = [Path(img) for img in image_paths[:min(5, len(image_paths))]]
            if len(fallback_images) == 0:
                raise ValueError(f"Cannot generate report: No images available. Please upload at least one image.")
            
            return fallback_images, location_map_path
    except AuthenticationError as e:
        error_msg = f"API Authentication Error: Invalid or expired API key.\n\n"
        error_msg += f"Please check your OPENAI_API_KEY.\n\n"
        error_msg += f"Error details: {str(e)}"
        raise ValueError(error_msg)
    except APIError as e:
        error_msg = f"OpenAI API Error: {str(e)}"
        raise ValueError(error_msg)

@track_time("extract_info_with_gpt4o")
def extract_info_with_gpt4o(property_folder: Path, status_callback=None, output_dir: Path = None, pre_extracted_text: str = None, documents_without_text: list = None) -> tuple:
    """Send all property PDFs/images to GPT-4.1 for multilingual OCR + structured extraction."""
    from openai import APIError, AuthenticationError
    import base64
    from extract_text import extract_text_from_pdf
    
    print("📄 Processing documents and images for GPT-4.1...")
    docs = list((property_folder / "documents").glob("*"))
    imgs = list((property_folder / "images").glob("*"))
    
    # Use pre-extracted text if provided, otherwise extract from documents
    document_texts = []
    
    # Use provided list of documents without text, or create new list
    if documents_without_text is None:
        documents_without_text = []  # Track PDFs that failed text extraction
    
    # Track which PDFs were successfully sent as images vs skipped
    skipped_pdfs = []  # PDFs that couldn't be sent to LLM
    
    if pre_extracted_text and pre_extracted_text.strip():
        # Use pre-extracted text that was already extracted
        if status_callback:
            status_callback(f"📄 Using pre-extracted text ({len(pre_extracted_text):,} characters)...")
        # Split the pre-extracted text back into document sections
        sections = pre_extracted_text.split("=== Document:")
        for section in sections:
            if section.strip():
                # Extract document name and content - safe split
                lines = section.strip().split("\n", 1)
                if len(lines) >= 2:
                    doc_name = lines[0].replace("===", "").strip()
                    content = lines[1] if len(lines) > 1 else ""
                    if content.strip():
                        document_texts.append(f"=== Document: {doc_name} ===\n{content}")
                elif len(lines) == 1:
                    # Only document name, no content
                    doc_name = lines[0].replace("===", "").strip()
                    if doc_name:
                        document_texts.append(f"=== Document: {doc_name} ===\n")
        
        # If documents_without_text was provided, use it (don't re-extract)
        if documents_without_text and status_callback:
            status_callback(f"📄 {len(documents_without_text)} document(s) had no text - will send as images to LLM")
    else:
        # Extract text from PDFs (original behavior)
        if status_callback:
            status_callback(f"📄 Processing {len(docs)} document(s)...")
        
        for doc in docs:
            if doc.suffix.lower() == '.pdf':
                text = extract_text_from_pdf(doc, status_callback=status_callback)
                if text.strip():
                    document_texts.append(f"=== Document: {doc.name} ===\n{text}")
                    if status_callback:
                        status_callback(f"✓ Successfully extracted text from {doc.name}")
                else:
                    if status_callback:
                        status_callback(f"⚠️ No text extracted from {doc.name} - will send PDF directly to LLM")
                    # Store PDFs that failed text extraction to send directly to Vision API
                    documents_without_text.append(doc)
            elif doc.suffix.lower() == '.txt':
                try:
                    if status_callback:
                        status_callback(f"📄 Reading text file: {doc.name}...")
                    text = doc.read_text(encoding='utf-8', errors='ignore')
                    if text.strip():
                        document_texts.append(f"=== Document: {doc.name} ===\n{text}")
                        if status_callback:
                            status_callback(f"✓ Read {len(text):,} characters from {doc.name}")
                    else:
                        if status_callback:
                            status_callback(f"⚠️ Empty text file: {doc.name}")
                except Exception as e:
                    if status_callback:
                        status_callback(f"✗ Failed to read {doc.name}: {str(e)}")
                    print(f"✗ Failed to read {doc.name}: {e}")
                    pass
    
    # Store extracted text for saving later
    full_extracted_text = "\n\n".join(document_texts) if document_texts else ""
    
    # If no text was extracted and no pre-extracted text was provided, try to extract from all PDFs
    if not full_extracted_text and not pre_extracted_text:
        if status_callback:
            status_callback("⚠️ No text found in pre-extracted text, attempting to extract from PDFs...")
        # Fall back to extracting from documents
        for doc in docs:
            if doc.suffix.lower() == '.pdf':
                text = extract_text_from_pdf(doc, status_callback=status_callback)
                if text.strip():
                    document_texts.append(f"=== Document: {doc.name} ===\n{text}")
                    full_extracted_text = "\n\n".join(document_texts) if document_texts else ""
    
    if status_callback:
        status_callback(f"\n📊 Text Extraction Summary:")
        status_callback(f"  - Documents processed: {len(docs)}")
        status_callback(f"  - Documents with extracted text: {len(document_texts)}")
        status_callback(f"  - Total text length: {sum(len(dt) for dt in document_texts):,} characters")
    
    print(f"\n📊 Text Extraction Summary:")
    print(f"  - Documents processed: {len(docs)}")
    print(f"  - Documents with extracted text: {len(document_texts)}")
    print(f"  - Total text length: {sum(len(dt) for dt in document_texts):,} characters")
    
    # Prepare content with base64-encoded images and PDFs
    content = []
    
    # Add PDFs that failed text extraction as images (Vision API can read PDFs)
    for pdf_doc in documents_without_text:
        try:
            if status_callback:
                status_callback(f"📄 Sending {pdf_doc.name} directly to LLM Vision API...")
            # Use rasterizer cascade from extract_text.py to ensure no pages are skipped
            # This will try: pdf2image → pypdfium2 → PyMuPDF
            from extract_text import rasterize_page
            from PIL import Image
            import io
            
            # Convert first few pages (limit to avoid token limits)
            max_pages = 5  # Limit to first 5 pages per PDF
            
            # First, get total page count using available backends
            total_pages = max_pages  # Default
            try:
                import pdfplumber
                with pdfplumber.open(pdf_doc) as pdf:
                    total_pages = len(pdf.pages)
            except Exception:
                try:
                    import pypdfium2 as pdfium
                    doc = pdfium.PdfDocument(str(pdf_doc))
                    total_pages = len(doc)
                    doc.close()
                except Exception:
                    try:
                        import fitz  # PyMuPDF
                        doc = fitz.open(str(pdf_doc))
                        total_pages = doc.page_count
                        doc.close()
                    except Exception:
                        pass  # Use default max_pages
            
            pages_to_convert = min(max_pages, total_pages)
            if status_callback:
                status_callback(f"  🔄 Converting {pages_to_convert} page(s) using rasterizer cascade...")
            
            pages_converted = 0
            for page_num in range(1, pages_to_convert + 1):
                try:
                    # Use rasterizer cascade: pdf2image → pypdfium2 → PyMuPDF
                    # This ensures no pages are skipped even if Poppler is not available
                    page_img = rasterize_page(pdf_doc, page_num, dpi=200)
                    
                    # Convert PIL image to base64
                    img_buffer = io.BytesIO()
                    page_img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    image_data = base64.b64encode(img_buffer.read()).decode('utf-8')
                    
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    })
                    pages_converted += 1
                    if status_callback:
                        status_callback(f"  ✓ Converted page {page_num}/{pages_to_convert} from {pdf_doc.name}")
                except Exception as page_err:
                    if status_callback:
                        status_callback(f"  ⚠️ Failed to convert page {page_num}: {str(page_err)}")
                    print(f"[WARN] Failed to convert page {page_num} of {pdf_doc.name}: {page_err}")
                    # Continue with next page instead of failing entirely
            
            if pages_converted == 0:
                if status_callback:
                    status_callback(f"  ❌ CRITICAL: Could not convert any pages from {pdf_doc.name}")
                    status_callback(f"  💡 Install one of: pdf2image(+Poppler), pypdfium2, or pymupdf")
                print(f"[ERROR] Could not convert any pages from {pdf_doc.name} - will be SKIPPED")
                skipped_pdfs.append(pdf_doc.name)
            else:
                if status_callback:
                    status_callback(f"  ✅ Successfully converted {pages_converted}/{pages_to_convert} page(s)")
        except ImportError as import_err:
            if status_callback:
                status_callback(f"  ⚠️ Required modules not available: {str(import_err)}")
                status_callback(f"  ❌ CRITICAL: This PDF will NOT be analyzed by LLM!")
                status_callback(f"  💡 Install: pip install pypdfium2 (recommended, no Poppler needed)")
                status_callback(f"  💡 Or: pip install pdf2image + Poppler")
                status_callback(f"  💡 Or: pip install pymupdf")
            print(f"[WARN] Cannot send PDF {pdf_doc.name} directly - required modules not installed")
            print(f"[ERROR] PDF {pdf_doc.name} will be SKIPPED from LLM analysis!")
            print(f"[INFO] Install one of: pypdfium2 (recommended), pdf2image(+Poppler), or pymupdf")
            skipped_pdfs.append(pdf_doc.name)
        except Exception as e:
            if status_callback:
                status_callback(f"  ⚠️ Failed to process PDF: {str(e)}")
                status_callback(f"  ❌ This PDF may not be fully analyzed by LLM")
            print(f"[WARN] Failed to process PDF {pdf_doc.name}: {e}")
            skipped_pdfs.append(pdf_doc.name)
    
    # Check for blueprint/floor plan images and PDFs
    blueprint_images = []
    blueprint_pdfs = []
    blueprint_keywords = ['blueprint', 'floor plan', 'house plan', 'plan', 'architectural', 'drawing', 'site plan', 'layout', 'elevation', 'permission']
    
    # Check PDF documents for blueprint keywords in filename
    for doc in docs:
        doc_name_lower = Path(doc).name.lower()
        if any(keyword in doc_name_lower for keyword in blueprint_keywords):
            blueprint_pdfs.append(Path(doc).name)
            if status_callback:
                status_callback(f"📐 Blueprint/floor plan PDF detected: {Path(doc).name}")
    
    # Add images as base64 (Vision API format)
    # Track image filenames for reference (for surrounding land use determination)
    image_filenames = []
    for img in imgs:
        try:
            with open(img, "rb") as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            ext = img.suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            # Store image filename for reference
            img_filename = Path(img).name
            image_filenames.append(img_filename)
            
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}"
                }
            })
            
            # Check if this might be a blueprint by filename
            img_name_lower = img_filename.lower()
            if any(keyword in img_name_lower for keyword in blueprint_keywords):
                blueprint_images.append(img_filename)
                if status_callback:
                    status_callback(f"📐 Blueprint/floor plan detected: {img_filename}")
        except Exception as e:
            print(f"⚠️ Error encoding image {img}: {e}")
            continue
    
    # Log which images are being sent for surrounding land use analysis
    if image_filenames and status_callback:
        status_callback(f"📸 Uploaded Image Files ({len(image_filenames)} total):")
        for idx, img_name in enumerate(image_filenames, 1):
            # Identify likely images for surrounding land use
            img_lower = img_name.lower()
            img_note = ""
            if any(kw in img_lower for kw in ['surrounding', 'neighborhood', 'area', 'location', 'map', 'google', 'satellite', 'street', 'view']):
                img_note = " (likely for surrounding land use)"
            status_callback(f"   {idx}. {img_name}{img_note}")

    # Build prompt with document text - use the full_extracted_text if available
    docs_text = full_extracted_text if full_extracted_text else "\n\n".join(document_texts) if document_texts else ""
    
    # Log that we're sending extracted text to LLM
    if docs_text and docs_text.strip():
        if status_callback:
            status_callback(f"📤 Sending extracted text context to LLM for report generation...")
            status_callback(f"   - Text length: {len(docs_text):,} characters")
            status_callback(f"   - This context will be used to generate the structured report")
        print(f"📤 Sending {len(docs_text):,} characters of extracted text to LLM for report generation")
    else:
        if status_callback:
            status_callback("⚠️ No extracted text to send to LLM - will rely on images only")
        print("⚠️ No extracted text available for LLM")
    
    # Get the base prompt and add document text
    base_prompt = get_property_extraction_prompt()
    
    # Add note about PDFs sent directly if any
    pdf_note = ""
    if documents_without_text:
        # Check which PDFs were actually sent as images vs which were skipped
        # Count how many PDF images were added to content
        pdf_images_added = len([img for img in content if isinstance(img, dict) and img.get('type') == 'image_url' and 'pdf' in str(img.get('image_url', {}).get('url', '')).lower()])
        
        # Estimate sent PDFs (rough check - if we added images from PDFs, some were sent)
        # For now, we'll use the skipped_pdfs list we built
        sent_pdfs = [d.name for d in documents_without_text if d.name not in skipped_pdfs]
        
        if sent_pdfs:
            pdf_names_sent = ", ".join(sent_pdfs)
            pdf_note += f"\n\nIMPORTANT: The following PDF documents had no extractable text (likely scanned/image-based PDFs) and are being sent as images to the Vision API: {pdf_names_sent}\nPlease carefully analyze these images to extract ALL property information visible in them, including:\n- Property details, addresses\n- Buyer/Seller names (Vendee/Vendor)\n- Property reference numbers (tracker numbers)\n- Area measurements, construction details\n- Any other relevant information visible in the document images.\n\nCRITICAL: DO NOT extract GPS coordinates (latitude/longitude) from these images. GPS coordinates must ONLY be extracted from written text in property documents (PDF/TXT files), NOT from images. If GPS coordinates are not found in document text, return \"NA\" for both gps_latitude and gps_longitude."
        
        if skipped_pdfs:
            pdf_names_skipped = ", ".join(skipped_pdfs)
            pdf_note += f"\n\n⚠️ CRITICAL WARNING: The following PDF documents could NOT be analyzed because pdf2image/poppler is not installed: {pdf_names_skipped}\nThese documents contain important property information that will be MISSING from the extraction.\nTo fix this, install:\n1. pip install pdf2image\n2. Install Poppler from: https://github.com/oschwartz10612/poppler-windows/releases\n3. Add poppler/bin to your system PATH\n\nPlease note that information from these documents will NOT be included in the generated report."
    
    # Warn if no text was extracted at all
    if not docs_text.strip() and not documents_without_text:
        if status_callback:
            status_callback("⚠️ WARNING: No text extracted from any documents!")
    
    # Warn if some documents were skipped
    if skipped_pdfs:
        if status_callback:
            status_callback(f"❌ CRITICAL: {len(skipped_pdfs)} document(s) were SKIPPED and will NOT be analyzed!")
            status_callback(f"   Missing documents: {', '.join(skipped_pdfs)}")
            status_callback(f"   Install pdf2image and poppler to analyze scanned PDFs")
    
    # Add note about blueprints if detected
    blueprint_note = ""
    all_blueprints = blueprint_images + blueprint_pdfs
    if all_blueprints:
        blueprint_names = ", ".join(all_blueprints)
        blueprint_note = f"\n\n📐 BLUEPRINT/FLOOR PLAN DETECTED: The following files appear to be blueprints, floor plans, or architectural drawings: {blueprint_names}\nCRITICAL: Please carefully examine these blueprint/floor plan images to extract room information AND PROJECTIONS:\n\nROOM COUNTING:\n- Count the number of bedrooms (look for rooms labeled 'Bedroom', 'BR', 'B/R', 'BEDROOM' or rooms that appear to be bedrooms based on their location and size in the floor plan)\n- Count the number of bathrooms (look for rooms labeled 'Bathroom', 'Bath', 'W/C', 'Toilet', 'WC', 'BATHROOM' or rooms with bathroom fixtures shown)\n- Count the number of halls/living rooms (look for rooms labeled 'Hall', 'Living Room', 'Drawing Room', 'Lounge', 'Sitting Room', 'HALL' or large open spaces that serve as common areas)\n- Count the number of kitchens (look for rooms labeled 'Kitchen', 'Kit', 'KITCHEN' or rooms with kitchen fixtures/appliances shown)\n- Count any other rooms (store room, puja room, study room, balcony, etc.)\n- If the blueprint shows multiple floors (Ground Floor, First Floor, etc.), count rooms across ALL floors for the total property\n- Extract these room counts from the blueprint even if they are not mentioned in text documents\n- Be accurate and count each room type carefully - do not guess or estimate\n\nPROJECTIONS EXTRACTION - CRITICAL:\n- BALCONY: Look for balconies shown extending from the building (open spaces attached to rooms, often labeled 'Balcony', 'BAL', or visible as extended areas). Extract 'Yes' if visible, 'No' if not visible.\n- PORTICO: Look for a covered entrance area or portico at the front of the building (covered area at main entrance). Extract 'Yes' if visible, 'No' if not visible.\n- STAIRCASE: Check if the staircase extends beyond the building footprint or projects outward (staircases shown as series of steps, check if they project beyond main building line). Extract 'Yes' if projects, 'No' if doesn't project.\n- OVERHEAD TANK: Look for overhead water tanks on the roof or terrace (rectangular or circular structures on top floor or roof). Extract count (e.g., '1', '2') if visible, 'No' or '0' if not visible.\n- TERRACE: Look for terraces or open terrace areas (open areas on top floor or roof, may be labeled 'Terrace' or 'Open Terrace'). Extract count (e.g., '1', '2') if visible, 'No' or '0' if not visible.\n- OTHER PROJECTIONS: Check for any other structures extending beyond main building footprint (chajja/canopy, pergola, extended roof, etc.). Extract description if found.\n- CRITICAL: Do NOT return 'NA' for projections if you can clearly see them (or their absence) in the blueprint - extract what you actually see! Only use 'NA' if the blueprint is unclear or not available."
    
    # Build image list for reference in prompt
    image_list_note = ""
    if image_filenames:
        image_list_note = f"\n\n📸 IMAGES PROVIDED FOR ANALYSIS:\nThe following {len(image_filenames)} image(s) are available for analysis. When determining surrounding_land_use, surrounding_condition, negative_area, or outside_city_limits from images, you MUST identify which specific image(s) you used in the corresponding source_image fields:\n"
        for idx, img_name in enumerate(image_filenames, 1):
            # Identify image type based on filename
            img_lower = img_name.lower()
            img_type = "Unknown"
            if any(kw in img_lower for kw in ['surrounding', 'neighborhood', 'area', 'view']):
                img_type = "Surrounding View (likely for surrounding_land_use)"
            elif any(kw in img_lower for kw in ['map', 'google', 'satellite', 'location', 'gps']):
                img_type = "Location Map (likely for surrounding_land_use)"
            elif any(kw in img_lower for kw in ['exterior', 'outside', 'front', 'back']):
                img_type = "Exterior View (may show surrounding area)"
            elif any(kw in img_lower for kw in ['interior', 'inside', 'kitchen', 'room']):
                img_type = "Interior View"
            elif any(kw in img_lower for kw in ['blueprint', 'plan', 'floor', 'layout']):
                img_type = "Blueprint/Floor Plan"
            image_list_note += f"  Image {idx}: {img_name} ({img_type})\n"
        image_list_note += "\nCRITICAL: When you determine surrounding_land_use from images, you MUST specify which image(s) you used in the surrounding_land_use_source_image field (e.g., 'Image 2' or 'Image 2, Image 5'). If determined from documents, use 'From documents'.\n"
    
    # Build the final prompt with extracted text context
    prompt = f"""{base_prompt}

EXTRACTED TEXT CONTEXT FROM DOCUMENTS:
{docs_text}{pdf_note}{blueprint_note}{image_list_note}

Return JSON with the extracted information."""
    
    # Debug: Check if we have text to send
    if not docs_text or not docs_text.strip():
        error_msg = "❌ CRITICAL: No extracted text available to send to LLM!"
        if status_callback:
            status_callback(error_msg)
            status_callback("   This means:")
            status_callback("   1. PDFs may not have extractable text")
            status_callback("   2. Text extraction may have failed")
            status_callback("   3. Documents may be image-only PDFs")
            status_callback("   → LLM will try to extract from images only")
        print(f"[ERROR] {error_msg}")
    else:
        if status_callback:
            status_callback(f"✅ Extracted text context prepared and ready to send to LLM")
            status_callback(f"   - Prompt includes {len(docs_text):,} characters of extracted text")
            status_callback(f"   - Preview: {docs_text[:200]}...")
            status_callback(f"   - LLM will now analyze this context to generate the report")
        print(f"[DEBUG] Sending {len(docs_text):,} characters to LLM")
        print(f"[DEBUG] Text preview: {docs_text[:500]}")
    
    try:
        if status_callback:
            status_callback("🤖 Sending data to LLM API for analysis...")
            status_callback(f"   📊 Processing {len(content)} image(s) and {len(docs_text):,} characters of text")
            status_callback(f"   ⏱️ This may take 30-120 seconds depending on document complexity...")
        # Build content with text prompt first, then images
        message_content = [{"type": "text", "text": prompt}] + content

        payload = {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": message_content}],
            "max_tokens": 4000,  # Increased for comprehensive extraction
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
            "timeout": 300,  # 5 minute timeout for main extraction (can be slow with many images)
        }

        # Persist request payload for traceability (overwrites on each run)
        if output_dir is not None:
            try:
                output_dir.mkdir(exist_ok=True)
                request_path = output_dir / f"{property_folder.name}_llm_request.json"
                request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                if status_callback:
                    status_callback(f"💾 Saved LLM request payload to: {request_path.name}")
                else:
                    print(f"[LLM] Saved request payload to {request_path}")
            except Exception as err:
                warn_msg = f"⚠️ Failed to save LLM request payload: {err}"
                if status_callback:
                    status_callback(warn_msg)
                else:
                    print(warn_msg)

        if status_callback:
            status_callback("   🔄 Waiting for LLM response... (this is the slowest step)")
        
        response = client.chat.completions.create(**payload)
        
        if status_callback:
            status_callback("   ✅ Received LLM response, parsing data...")
        
        # Check if response has choices
        if not response.choices or len(response.choices) == 0:
            raise Exception("OpenAI API returned empty response - no choices available")
        
        text = response.choices[0].message.content
        
        # Clean the response - remove markdown code blocks if present
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        start = text.find("{")
        end = text.rfind("}") + 1
        
        try:
            if start >= 0 and end > start:
                parsed_json_str = text[start:end]
                if status_callback:
                    status_callback(f"📋 Parsing LLM JSON response ({len(parsed_json_str)} characters)...")
                structured_data = json.loads(parsed_json_str)
                
                # CRITICAL: Normalize all fields - ensure empty/None/null values become "NA"
                def normalize_field_value(value):
                    """Convert empty, None, or null values to 'NA'."""
                    if value is None:
                        return "NA"
                    value_str = str(value).strip()
                    if value_str == "" or value_str.lower() in {"null", "none", "n/a"}:
                        return "NA"
                    return value_str
                
                # Normalize all fields in structured_data
                for key in structured_data.keys():
                    structured_data[key] = normalize_field_value(structured_data[key])
                
                # Debug: Check what LLM returned
                if status_callback:
                    status_callback(f"✅ Successfully parsed LLM response")
                    # Count non-NA fields
                    non_na = sum(1 for k, v in structured_data.items() 
                                if v and str(v).strip() not in {"", "NA", "N/A", "null", "None"})
                    total = len(structured_data)
                    status_callback(f"   - LLM returned {non_na}/{total} fields with values")
                    if non_na == 0:
                        status_callback(f"   ⚠️ WARNING: LLM returned all NA values!")
                        status_callback(f"   - This may indicate:")
                        status_callback(f"     • Documents contain no extractable information")
                        status_callback(f"     • LLM could not find information in provided text/images")
                        status_callback(f"     • Check extracted text file to verify text was extracted")
                print(f"[DEBUG] LLM returned {non_na}/{total} non-NA fields")

                # CRITICAL: DO NOT merge fallback/default values
                # Only use values extracted by LLM from documents
                # If LLM returns "NA" or missing, keep it as "NA" - do NOT fill with defaults
                # This ensures report only contains information from actual property documents
                
                # POST-PROCESSING VALIDATION: Verify GPS coordinates are from document text, not images
                # Check if GPS coordinates exist in the extracted text from documents
                if full_extracted_text:
                    # Check for GPS coordinate patterns in the extracted text
                    gps_patterns = [
                        r'[Ll]atitude[:\s]*([\d°\'\"\.\sNSEW]+)',
                        r'[Ll]ongitude[:\s]*([\d°\'\"\.\sNSEW]+)',
                        r'[Gg][Pp][Ss][:\s]*([\d°\'\"\.\s,]+)',
                        r'[Cc]oordinate[:\s]*([\d°\'\"\.\s,]+)',
                        r'[Ll]at[:\s]*([\d°\'\"\.\sNSEW]+)',
                        r'[Ll]ong[:\s]*([\d°\'\"\.\sNSEW]+)',
                    ]
                    
                    gps_found_in_text = False
                    for pattern in gps_patterns:
                        if re.search(pattern, full_extracted_text, re.IGNORECASE):
                            gps_found_in_text = True
                            break
                    
                    # If GPS coordinates are provided but NOT found in document text, set to "NA"
                    gps_lat = structured_data.get("gps_latitude", "NA")
                    gps_lon = structured_data.get("gps_longitude", "NA")
                    
                    # Check if GPS values are not "NA" but also not found in document text
                    if (gps_lat and str(gps_lat).strip() not in {"", "NA", "N/A"}) or \
                       (gps_lon and str(gps_lon).strip() not in {"", "NA", "N/A"}):
                        if not gps_found_in_text:
                            # GPS coordinates were extracted but not found in document text
                            # This means they likely came from images - set to "NA"
                            if status_callback:
                                status_callback("⚠️ GPS coordinates found in response but NOT in document text - setting to 'NA' (likely extracted from images)")
                            structured_data["gps_latitude"] = "NA"
                            structured_data["gps_longitude"] = "NA"
                        else:
                            if status_callback:
                                status_callback("✓ GPS coordinates validated - found in document text")
                
                # POST-PROCESSING VALIDATION: Check for total_value_inr and total_value_amenities_inr in extracted text
                # If LLM returned "NA" but values exist in text, try to extract them
                if full_extracted_text:
                    # Check for total_value_inr patterns - more flexible patterns
                    total_value_patterns = [
                        # Specific patterns with labels
                        r'[Tt]otal\s+[Vv]alue\s+of\s+[Pp]roperty[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Mm]arket\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Vv]aluation\s+[Aa]mount[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Tt]otal\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Pp]roperty\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Vv]alue\s+of\s+[Pp]roperty[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        # Patterns with currency symbols
                        r'INR\s*[:\-]?\s*([\d,]{6,})',  # Large numbers after INR (6+ digits)
                        r'₹\s*([\d,]{6,})',  # Large numbers after ₹ symbol
                        r'Rs\.?\s*([\d,]{6,})',  # Large numbers after Rs
                        # Patterns with "as on" or date context
                        r'([\d,]{6,})\s+as\s+on\s+[Dd]ate\s+of\s+[Vv]aluation',
                        r'([\d,]{6,})\s+as\s+on',
                        # More flexible: any large number near value keywords (within 50 chars)
                        r'(?:[Tt]otal|[Mm]arket|[Vv]aluation|[Pp]roperty|[Vv]alue).{0,50}?([\d,]{6,})',
                        # Pattern for "Total Value of Property (INR):" format
                        r'[Tt]otal\s+[Vv]alue\s+of\s+[Pp]roperty\s*\([^)]*\)\s*[:\-]?\s*([\d,]+)',
                        # Pattern for Indian numbering (lakhs/crores) - e.g., 1,66,42,800
                        r'([\d]{1,2}(?:,\d{2}){2,})',  # Matches 1,66,42,800 format
                        # Fallback: find any large number (7+ digits) that might be a property value
                        # BUT we'll validate it's not a phone number later
                        r'\b([\d,]{7,})\b',
                    ]
                    
                    total_value_found = None
                    for pattern in total_value_patterns:
                        matches = re.finditer(pattern, full_extracted_text, re.IGNORECASE)
                        for match in matches:
                            value_str = match.group(1).replace(',', '').replace(' ', '').strip()
                            # Validate it's a reasonable property value (typically 6-10 digits)
                            if len(value_str) >= 6 and len(value_str) <= 12 and value_str.isdigit():
                                value_int = int(value_str)
                                
                                # CRITICAL: Reject phone numbers (Indian mobile numbers are typically 10 digits starting with 6-9)
                                # BUT: If it has commas or currency symbols nearby, it might be a property value (e.g., "9,12,44,08,627" with commas)
                                original_match = match.group(0)
                                match_start = match.start()
                                match_end = match.end()
                                # Check context around the match (100 chars before and after for better context)
                                context_start = max(0, match_start - 100)
                                context_end = min(len(full_extracted_text), match_end + 100)
                                context = full_extracted_text[context_start:context_end].lower()
                                
                                has_currency_or_commas = (',' in original_match or 
                                                         'INR' in original_match.upper() or 
                                                         '₹' in original_match or 
                                                         'Rs' in original_match or
                                                         'Rupee' in original_match)
                                
                                # Check if context contains phone-related keywords
                                phone_keywords = ['phone', 'mobile', 'contact', 'tel', 'telephone', 'call', 'number']
                                has_phone_keywords = any(keyword in context for keyword in phone_keywords)
                                
                                # Check if context contains value-related keywords
                                value_keywords = ['value', 'price', 'amount', 'valuation', 'cost', 'total', 'property', 'market', 'inr', 'rupee', 'rs', '₹']
                                has_value_keywords = any(keyword in context for keyword in value_keywords)
                                
                                # CRITICAL: Reject values from "Tax Details" sections - these are often OCR errors or tax amounts, not property values
                                tax_keywords = ['tax details', 'tax receipt', 'receipt', 'tax', 'municipal tax', 'property tax', 'panchayat']
                                has_tax_keywords = any(keyword in context for keyword in tax_keywords)
                                
                                # If it's in a tax-related context, it's likely NOT a property value
                                if has_tax_keywords and not has_value_keywords:
                                    # This is likely a tax amount or receipt number, not a property value - skip it
                                    if status_callback:
                                        status_callback(f"⚠️ Rejected value from tax context: {value_str} (likely tax amount/receipt, not property value)")
                                    continue
                                
                                # If it's exactly 10 digits starting with 6-9 AND has no currency/commas AND has phone keywords nearby, it's likely a phone number
                                if len(value_str) == 10 and value_str[0] in '6789' and not has_currency_or_commas and has_phone_keywords:
                                    # This is likely a phone number, skip it
                                    continue
                                
                                # If it's 10 digits starting with 6-9 but has value keywords and no phone keywords, it might be a property value
                                # Additional validation: property values are usually in lakhs/crores range
                                # Reject if it's too small (< 100,000) or too large (> 1,000,000,000,000)
                                if 100000 <= value_int <= 1000000000000:
                                    # If it's 10 digits starting with 6-9, only accept if it has value keywords or currency indicators
                                    if len(value_str) == 10 and value_str[0] in '6789':
                                        if has_value_keywords or has_currency_or_commas:
                                            total_value_found = value_str
                                            break
                                        else:
                                            # 10 digits starting with 6-9 without value context - likely phone number
                                            continue
                                    else:
                                        # Not a phone number pattern, accept it
                                        total_value_found = value_str
                                        break
                        if total_value_found:
                            break
                    
                    # If found in text but LLM returned "NA", use the extracted value
                    if total_value_found:
                        current_value = structured_data.get("total_value_inr", "NA")
                        if str(current_value).strip() in {"", "NA", "N/A"}:
                            structured_data["total_value_inr"] = total_value_found
                            if status_callback:
                                status_callback(f"✓ Found total_value_inr in document text: {total_value_found} (was 'NA' in LLM response)")
                    
                    # CRITICAL: Validate that the LLM response doesn't contain a phone number as total_value_inr
                    current_total_value = structured_data.get("total_value_inr", "NA")
                    if current_total_value and str(current_total_value).strip() not in {"", "NA", "N/A"}:
                        value_str_clean = str(current_total_value).replace(',', '').replace(' ', '').strip()
                        # Check if it's a phone number (10 digits starting with 6-9)
                        if len(value_str_clean) == 10 and value_str_clean.isdigit() and value_str_clean[0] in '6789':
                            # This is likely a phone number, not a property value - set to NA
                            if status_callback:
                                status_callback(f"⚠️ Rejected phone number as total_value_inr: {current_total_value} (setting to 'NA')")
                            structured_data["total_value_inr"] = "NA"
                    else:
                        # Log that we tried but didn't find it - also search for any large numbers for debugging
                        if status_callback:
                            # Try to find any large numbers in the text for debugging
                            all_large_numbers = re.findall(r'\b([\d,]{6,})\b', full_extracted_text)
                            if all_large_numbers:
                                status_callback(f"⚠️ total_value_inr not found. Found {len(all_large_numbers)} large number(s) in text: {all_large_numbers[:5]}...")
                            else:
                                status_callback(f"⚠️ total_value_inr not found in extracted text (length: {len(full_extracted_text)} chars, no large numbers found)")
                    
                    # Check for total_value_amenities_inr patterns - more flexible
                    amenities_value_patterns = [
                        # Specific patterns with labels
                        r'[Tt]otal\s+[Vv]alue\s+of\s+[Aa]menities[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Aa]menities\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Vv]alue\s+of\s+[Aa]menities[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Aa]menities\s+[Aa]mount[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Ff]urniture\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Ff]ixtures\s+[Vv]alue[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Ff]ixed\s+[Ff]urniture[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        r'[Ff]urniture\s+[&\s]+[Ff]ixtures[:\s]*[\(INR\)]*\s*[:\-]?\s*([\d,]+)',
                        # Patterns with currency symbols
                        r'[Aa]menities.*?INR\s*[:\-]?\s*([\d,]{5,})',
                        r'[Aa]menities.*?₹\s*([\d,]{5,})',
                        # More flexible: any number near amenities keywords
                        r'(?:[Aa]menities|[Ff]urniture|[Ff]ixtures).{0,50}?([\d,]{5,})',
                    ]
                    
                    amenities_value_found = None
                    for pattern in amenities_value_patterns:
                        matches = re.finditer(pattern, full_extracted_text, re.IGNORECASE)
                        for match in matches:
                            value_str = match.group(1).replace(',', '').replace(' ', '').strip()
                            # Validate it's a reasonable amenities value (typically 5-9 digits)
                            if len(value_str) >= 5 and len(value_str) <= 10 and value_str.isdigit():
                                # Additional validation: amenities values are usually in thousands to lakhs
                                value_int = int(value_str)
                                if 10000 <= value_int <= 100000000:  # 10k to 10 crore
                                    amenities_value_found = value_str
                                    break
                        if amenities_value_found:
                            break
                    
                    # If found in text but LLM returned "NA", use the extracted value
                    if amenities_value_found:
                        current_value = structured_data.get("total_value_amenities_inr", "NA")
                        if str(current_value).strip() in {"", "NA", "N/A"}:
                            structured_data["total_value_amenities_inr"] = amenities_value_found
                            if status_callback:
                                status_callback(f"✓ Found total_value_amenities_inr in document text: {amenities_value_found} (was 'NA' in LLM response)")
                    
                    # POST-PROCESSING: Check for percentage_completion in extracted text
                    percentage_patterns = [
                        r'[Pp]ercentage\s+of\s+[Pp]roperty\s+[Cc]ompletion[:\s]*([\d]+%)',
                        r'[Pp]ercentage\s+of\s+[Cc]ompletion[:\s]*([\d]+%)',
                        r'[Cc]ompletion\s+[Pp]ercentage[:\s]*([\d]+%)',
                        r'[Pp]roperty\s+[Cc]ompletion[:\s]*([\d]+%)',
                        r'([\d]+%)\s+[Cc]omplete',
                        r'([\d]+%)\s+[Cc]ompletion',
                        r'[Ff]ully\s+[Cc]onstructed|100%|[Cc]omplete',
                        r'[Rr]eady\s+to\s+[Mm]ove|100%',
                    ]
                    
                    percentage_found = None
                    for pattern in percentage_patterns:
                        match = re.search(pattern, full_extracted_text, re.IGNORECASE)
                        if match:
                            if '%' in match.group(0):
                                # Extract percentage value
                                pct_match = re.search(r'(\d+)%', match.group(0))
                                if pct_match:
                                    percentage_found = pct_match.group(1) + "%"
                                    break
                            elif any(term in match.group(0).lower() for term in ['fully constructed', 'complete', 'ready to move']):
                                percentage_found = "100%"
                                break
                    
                    # If found in text but LLM returned "NA", use the extracted value
                    if percentage_found:
                        current_value = structured_data.get("percentage_completion", "NA")
                        if str(current_value).strip() in {"", "NA", "N/A"}:
                            structured_data["percentage_completion"] = percentage_found
                            if status_callback:
                                status_callback(f"✓ Found percentage_completion in document text: {percentage_found} (was 'NA' in LLM response)")
                
                # POST-PROCESSING: Set date_of_valuation to current date
                from datetime import datetime
                current_date = datetime.now()
                # Format: "DD Month YYYY" (e.g., "20 November 2025")
                date_of_valuation = current_date.strftime("%d %B %Y")
                structured_data["date_of_valuation"] = date_of_valuation
                if status_callback:
                    status_callback(f"✓ Set date_of_valuation to current date: {date_of_valuation}")
                
                # Log which image was used for surrounding_land_use - Show actual filenames
                surrounding_land_use = structured_data.get("surrounding_land_use", "")
                surrounding_land_use_source = structured_data.get("surrounding_land_use_source_image", "")
                if surrounding_land_use and surrounding_land_use.strip() not in {"", "NA", "N/A"}:
                    if status_callback:
                        if surrounding_land_use_source and surrounding_land_use_source.strip() not in {"", "NA", "N/A", "From documents"}:
                            # Parse image number(s) from source
                            image_numbers = re.findall(r'Image\s+(\d+)', str(surrounding_land_use_source))
                            if image_numbers:
                                image_names_used = []
                                for img_num in image_numbers:
                                    img_idx = int(img_num) - 1  # Convert to 0-based index
                                    if 0 <= img_idx < len(image_filenames):
                                        image_names_used.append(image_filenames[img_idx])
                                if image_names_used:
                                    # Show actual filenames clearly
                                    filenames_str = ', '.join(image_names_used)
                                    status_callback(f"📸 Use of Surrounding Land: '{surrounding_land_use}'")
                                    status_callback(f"   📁 Source Image File(s): {filenames_str}")
                                    # Also update the source field to show filenames instead of "Image X"
                                    structured_data["surrounding_land_use_source_image"] = filenames_str
                                else:
                                    status_callback(f"📸 Use of Surrounding Land: '{surrounding_land_use}'")
                                    status_callback(f"   📁 Source: {surrounding_land_use_source}")
                            else:
                                # Check if source already contains filename
                                if any(fname in str(surrounding_land_use_source) for fname in image_filenames):
                                    status_callback(f"📸 Use of Surrounding Land: '{surrounding_land_use}'")
                                    status_callback(f"   📁 Source Image File(s): {surrounding_land_use_source}")
                                else:
                                    status_callback(f"📸 Use of Surrounding Land: '{surrounding_land_use}'")
                                    status_callback(f"   📁 Source: {surrounding_land_use_source}")
                        elif surrounding_land_use_source and "From documents" in str(surrounding_land_use_source):
                            status_callback(f"📄 Use of Surrounding Land: '{surrounding_land_use}'")
                            status_callback(f"   📁 Source: Extracted from property documents")
                        else:
                            status_callback(f"📸 Use of Surrounding Land: '{surrounding_land_use}'")
                            status_callback(f"   ⚠️ Source image not specified by LLM - check uploaded images")
                
                # POST-PROCESSING: Calculate age_years from year_of_construction
                year_of_construction = structured_data.get("year_of_construction", "")
                if year_of_construction and str(year_of_construction).strip() not in {"", "NA", "N/A"}:
                    try:
                        # Extract year from string (handle formats like "2020", "Year: 2020", etc.)
                        year_str = str(year_of_construction).strip()
                        # Try to extract 4-digit year
                        year_match = re.search(r'\b(19|20)\d{2}\b', year_str)
                        if year_match:
                            construction_year = int(year_match.group(0))
                            # Get current year
                            from datetime import datetime
                            current_year = datetime.now().year
                            # Calculate age
                            age = current_year - construction_year
                            if age >= 0:
                                structured_data["age_years"] = str(age)
                                if status_callback:
                                    status_callback(f"✓ Calculated age_years: {age} years (from year_of_construction: {construction_year})")
                            else:
                                # Future year - invalid
                                structured_data["age_years"] = "NA"
                                if status_callback:
                                    status_callback(f"⚠️ Invalid year_of_construction: {construction_year} (future year), setting age_years to 'NA'")
                        else:
                            # Could not extract valid year
                            if status_callback:
                                status_callback(f"⚠️ Could not extract valid year from year_of_construction: {year_str}, keeping age_years as is")
                    except (ValueError, AttributeError) as e:
                        if status_callback:
                            status_callback(f"⚠️ Error calculating age_years: {str(e)}, keeping age_years as is")
                else:
                    # year_of_construction is NA or missing
                    if "age_years" not in structured_data or structured_data.get("age_years", "").strip() in {"", "NA", "N/A"}:
                        structured_data["age_years"] = "NA"
                        if status_callback:
                            status_callback("ℹ️ year_of_construction not found, age_years set to 'NA'")
                
                # CRITICAL: Final normalization - ensure all fields are "NA" if empty/None/null
                # This ensures no field is left as empty string, None, or "null"
                def final_normalize_field(value):
                    """Final normalization to ensure all missing values are 'NA'."""
                    if value is None:
                        return "NA"
                    value_str = str(value).strip()
                    if value_str == "" or value_str.lower() in {"null", "none", "n/a"}:
                        return "NA"
                    return value_str
                
                # Normalize all fields one more time before saving
                for key in list(structured_data.keys()):
                    structured_data[key] = final_normalize_field(structured_data[key])
                
                # CRITICAL: Parse documents_list if it's a string (LLM sometimes returns it as string)
                if "documents_list" in structured_data:
                    docs_list = structured_data["documents_list"]
                    if isinstance(docs_list, str) and docs_list.strip() not in {"", "NA", "N/A", "null", "none"}:
                        try:
                            # Try JSON parsing first (for double-quoted JSON format)
                            import json as json_module
                            parsed_docs = json_module.loads(docs_list)
                            if isinstance(parsed_docs, list):
                                structured_data["documents_list"] = parsed_docs
                        except (json_module.JSONDecodeError, ValueError):
                            try:
                                # If JSON fails, try ast.literal_eval (for Python single-quote format)
                                import ast
                                parsed_docs = ast.literal_eval(docs_list)
                                if isinstance(parsed_docs, list):
                                    structured_data["documents_list"] = parsed_docs
                            except (ValueError, SyntaxError):
                                # If both fail, keep as string - report builder will handle it
                                pass
                
                # Log any missing fields (for debugging, but don't fill them)
                missing_fields = [key for key in structured_data.keys() 
                                if not structured_data.get(key) or 
                                str(structured_data.get(key)).strip() in {"", "NA", "N/A"}]
                if missing_fields and status_callback:
                    status_callback(f"ℹ️ {len(missing_fields)} fields returned as 'NA' by LLM (not found in documents)")
                
                # Ensure all required fields exist (set to "NA" if missing, but don't use defaults)
                # This is just to ensure the report structure is complete
                # The LLM should have already provided all fields, but if any are missing, set to "NA"
                # DO NOT use fallback_structured data

                # Persist LLM response for debugging/inspection if requested
                llm_response_path = None
                if output_dir:
                    try:
                        output_dir.mkdir(exist_ok=True)
                        llm_response_path = output_dir / f"{property_folder.name}_llm_response.json"
                        llm_response_path.write_text(
                            json.dumps(structured_data, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        if status_callback:
                            status_callback(f"💾 Saved LLM structured response to: {llm_response_path.name}")
                        else:
                            print(f"[LLM] Saved structured response to {llm_response_path}")
                    except Exception as err:
                        warn_msg = f"⚠️ Failed to save LLM response: {err}"
                        if status_callback:
                            status_callback(warn_msg)
                        else:
                            print(warn_msg)

                # Log to console for immediate visibility
                print("[LLM] Structured response preview:")
                print(json.dumps(structured_data, indent=2, ensure_ascii=False)[:2000])

                # Validate that we got actual data, not just placeholders
                if status_callback:
                    status_callback(f"Extracted {len(structured_data)} fields from documents")

                # Return both structured data, extracted text, and JSON file path
                # (Text files are saved earlier in generate_report_from_files)
                return structured_data, full_extracted_text, llm_response_path
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            print(f"⚠️ GPT-4.1 returned non-JSON output: {e}")
            print(f"Response preview: {text[:500]}")
            if status_callback:
                status_callback(f"⚠️ Error parsing LLM response: {str(e)}")
            return {"raw_output": text, "error": str(e)}, full_extracted_text, None
    except AuthenticationError as e:
        error_msg = f"API Authentication Error: Invalid or expired API key.\n\n"
        error_msg += f"Please check your OPENAI_API_KEY:\n"
        error_msg += f"1. Get a valid API key from: https://platform.openai.com/account/api-keys\n"
        error_msg += f"2. Set it in environment variable: OPENAI_API_KEY=sk-...\n"
        error_msg += f"3. Or create a .env file with: OPENAI_API_KEY=sk-...\n\n"
        error_msg += f"Error details: {str(e)}"
        raise ValueError(error_msg)
    except APIError as e:
        error_msg = f"OpenAI API Error: {str(e)}"
        raise ValueError(error_msg)

@track_time("generate_report_from_files")
def generate_report_from_files(documents: list, images: list, property_name: str, status_callback=None):
    """Generate report from selected document and image files."""
    try:
        if status_callback:
            status_callback("Creating temporary folder structure...")
        
        # Validate inputs
        if not documents and not images:
            raise ValueError("No documents or images provided. Please upload at least one file.")
        
        if not images or len(images) == 0:
            raise ValueError("No images provided. Please upload at least one image file.")
        
        # Create temporary folder structure
        temp_dir = Path(tempfile.mkdtemp(prefix="property_valuation_"))
        docs_dir = temp_dir / "documents"
        imgs_dir = temp_dir / "images"
        docs_dir.mkdir()
        imgs_dir.mkdir()
        
    except (IndexError, ValueError) as e:
        error_msg = f"Input validation error: {str(e)}"
        if status_callback:
            status_callback(f"❌ {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Error setting up report generation: {str(e)}"
        if status_callback:
            status_callback(f"❌ {error_msg}")
        return None, error_msg
    
    try:
        # Copy documents
        if status_callback:
            status_callback(f"Copying {len(documents)} document(s)...")
        for doc_path in documents:
            shutil.copy2(doc_path, docs_dir / Path(doc_path).name)
        
        # Copy images
        if status_callback:
            status_callback(f"Copying {len(images)} image(s)...")
        for img_path in images:
            shutil.copy2(img_path, imgs_dir / Path(img_path).name)
        
        # Use property_name or temp folder name
        folder_name = property_name.strip() if property_name.strip() else temp_dir.name
        
        output_dir = Path("./output")
        output_dir.mkdir(exist_ok=True)
        
        # Extract text first and save it IMMEDIATELY in human-readable format
        if status_callback:
            status_callback("📄 Step 1: Extracting text from documents...")
        
       
        docs = list(docs_dir.glob("*"))
        document_texts = []
        document_details = []  # Store detailed info for human-readable output
        documents_without_text = []  # Track PDFs that failed text extraction - IMPORTANT!
        
        for doc in docs:
            if doc.suffix.lower() == '.pdf':
                from extract_text import extract_text_from_pdf
                if status_callback:
                    status_callback(f"📄 Extracting text from {doc.name}...")
                text = extract_text_from_pdf(doc, status_callback=status_callback)
                if text.strip():
                    char_count = len(text)
                    word_count = len(text.split())
                    line_count = len(text.splitlines())
                    document_texts.append(f"=== Document: {doc.name} ===\n{text}")
                    document_details.append({
                        "filename": doc.name,
                        "type": "PDF",
                        "characters": char_count,
                        "words": word_count,
                        "lines": line_count,
                        "content": text
                    })
                    if status_callback:
                        status_callback(f"✅ Extracted {char_count:,} characters from {doc.name}")
                        status_callback(f"   Preview: {text[:150].replace(chr(10), ' ')}...")
                    print(f"[DEBUG] Extracted {char_count} chars from {doc.name}")
                else:
                    # Track this document as having no extracted text
                    documents_without_text.append(doc)
                    document_details.append({
                        "filename": doc.name,
                        "type": "PDF",
                        "status": "No text extracted",
                        "content": ""
                    })
                    if status_callback:
                        status_callback(f"⚠️ No text extracted from {doc.name} - will send as images to LLM")
                        status_callback(f"   → This PDF will be converted to images for LLM Vision API")
                    print(f"[WARN] No text extracted from {doc.name}")
            elif doc.suffix.lower() == '.txt':
                try:
                    text = doc.read_text(encoding='utf-8', errors='ignore')
                    if text.strip():
                        char_count = len(text)
                        word_count = len(text.split())
                        line_count = len(text.splitlines())
                        document_texts.append(f"=== Document: {doc.name} ===\n{text}")
                        document_details.append({
                            "filename": doc.name,
                            "type": "Text File",
                            "characters": char_count,
                            "words": word_count,
                            "lines": line_count,
                            "content": text
                        })
                except Exception as e:
                    document_details.append({
                        "filename": doc.name,
                        "type": "Text File",
                        "status": f"Error reading file: {str(e)}",
                        "content": ""
                    })
        
        full_extracted_text = "\n\n".join(document_texts) if document_texts else ""
        
        # Log summary of extraction
        if status_callback:
            status_callback(f"\n📊 Text Extraction Summary:")
            status_callback(f"  - Total documents processed: {len(docs)}")
            status_callback(f"  - Documents with extracted text: {len(document_texts)}")
            status_callback(f"  - Documents without text (will use images): {len(documents_without_text)}")
            status_callback(f"  - Total characters extracted: {len(full_extracted_text):,}")
        
        # Save extracted text IMMEDIATELY in human-readable format (BEFORE LLM processing)
        if status_callback:
            status_callback("💾 Saving extracted text to file...")
        
        from datetime import datetime
        
        # Create human-readable text file
        human_readable_text = []
        human_readable_text.append("=" * 80)
        human_readable_text.append("EXTRACTED TEXT FROM PROPERTY DOCUMENTS")
        human_readable_text.append("=" * 80)
        human_readable_text.append(f"Extraction Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        human_readable_text.append(f"Property Name: {folder_name}")
        human_readable_text.append(f"Total Documents Processed: {len(docs)}")
        human_readable_text.append(f"Documents with Extracted Text: {len([d for d in document_details if d.get('content')])}")
        human_readable_text.append("")
        human_readable_text.append("=" * 80)
        human_readable_text.append("")
        
        # Add each document's extracted text in a readable format
        for detail in document_details:
            human_readable_text.append("")
            human_readable_text.append("-" * 80)
            human_readable_text.append(f"DOCUMENT: {detail['filename']}")
            human_readable_text.append(f"Type: {detail.get('type', 'Unknown')}")
            
            if detail.get('status'):
                human_readable_text.append(f"Status: {detail['status']}")
            else:
                human_readable_text.append(f"Characters: {detail.get('characters', 0):,}")
                human_readable_text.append(f"Words: {detail.get('words', 0):,}")
                human_readable_text.append(f"Lines: {detail.get('lines', 0):,}")
            
            human_readable_text.append("-" * 80)
            human_readable_text.append("")
            
            if detail.get('content'):
                # Add the actual content
                human_readable_text.append(detail['content'])
            else:
                human_readable_text.append("[No text extracted from this document]")
            
            human_readable_text.append("")
        
        # Save human-readable text file
        text_file = output_dir / f"{folder_name}_extracted_text.txt"
        try:
            text_file.write_text("\n".join(human_readable_text), encoding='utf-8')
            if status_callback:
                status_callback(f"✅ Extracted text saved to: {text_file.name}")
                status_callback(f"   Location: {text_file.absolute()}")
        except Exception as e:
            if status_callback:
                status_callback(f"⚠️ Failed to save text file: {str(e)}")
            print(f"[WARN] Failed to save extracted text: {e}")
        
        # Save extracted text in both formats
        # Also save as JSON for programmatic access (already saved human-readable above)
        if full_extracted_text:
            from datetime import datetime
            extracted_data_json = {
                "extraction_date": datetime.now().isoformat(),
                "property_name": folder_name,
                "total_documents": len(docs),
                "documents_with_text": len([d for d in document_details if d.get('content')]),
                "total_characters": len(full_extracted_text),
                "documents": document_details
            }
            
            # Save as JSON file
            json_file = output_dir / f"{folder_name}_extracted_text.json"
            try:
                json_file.write_text(json.dumps(extracted_data_json, indent=2, ensure_ascii=False), encoding='utf-8')
                if status_callback:
                    status_callback(f"💾 Saved extracted text JSON to: {json_file.name}")
            except Exception as e:
                if status_callback:
                    status_callback(f"⚠️ Failed to save JSON file: {str(e)}")
        
        # Now extract structured info using GPT-4.1 (mapping text to structured format)
        if status_callback:
            status_callback("🧠 Step 2: Sending extracted text context to LLM for report generation...")
            if full_extracted_text and full_extracted_text.strip():
                status_callback(f"   - Using {len(full_extracted_text):,} characters of extracted text")
                status_callback(f"   - LLM will analyze this context to generate the structured report")
            else:
                status_callback("   - No extracted text available - will use images only")
        try:
            # Pass the already-extracted text to LLM to avoid re-extraction
            # Also pass documents_without_text so they can be sent as images to LLM
            structured, _, llm_response_json_path = extract_info_with_gpt4o(
                temp_dir,
                status_callback=status_callback,
                output_dir=output_dir,
                pre_extracted_text=full_extracted_text,
                documents_without_text=documents_without_text,
            )
            
            # Debug: Check if structured data has values
            if structured:
                non_na_count = sum(1 for k, v in structured.items() 
                                 if v and str(v).strip() not in {"", "NA", "N/A", "null", "None"})
                total_fields = len(structured)
                if status_callback:
                    status_callback(f"📊 Extracted {non_na_count}/{total_fields} non-NA fields from documents")
                print(f"[DEBUG] Structured data: {non_na_count}/{total_fields} fields have values")
                
                # Show sample of extracted data
                sample_fields = ["buyer_name", "seller_name", "address_1", "city", "total_value_inr", "property_reference_number"]
                found_values = []
                for field in sample_fields:
                    value = structured.get(field, "NOT_FOUND")
                    if value and str(value).strip() not in {"", "NA", "N/A", "null", "None"}:
                        found_values.append(f"{field}={str(value)[:30]}")
                        if status_callback:
                            status_callback(f"   ✓ {field}: {str(value)[:50]}")
                        print(f"[DEBUG] {field}: {value}")
                
                if not found_values:
                    if status_callback:
                        status_callback("❌ CRITICAL: No values extracted from documents! All fields are NA.")
                        status_callback("   This may indicate:")
                        status_callback("   1. Documents contain no extractable text")
                        status_callback("   2. LLM extraction failed")
                        status_callback("   3. Documents are not being processed correctly")
                    print("[ERROR] No values extracted - all fields are NA!")
                else:
                    if status_callback:
                        status_callback(f"✅ Found {len(found_values)} fields with values")
            else:
                if status_callback:
                    status_callback("❌ CRITICAL: Structured data is empty or None!")
                print("[ERROR] Structured data is empty!")
        except ValueError as e:
            # Re-raise ValueError (API key errors) with better message
            raise e
        except Exception as e:
            # Wrap other exceptions
            raise Exception(f"Error during extraction: {str(e)}")

        # Comparables will be enriched AFTER saving to database (see below)
        # This ensures the property is saved first, then we can find similar properties
        
        # Collect all images and let LLM select the best 5
        all_image_paths = sorted(imgs_dir.glob("*"))
        
        if status_callback:
            status_callback(f"📸 Analyzing {len(all_image_paths)} image(s) to select the best 5...")
        
        location_map = None
        
        # First, try to find location map from all images (before LLM selection)
        if status_callback:
            status_callback("🔍 Searching for location map in uploaded images...")
        
        # Prioritize Google Maps images first, then other map keywords
        location_map_keywords_priority = ['google', 'maps', 'googlemaps', 'google_maps']  # Highest priority
        location_map_keywords = ['map', 'location', 'satellite', 'street', 'gps', 'road', 'address', 'area', 'loc', 'coordinate']
        
        # First, try to find Google Maps specifically
        for img_path in all_image_paths:
            img_name_lower = Path(img_path).name.lower()
            if any(keyword in img_name_lower for keyword in location_map_keywords_priority):
                location_map = img_path
                if status_callback:
                    status_callback(f"🗺️ Google Maps image found by filename: {location_map.name}")
                print(f"📍 Google Maps identified: {location_map}")
                break
        
        # If no Google Maps found, try other map keywords
        if not location_map:
            for img_path in all_image_paths:
                img_name_lower = Path(img_path).name.lower()
                if any(keyword in img_name_lower for keyword in location_map_keywords):
                    location_map = img_path
                    if status_callback:
                        status_callback(f"🗺️ Location map found by filename: {location_map.name}")
                    print(f"📍 Location map identified: {location_map}")
                    break
        
        # Match images by filename patterns
        try:
            selected_images, llm_location_map = select_best_images_with_llm([str(p) for p in all_image_paths], status_callback)
            
            # Ensure selected_images is not empty and has at least some images
            if not selected_images or len(selected_images) == 0:
                if status_callback:
                    status_callback(f"⚠️ No images selected, using first available images")
                print(f"⚠️ No images selected, using fallback")
                selected_images = all_image_paths[:min(5, len(all_image_paths))]
            
            # Ensure we have at least 1 image (pad with available images if needed, but don't exceed 5)
            while len(selected_images) < min(5, len(all_image_paths)) and len(selected_images) < len(all_image_paths):
                for img_path in all_image_paths:
                    if img_path not in selected_images:
                        selected_images.append(img_path)
                        break
                else:
                    break  # No more images to add
            
            # Use LLM-identified location map if found
            # If we already found one by filename, prefer the LLM result if it's different (LLM is more accurate)
            if llm_location_map and llm_location_map.exists():
                # If filename search found one, check if LLM found a different one
                # Prefer LLM result as it's more accurate at identifying actual maps vs photos
                if not location_map or (location_map and str(location_map) != str(llm_location_map)):
                    location_map = llm_location_map
                    if status_callback:
                        status_callback(f"🗺️ Location map identified by AI: {location_map.name}")
                elif location_map and str(location_map) == str(llm_location_map):
                    if status_callback:
                        status_callback(f"✓ Location map confirmed by AI: {location_map.name}")
            
            # If still no location map found, use any image not in the selected images as fallback
            if not location_map and len(all_image_paths) > len(selected_images):
                selected_paths_str = [str(p) for p in selected_images]
                for img_path in all_image_paths:
                    if str(img_path) not in selected_paths_str:
                        location_map = img_path
                        if status_callback:
                            status_callback(f"🗺️ Using additional image as location map: {location_map.name}")
                        print(f"📍 Using fallback location map: {location_map}")
                        break
            
            if location_map:
                if status_callback:
                    status_callback(f"✓ Location map will be included in report: {location_map.name}")
                print(f"✅ Final location map: {location_map} (exists: {location_map.exists()})")
            else:
                if status_callback:
                    status_callback("ℹ️ No location map identified - report will show placeholder")
                print("⚠️ No location map found in uploaded images")
                
        except Exception as e:
            if status_callback:
                status_callback(f"⚠️ Image selection failed, using first 5 images: {str(e)}")
            print(f"⚠️ LLM selection error: {e}")
            # Fallback: use first 5 images (or all if less than 5)
            selected_images = all_image_paths[:min(5, len(all_image_paths))]
            if len(selected_images) == 0:
                raise ValueError("No images available for report generation")
            # location_map already found by filename search above, or remains None
        
        out_pdf = output_dir / f"{folder_name}_valuation_report.pdf"
        if status_callback:
            status_callback("📝 Generating PDF report...")
        
        # Verify location map before passing to report builder
        final_location_map = None
        if location_map:
            if isinstance(location_map, Path):
                if location_map.exists():
                    final_location_map = location_map
                    print(f"✅ Using location map: {final_location_map}")
                else:
                    print(f"⚠️ Location map path doesn't exist: {location_map}")
            else:
                # Convert string to Path
                loc_map_path = Path(location_map)
                if loc_map_path.exists():
                    final_location_map = loc_map_path
                    print(f"✅ Using location map (converted): {final_location_map}")
                else:
                    print(f"⚠️ Location map path doesn't exist: {loc_map_path}")
        
        # CRITICAL: Ensure selected_images is not empty before building report
        if not selected_images or len(selected_images) == 0:
            # Last resort: try to use any available images
            if len(all_image_paths) > 0:
                if status_callback:
                    status_callback("⚠️ No images selected, using all available images as fallback")
                selected_images = all_image_paths[:min(5, len(all_image_paths))]
            else:
                raise ValueError("Cannot generate report: No images selected and no images available. Please upload at least one image.")
        
        # Convert to Path objects if needed and validate they exist
        selected_images_paths = []
        for img in selected_images:
            img_path = Path(img) if not isinstance(img, Path) else img
            if img_path.exists():
                selected_images_paths.append(img_path)
            else:
                if status_callback:
                    status_callback(f"⚠️ Image not found, skipping: {img_path}")
        
        # CRITICAL: Final check - ensure we have at least one valid image
        if len(selected_images_paths) == 0:
            raise ValueError("Cannot generate report: No valid images found. Please check that uploaded images exist.")
        
        # ========================================================================
        # DATABASE SAVE AND COMPARABLES FLOW:
        # 1. Save LLM-extracted property data to database (all 10 tables)
        # 2. Find similar properties from database to use as comparables
        # 3. Merge comparables into structured data for report
        # 4. Update comparables in database with final merged comparables
        # ========================================================================
        
        # Step 1: Save to SQLite database FIRST (before finding comparables)
        # This saves the LLM JSON data to all 10 tables:
        # - property, property_area_details, property_setback_details,
        # - property_projection_details, property_construction_details,
        # - comparables, market_value_details, pricing_additional_charges,
        # - documents_list, audit_trail
        property_id = None
        try:
            if status_callback:
                status_callback("💾 Saving LLM-extracted property data to database...")
                status_callback("   → Creating/updating all 10 database tables...")
            property_id = save_to_sqlite_database(structured, status_callback)
            if status_callback:
                status_callback(f"✅ Property saved to database (Property ID: {property_id})")
                status_callback(f"   📁 Database: property_valuations.db")
                # Verify the save
                from db_comparables import get_property_count
                total_count = get_property_count()
                status_callback(f"   📊 Total properties in database: {total_count}")
        except Exception as e:
            error_msg = f"❌ CRITICAL: Failed to save property to database: {str(e)}"
            if status_callback:
                status_callback(error_msg)
            print(f"❌ SQLite save error: {e}")
            import traceback
            print(f"Full traceback:\n{traceback.format_exc()}")
            # Don't raise - continue with report generation even if save fails
            # But log the error clearly
        
        # Step 2: Now find comparables from database (excluding current property)
        # This happens AFTER saving so the property is in the database
        try:
            from db_comparables import find_similar_properties_from_db, get_property_count
            
            property_count = get_property_count()
            if status_callback:
                status_callback(f"📊 Database contains {property_count} property(ies)")
            
            # Try to find comparables from database
            # Comparable #1 = Subject property (always)
            # Comparable #2 = Best match from database (if available)
            db_comparables = []
            print(f"[Main] 🔍 Checking for comparables: property_count={property_count}, property_id={property_id}")
            
            if status_callback:
                status_callback("📊 Comparables Logic:")
                status_callback("   - Comparable #1: Subject property (input property)")
            
            if property_count > 1:  # Need at least 2 properties (current + 1 other)
                if status_callback:
                    status_callback("🔍 Searching database for Comparable #2 using parameters:")
                    status_callback("   PRIMARY: Pincode, Location (Locality/Sub-locality)")
                    status_callback("   SECONDARY: Land Area, Actual Area, Year, Bedrooms")
                print(f"[Main] 🔍 Calling find_similar_properties_from_db with exclude_property_id={property_id}")
                # Find matching properties from database based on subject property's parameters
                # Limit to 1 since we only need Comparable #2 (Comparable #1 is the subject property itself)
                db_comparables = find_similar_properties_from_db(
                    structured, 
                    exclude_property_id=property_id, 
                    limit=1  # Only need 1 match for Comparable #2
                )
                print(f"[Main] 🔍 find_similar_properties_from_db returned {len(db_comparables)} matching property(ies) from database")
                
                if db_comparables and len(db_comparables) > 0:
                    comp = db_comparables[0]
                    comp_city = comp.get("city", "N/A")
                    comp_locality = comp.get("locality", "N/A")
                    if status_callback:
                        status_callback(f"✅ Comparable #2: Matching property from database")
                        status_callback(f"   - City: {comp_city}, Locality: {comp_locality}")
                    # Merge comparables: Comparable #1 = subject property, Comparable #2 = database match
                    structured = merge_comparables(structured, db_comparables, source="database")
                    if status_callback:
                        status_callback(f"✅ Comparables merged into report data")
                    # Verify comparables were added
                    merged_comparables = structured.get("comparables", [])
                    print(f"[Main] ✅ Comparables merged: {len(merged_comparables)} comparables in structured data")
                    if len(merged_comparables) > 0:
                        comp1 = merged_comparables[0] if isinstance(merged_comparables[0], dict) else {}
                        print(f"[Main] ✅ Comparable #1 (Subject): City={comp1.get('city')}, Locality={comp1.get('locality')}, Address={comp1.get('address_1')}")
                        if len(merged_comparables) > 1:
                            comp2 = merged_comparables[1] if isinstance(merged_comparables[1], dict) else {}
                            print(f"[Main] ✅ Comparable #2 (Database): City={comp2.get('city')}, Locality={comp2.get('locality')}, Address={comp2.get('address_1')}")
                    
                    # Verify PDF-compatible fields were generated
                    pdf_fields_count = sum(1 for k in structured.keys() if '_comparable_' in k)
                    print(f"[Main] ✅ PDF-compatible fields generated: {pdf_fields_count} fields")
                    if pdf_fields_count > 0:
                        # Check a few sample fields
                        sample_fields = ['address_1_comparable_1', 'city_comparable_1', 'address_1_comparable_2', 'city_comparable_2']
                        for field in sample_fields:
                            val = structured.get(field, 'NOT_FOUND')
                            print(f"[Main]   - {field}: {val}")
                    else:
                        print(f"[Main] ⚠️ WARNING: No PDF-compatible fields found in structured data!")
                else:
                    if status_callback:
                        status_callback("ℹ️ No matching properties found in database")
                        status_callback("   - Comparable #2 will show NA")
                    # No database matches - Comparable #1 = subject property, Comparable #2 = NA
                    structured = merge_comparables(structured, [], source="none")
            else:
                # First property - Comparable #1 = subject property, Comparable #2 = NA
                print(f"[Main] ℹ️ Only {property_count} property(ies) in database - first property")
                if status_callback:
                    status_callback("ℹ️ First property in database")
                    status_callback("   - Comparable #1: Subject property (input property)")
                    status_callback("   - Comparable #2: NA (no other properties to compare)")
                structured = merge_comparables(structured, [], source="none")
        except Exception as exc:
            msg = f"[Comparables] Error: {exc}"
            print(msg)
            if status_callback:
                status_callback(msg)
            # Fallback: ensure comparables structure exists
            structured = merge_comparables(structured, [], source="none")
        
        # Debug: Verify structured data before generating report
        if status_callback:
            status_callback("🔍 Verifying structured data before report generation...")
        sample_fields_check = ["buyer_name", "seller_name", "address_1", "city", "total_value_inr", "property_reference_number"]
        missing_or_na = []
        for field in sample_fields_check:
            value = structured.get(field, "NOT_FOUND")
            if not value or str(value).strip() in {"", "NA", "N/A", "null", "None"}:
                missing_or_na.append(field)
        if missing_or_na:
            if status_callback:
                status_callback(f"⚠️ WARNING: {len(missing_or_na)} key fields are missing/NA: {', '.join(missing_or_na)}")
            print(f"[WARNING] Missing/NA fields before report: {missing_or_na}")
        else:
            if status_callback:
                status_callback("✅ All key fields have values")
        
        # Debug: Verify comparable fields before report generation
        pdf_comparable_fields = [k for k in structured.keys() if '_comparable_' in k]
        print(f"[Main] 🔍 Before report generation - PDF-compatible comparable fields: {len(pdf_comparable_fields)}")
        if len(pdf_comparable_fields) > 0:
            print(f"[Main]   Sample fields: {pdf_comparable_fields[:5]}...")
            # Check Comparable #1 fields
            comp1_fields = [f for f in pdf_comparable_fields if '_comparable_1' in f]
            comp2_fields = [f for f in pdf_comparable_fields if '_comparable_2' in f]
            print(f"[Main]   - Comparable #1 fields: {len(comp1_fields)}")
            print(f"[Main]   - Comparable #2 fields: {len(comp2_fields)}")
            if len(comp2_fields) > 0:
                sample_comp2 = structured.get('address_1_comparable_2', 'NOT_FOUND')
                print(f"[Main]   - Sample Comparable #2 address_1: {sample_comp2}")
        else:
            print(f"[Main] ⚠️ WARNING: No PDF-compatible comparable fields found before report generation!")
            # Check if comparables list exists
            comparables_list = structured.get("comparables", [])
            print(f"[Main]   - Comparables list length: {len(comparables_list)}")
            if len(comparables_list) > 0:
                print(f"[Main]   - Comparable #1 exists: {isinstance(comparables_list[0], dict)}")
                if len(comparables_list) > 1:
                    print(f"[Main]   - Comparable #2 exists: {isinstance(comparables_list[1], dict)}")
                    if isinstance(comparables_list[1], dict):
                        print(f"[Main]   - Comparable #2 city: {comparables_list[1].get('city', 'N/A')}")
        
        # Generate report with comparables included
        build_report_pdf(structured, selected_images_paths, out_pdf, final_location_map)
        
        # Save the final structured data (with comparables) to database
        # This ensures comparables are saved to the comparables table
        if status_callback:
            status_callback("💾 Saving final report data with comparables to DB...")
        try:
            # Update the property with comparables if property_id exists
            if property_id:
                from create_comprehensive_database import DB_PATH
                import sqlite3
                con = sqlite3.connect(str(DB_PATH))
                cur = con.cursor()
                
                # Delete existing comparables for this property
                cur.execute("DELETE FROM comparables WHERE property_id = ?", (property_id,))
                
                # Insert new comparables from structured data
                comparables_list = structured.get("comparables", [])
                for comp in comparables_list:
                    if comp and isinstance(comp, dict):
                        # Skip if all values are NA (empty comparable)
                        if all(not v or str(v).strip() in {"", "NA", "N/A"} for k, v in comp.items() if k != "source_of_information"):
                            continue
                        
                        from create_comprehensive_database import safe_get
                        cur.execute("""
                            INSERT INTO comparables (
                                property_id, address_1, address_2, address_3, address_4,
                                building_name, sub_locality, locality, city, pin_code,
                                date_of_transaction, transaction_type, approx_area_sft, area_type,
                                land_area_sft, approx_transaction_price_inr, approx_transaction_price_land_inr,
                                transaction_price_per_sft_inr, transaction_price_per_sft_land_inr, source_of_information
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            property_id,
                            safe_get(comp, "address_1"),
                            safe_get(comp, "address_2"),
                            safe_get(comp, "address_3"),
                            safe_get(comp, "address_4"),
                            safe_get(comp, "building_name"),
                            safe_get(comp, "sub_locality"),
                            safe_get(comp, "locality"),
                            safe_get(comp, "city"),
                            safe_get(comp, "pin_code"),
                            safe_get(comp, "date_of_transaction"),
                            safe_get(comp, "transaction_type"),
                            safe_get(comp, "approx_area_sft"),
                            safe_get(comp, "area_type"),
                            safe_get(comp, "land_area_sft"),
                            safe_get(comp, "approx_transaction_price_inr"),
                            safe_get(comp, "approx_transaction_price_land_inr"),
                            safe_get(comp, "transaction_price_per_sft_inr"),
                            safe_get(comp, "transaction_price_per_sft_land_inr"),
                            safe_get(comp, "source_of_information")
                        ))
                
                con.commit()
                con.close()
                if status_callback:
                    status_callback(f"✅ Saved {len(comparables_list)} comparable(s) to database")
        except Exception as e:
            if status_callback:
                status_callback(f"⚠️ Warning: Could not update comparables in database: {str(e)}")
            print(f"[WARN] Could not update comparables: {e}")
        
        # All data is already saved to property_valuations.db via save_to_sqlite_database()
        # No need for separate reports.db file
        if status_callback:
            status_callback("✅ All property data saved to property_valuations.db")
        
        if status_callback:
            status_callback(f"✅ Done! Report saved to {out_pdf}")
        
        return str(out_pdf), None
    except IndexError as idx_err:
        error_msg = f"IndexError (pop from empty list): {str(idx_err)}. This usually means trying to access an empty list."
        if status_callback:
            status_callback(f"❌ {error_msg}")
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return None, error_msg
    except ValueError as val_err:
        error_msg = f"ValueError: {str(val_err)}"
        if status_callback:
            status_callback(f"❌ {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        if status_callback:
            status_callback(f"❌ {error_msg}")
        import traceback
        print(f"[ERROR] {error_msg}")
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return None, error_msg
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def main_cli():
    """Command-line interface."""
    property_folder = Path(input("Enter property folder path: ").strip())
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)
    print("🧠 Extracting property info using GPT-4.1 (multi-language)...")
    structured, extracted_text, _ = extract_info_with_gpt4o(property_folder)
    
    # Save extracted text
    if extracted_text:
        extracted_text_file = output_dir / f"{property_folder.name}_extracted_text.txt"
        try:
            extracted_text_file.write_text(extracted_text, encoding='utf-8')
            print(f"💾 Saved extracted text to: {extracted_text_file}")
        except Exception as e:
            print(f"⚠️ Failed to save extracted text: {e}")
    
    # Collect image list for embedding
    images = sorted((property_folder / "images").glob("*"))

    out_pdf = output_dir / f"{property_folder.name}_valuation_report.pdf"
    print("📝 Generating PDF report...")
    build_report_pdf(structured, images, out_pdf)

    # All data is saved to property_valuations.db via save_to_sqlite_database()
    # No need for separate reports.db file
    print("✅ All property data saved to property_valuations.db")
    print(f"✅ Done! Report saved to {out_pdf}")

def main():
    """Main entry point - launches GUI by default."""
    from gui import main_gui
    main_gui()

if __name__ == "__main__":
    # Check if --cli flag is provided for command-line mode
    import sys
    if "--cli" in sys.argv:
        main_cli()
    else:
        main()
