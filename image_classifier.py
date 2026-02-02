"""
Image classification for property valuation reports.

Classifies uploaded images into 5 report categories and optionally identifies
a location map. Supports:
- LLM (GPT-4 Vision): best accuracy, uses OpenAI API
- Heuristic: filename/keyword-based, no API (fallback)
- Model (future): local ML model for cost/latency savings
"""
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Report image categories (used in report_builder and prompts)
# ---------------------------------------------------------------------------
CATEGORY_OUTSIDE_VIEW = 1
CATEGORY_INSIDE_VIEW = 2
CATEGORY_KITCHEN = 3
CATEGORY_SURROUNDING_VIEW = 4
CATEGORY_SIGNAGE = 5
CATEGORY_LOCATION_MAP = "location_map"

CATEGORIES = [
    (1, "Outside View of Property"),
    (2, "Inside View of Property"),
    (3, "View of Property Kitchen"),
    (4, "Surrounding View from Property"),
    (5, "Number board / signage in the vicinity"),
]

# Filename keywords for heuristic location-map detection (priority order)
LOCATION_MAP_KEYWORDS_PRIORITY = ["google", "maps", "googlemaps", "google_maps", "satellite"]
LOCATION_MAP_KEYWORDS = ["map", "location", "street", "gps", "road", "address", "area", "loc", "coordinate", "lat", "long"]


def get_location_map_by_filename(image_paths: List[str]) -> Optional[Path]:
    """Find a location map from image paths using filename keywords."""
    for img_path in image_paths:
        name = Path(img_path).name.lower()
        if any(k in name for k in LOCATION_MAP_KEYWORDS_PRIORITY):
            return Path(img_path)
    for img_path in image_paths:
        name = Path(img_path).name.lower()
        if any(k in name for k in LOCATION_MAP_KEYWORDS):
            return Path(img_path)
    return None


def classify_images_heuristic(
    image_paths: List[str],
    status_callback=None,
) -> Tuple[List[Path], Optional[Path]]:
    """
    Classify images using filename/keyword heuristics only (no API).
    Returns (list of up to 5 paths in category order, location_map path or None).
    """
    paths = [Path(p) for p in image_paths]
    if status_callback:
        status_callback("📷 Image classification (heuristic): using filename/keywords")

    location_map = get_location_map_by_filename(image_paths)
    # Use first 5 images; if we have a location map, prefer non-map images for the 5
    selected = []
    for p in paths:
        if len(selected) >= 5:
            break
        if location_map and p.resolve() == location_map.resolve():
            continue
        selected.append(p)
    # If we have fewer than 5 and location_map exists, add it as last "photo" only if needed
    while len(selected) < 5 and len(selected) < len(paths):
        for p in paths:
            if p not in selected:
                selected.append(p)
                break
        else:
            break

    result = selected[:5]
    if status_callback:
        for i, p in enumerate(result, 1):
            status_callback(f"  Photo {i}: {p.name}")
        if location_map:
            status_callback(f"  Location map: {location_map.name}")
    return result, location_map


def classify_images_llm(
    image_paths: List[str],
    client,
    status_callback=None,
) -> Tuple[List[Path], Optional[Path]]:
    """
    Classify images using GPT-4 Vision (LLM). Selects best 5 for report categories
    and identifies location map if present.
    """
    import base64
    import json
    from prompts import get_image_selection_prompt

    if status_callback:
        status_callback("🔍 Image classification (LLM): analyzing images for report categories...")

    if len(image_paths) <= 5:
        location_map = get_location_map_by_filename(image_paths)
        return [Path(p) for p in image_paths[:5]], location_map

    # Encode images for Vision API
    image_contents = []
    image_map = {}
    mime_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    for idx, img_path in enumerate(image_paths):
        path = Path(img_path)
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        ext = path.suffix.lower()
        mime = mime_types.get(ext, "image/jpeg")
        image_contents.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        image_map[idx] = str(img_path)

    prompt = get_image_selection_prompt(len(image_paths))
    content = [{"type": "text", "text": prompt}] + image_contents

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": content}],
        max_tokens=1000,
        temperature=0.7,
        timeout=120,
    )
    if not response.choices:
        raise RuntimeError("OpenAI returned no choices for image classification")

    text = response.choices[0].message.content
    start, end = text.find("{"), text.rfind("}") + 1
    result = json.loads(text[start:end])

    selected_paths = [None] * 5
    items = sorted(result.get("selected_images", []), key=lambda x: x.get("category", 0))
    used = set()
    for item in items:
        cat = item.get("category", 0)
        idx = item.get("image_index")
        if 1 <= cat <= 5 and idx is not None and 0 <= idx < len(image_paths) and idx not in used:
            selected_paths[cat - 1] = Path(image_map[idx])
            used.add(idx)
            if status_callback:
                status_callback(f"  Category {cat}: {Path(image_map[idx]).name}")

    # Fill missing with unused images
    for i in range(5):
        if selected_paths[i] is not None:
            continue
        for idx in range(len(image_paths)):
            if idx not in used:
                selected_paths[i] = Path(image_paths[idx])
                used.add(idx)
                break

    final = [p for p in selected_paths if p is not None]
    if len(final) < 5:
        for p in image_paths:
            pth = Path(p)
            if pth not in final:
                final.append(pth)
                if len(final) >= 5:
                    break
    final = final[:5]
    if not final:
        final = [Path(p) for p in image_paths[: min(5, len(image_paths))]]

    # Location map from LLM or filename
    location_map = None
    loc_idx = result.get("location_map_index")
    if loc_idx is not None and 0 <= loc_idx < len(image_paths):
        location_map = Path(image_map[loc_idx])
        if str(location_map) in [str(p) for p in final]:
            final = [p for p in final if str(p) != str(location_map)]
            while len(final) < 5 and len(final) < len(image_paths):
                for p in image_paths:
                    pth = Path(p)
                    if pth not in final and pth != location_map:
                        final.append(pth)
                        break
                else:
                    break
            final = final[:5]
    if location_map is None:
        location_map = get_location_map_by_filename(image_paths)

    if status_callback:
        status_callback(f"✓ Classified {len(final)} images; location_map={'yes' if location_map else 'no'}")
    return final, location_map


def classify_images(
    image_paths: List[str],
    method: str = "llm",
    client=None,
    status_callback=None,
) -> Tuple[List[Path], Optional[Path]]:
    """
    Single entry point for image classification.

    Args:
        image_paths: List of paths to image files.
        method: "llm" (GPT-4 Vision), "heuristic" (filename/keywords), or "model" (future).
        client: OpenAI client required when method="llm".
        status_callback: Optional callback(str) for progress messages.

    Returns:
        (selected_paths, location_map_path)
        - selected_paths: list of up to 5 Paths in category order 1..5.
        - location_map_path: Path to location map image or None.
    """
    if not image_paths:
        return [], None

    if method == "heuristic":
        return classify_images_heuristic(image_paths, status_callback)
    if method == "llm":
        if client is None:
            raise ValueError("OpenAI client is required for method='llm'")
        return classify_images_llm(image_paths, client, status_callback)
    if method == "model":
        # Placeholder for future: load local model and run inference
        if status_callback:
            status_callback("⚠️ Image classification method 'model' not implemented; using heuristic")
        return classify_images_heuristic(image_paths, status_callback)
    raise ValueError(f"Unknown classification method: {method}. Use 'llm', 'heuristic', or 'model'.")
