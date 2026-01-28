# file: prompts.py
"""Prompts used for LLM interactions in the property valuation report generator."""

def get_image_selection_prompt(image_count: int) -> str:
    """Get the prompt for selecting the best 5 images matching required categories."""
    return f"""You are analyzing property images to select exactly 5 images for a valuation report photograph section.

You have {image_count} images total. You MUST select exactly 5 images that match these specific categories:

CATEGORY 1 - Outside View of Property:
- Shows the EXTERIOR of the building/property
- Building facade, front view, external structure
- NOT interior, NOT kitchen, NOT surrounding area
- Example: front of house, building exterior

CATEGORY 2 - Inside View of Property:
- Shows INTERIOR rooms or living spaces
- Living room, bedroom, hallway, interior spaces
- NOT kitchen, NOT exterior, NOT map
- Example: interior room views, inside of property

CATEGORY 3 - View of Property Kitchen:
- Shows the KITCHEN area specifically
- Kitchen appliances, countertops, cooking area
- NOT other rooms, NOT exterior
- Example: kitchen view with cabinets, stove, etc.

CATEGORY 4 - Surrounding View from Property:
- Shows views of the NEIGHBORHOOD or surroundings
- Nearby buildings, street view, surrounding area
- NOT the property itself, NOT interior
- Example: view of nearby buildings, street scene

CATEGORY 5 - Number board / signage in the vicinity:
- Shows STREET SIGNS, BUILDING NUMBERS, or SIGNAGE
- House number, street name sign, address board
- NOT the property itself, NOT interior
- Example: house number plate, street sign

LOCATION MAP:
- Identify if any image is a LOCATION MAP (Google Maps, satellite view, street map, area map)
- Location maps MUST show:
  * Satellite/aerial view of an area with buildings, roads, and landmarks visible from above
  * Street map view with road names, building names, and location markers
  * Map pins/markers (red teardrop pins, blue circles) indicating specific locations
  * Map interface elements (zoom controls, compass, map type buttons, layer controls)
  * Bird's eye view or top-down view of a geographic area
  * Multiple roads, buildings, and geographic features visible in a map-like layout
  * The image should look like a screenshot from Google Maps, Apple Maps, or similar mapping application

- What is NOT a location map:
  * Regular photographs of buildings, streets, or property exteriors (even if they have GPS coordinates overlaid)
  * Photos of alleyways, passages, or outdoor spaces (these are property photos, not maps)
  * Images that show a single building or street from ground level
  * Photos with GPS coordinates written on them but are still just photos
  * Any image that is primarily a photograph taken from ground level or eye level

- CRITICAL: A location map must be an ACTUAL MAP VIEW (satellite, street map, or hybrid view) showing the area from above, NOT a ground-level photograph with coordinates overlaid on it.

- This is SEPARATE from the 5 property photo categories above
- A location map is NOT a property photo - it's a map showing the property's location in the area
- PRIORITIZE images that clearly show Google Maps interface, satellite views with multiple buildings/roads visible, or street maps with road names and markers
- HIGHEST PRIORITY: If you see an image that shows Google Maps interface (with search bar showing coordinates, map controls, satellite view with multiple roads and buildings visible from above), that MUST be selected as the location map
- REJECT: Any image that is a ground-level photograph (even if it has GPS coordinates overlaid) - these are property photos, not maps

CRITICAL REQUIREMENTS:
- Each category MUST have a DIFFERENT image
- Select images that BEST match each category description
- image_index is 0-based (first image is 0, second is 1, etc.)
- You have images from index 0 to {image_count-1}

Return JSON in this exact format:
{{
  "selected_images": [
    {{"category": 1, "image_index": <number>, "reason": "why this matches Outside View"}},
    {{"category": 2, "image_index": <number>, "reason": "why this matches Inside View"}},
    {{"category": 3, "image_index": <number>, "reason": "why this matches Kitchen"}},
    {{"category": 4, "image_index": <number>, "reason": "why this matches Surrounding View"}},
    {{"category": 5, "image_index": <number>, "reason": "why this matches Number board/signage"}}
  ],
  "location_map_index": <number or null>
}}

Return ONLY valid JSON. Each image_index must be between 0 and {image_count-1}. All 5 categories must have different image_index values."""


def get_property_extraction_prompt() -> str:
    """Get the prompt for extracting property information from documents and images."""
    return """
You are a multilingual property valuation assistant.
Read all the provided information (may contain English and Telugu text from documents and images).
Extract and summarize details needed for a MARKET VALUATION REPORT matching the CBRE format.

CRITICAL EXTRACTION RULES:
1. Extract ALL information that is EXPLICITLY stated in the provided documents/images - BE THOROUGH
2. DO NOT make assumptions, guesses, or invent values - THIS IS CRITICAL
3. If information IS found in the documents, you MUST extract it - do NOT default to "NA" if the value exists
4. If information is NOT found in the documents after thorough search, you MUST use "NA" for numeric fields or "N/A" for text fields
5. NEVER provide default values like "Yes", "No", "Good", "Residential", numbers like "2", "1", "14", "9", etc. if the information is not explicitly stated
6. Extract exact values as they appear in the documents (preserve formatting, numbers with commas)
7. For dates, extract in the exact format found or convert to readable format (e.g., "August 21, 2025")
8. IMAGE ANALYSIS FOR LOCATION & SURROUNDINGS - CRITICAL: Analyze all uploaded images (surrounding views, exterior photos, location maps, Google Maps satellite views) to extract Location & Surroundings information:
   - Use of Surrounding Land: Examine surrounding area photos and location maps to identify if surrounding land is Residential, Commercial, Mixed, Agricultural, or Industrial
   - Condition of Surroundings: Assess building quality, infrastructure, road conditions, and overall development visible in surrounding area photos
   - Negative Area: Look for negative features like garbage dumps, drains, sewers, high tension wires, graveyards, industrial pollution, or slums in surrounding area photos
   - Outside City Limits: Analyze location maps and Google Maps satellite views to determine if property is within city limits or in village/gram panchayat area
   - Extract these fields from images if they are not explicitly mentioned in documents
   - Do NOT return "NA" for these fields if you can determine them from the images - extract what you see!

9. BLUEPRINT/FLOOR PLAN ANALYSIS - CRITICAL: If you see any blueprint, floor plan, house plan, architectural drawing, or site plan in the images:
   - Carefully examine the floor plan to count rooms
   - Count bedrooms, bathrooms, halls, kitchens, and other rooms by identifying them in the plan
   - Look for room labels, room numbers, or room types marked on the plan
   - Count each room type accurately - do not guess or estimate
   - If the blueprint shows multiple floors, count rooms across all floors for the total property
   - Extract room counts from blueprints even if they are not mentioned in text documents
   - PROJECTIONS EXTRACTION - CRITICAL: Carefully examine the blueprint/floor plan for projections:
     * Look for BALCONY - check if there are any balconies shown extending from the building (usually shown as open spaces attached to rooms, often labeled as "Balcony", "BAL", or visible as extended areas)
     * Look for PORTICO - check if there is a covered entrance area or portico at the front of the building (often shown as a covered area at the main entrance)
     * Look for STAIRCASE - check if the staircase extends beyond the building footprint or projects outward (staircases are usually shown as a series of steps, check if they project beyond the main building line)
     * Look for OVERHEAD TANK - check if there is an overhead water tank shown on the roof or terrace (usually shown as a rectangular or circular structure on the top floor or roof)
     * Look for TERRACE - check if there is a terrace or open terrace area shown (usually shown as an open area on the top floor or roof, may be labeled as "Terrace" or "Open Terrace")
     * Look for OTHER PROJECTIONS - check for any other structures that extend beyond the main building footprint (e.g., chajja/canopy, pergola, extended roof, etc.)
     * If you see any of these projections in the blueprint, extract them as "Yes" or the count (for overhead tank and terrace). If you do NOT see them in the blueprint, extract as "No". Only use "NA" if the blueprint is unclear or not available.
     * CRITICAL: Do NOT return "NA" for projections if you can clearly see them (or their absence) in the blueprint images - extract what you actually see!
10. SEARCH THOROUGHLY: Look for values using multiple terms and variations. For example:
   - Total Value: Search for "Total Value", "Market Value", "Valuation Amount", "Total Market Value", "Property Value", "Value of Property", "Total Price", "Sale Price", "Transaction Value"
   - Amenities Value: Search for "Amenities Value", "Value of Amenities", "Amenities Amount", "Furniture Value", "Fixtures Value"
   - Base Value: Search for "Base Value", "Base Rate", "Base Price", "Rate per sft", "Price per sft", "Rate per square foot"
   - Construction Cost: Search for "Construction Cost", "Building Cost", "Cost per sft", "Construction Rate", "Replacement Cost"
   - Replacement Value: Search for "Replacement Value", "Replacement Cost", "Reconstruction Cost", "Rebuilding Cost"
11. GPS COORDINATES (LATITUDE/LONGITUDE) - CRITICAL RULE: 
   - Extract GPS coordinates ONLY from written text in property documents (PDF/TXT files)
   - DO NOT extract GPS coordinates from images, maps, satellite views, Google Maps screenshots, or any visual content
   - Look for explicit text mentions like "Latitude", "Longitude", "GPS", "Coordinates", "Lat", "Long", "LAT", "LONG" in the EXTRACTED TEXT from documents
   - If GPS coordinates are NOT explicitly written as text in any property document, you MUST return "NA" for both gps_latitude and gps_longitude
   - Even if you see GPS coordinates visually in images or maps, DO NOT extract them - they must be written text in documents
   - This is a strict rule: GPS coordinates from images = "NA", GPS coordinates from document text = extract the value
12. Return valid JSON ONLY - no markdown, no explanations outside the JSON
13. REMEMBER: Extract ALL values that exist in documents OR can be determined from images. Only use "NA" or "N/A" when information is genuinely not found after thorough search of both documents and images
14. PROPERTY REFERENCE NUMBER: Look for "tracker", "tracker number", "tracker ID", "property tracker", or similar terms in the documents. This is the property reference number that should appear in the report header. Extract it exactly as shown (e.g., "TRACKER123456789" or "REF20241234567")
15. BUYER/SELLER NAMES: In property documents, look for:
   - VENDEE = Buyer/Purchaser (extract as buyer_name)
   - VENDOR = Seller (extract as seller_name)
   - Also look for "Purchaser", "Buyer", "Home Loan Applicant" for buyer
   - Also look for "Seller", "Registered Owner" for seller
   Extract names exactly as they appear in the documents

Analyze the images and document text above and return JSON with these EXACT keys in the exact order they appear in the report:

===============================================================================
REPORT HEADER
===============================================================================
These fields appear at the top of the report, right after "MARKET VALUATION REPORT" header:

- property_reference_number: Property reference number - Look for labels such as "Tracker No.", "Reference ID", or "Property Ref." in the documents. This is the unique identifier for the case (e.g., "TRACKER123456789"). Extract it exactly as shown. If not found, return "NA".
- date_of_valuation: Date of valuation - This should be set to the CURRENT DATE when the report is being generated. Format: "DD Month YYYY" (e.g., "10 November 2025", "15 December 2025"). CRITICAL: Use the actual current date when generating the report. This will be automatically set by the system to today's date, but you can also provide it if you know the report generation date. Do NOT extract this from documents - it should always be the date when the report is being prepared.

===============================================================================
SECTION 1 - PROPERTY DESCRIPTION
===============================================================================
This section contains all property details and descriptions. It appears after the main header.

1.1 Transacting Parties:
This subsection lists the parties involved in the property transaction. It appears as a gray header "1.1 Transacting Parties" followed by:
- buyer_name: Buyer (Home Loan Applicant) name - Look for "Vendee", "Purchaser", "Buyer", "Home Loan Applicant" in the documents. The VENDEE is the buyer/purchaser of the property. Format: "- Buyer (Home Loan Applicant): [Name]"
- seller_name: Seller (Registered Owner) name - Look for "Vendor", "Seller", "Registered Owner" in the documents. The VENDOR is the seller of the property. Format: "- Seller (Registered Owner): [Name]"
- contact_person: Contact Person name - The person to contact regarding the property
- contact_number: Contact Person (& Telephone No.) - telephone number in format like "9885525855" or . Format: "- Contact Person (& Telephone No.): [Name] [Phone]"

IMPORTANT: In property documents, "Vendee" = Buyer/Purchaser, and "Vendor" = Seller. Extract these names exactly as they appear in the documents.

1.2 Property Address:
This subsection contains the complete property address. It appears as a gray header "1.2 Property Address" followed by a table with:
- address_1: Address 1 - First line of address (e.g., "House on Plot No. 123"). MUST be populated from the documents—never leave empty and never fabricate.
- address_2: Address 2 - Second line of address, often with "(As per site)" notation (e.g., "Ward No. 4, Elm Street (As per site)"). Include the "(As per site)" qualifier when present.
- address_3: Address 3 - Survey numbers or additional location details (e.g., "Survey Nos. 1075, 1085" or "Survey No. 277").
- address_4: Address 4 - Village or area name (e.g., "Riverside Village").
- building_name: Building Name - Name of the building or complex (e.g., "Maple Residency"). If documents explicitly state there is no building name, return "NA"; otherwise never invent a placeholder.
- sub_locality: Sub-Locality - Administrative sub-locality (e.g., "Northfield Mandal").
- locality: Locality - District or locality name (e.g., "Evergreen District").
- city: City - City name (e.g., "Springfield"). Use the city stated in the documents.
- pin_code: Pin Code - Postal code (e.g., "502032"). Preserve the exact digits (no spaces).
- gps_latitude: GPS Coordinates - Latitude in degrees, minutes, seconds format (e.g., "17º 31' 49.483\" N" or "17º 30' 59.148\" N"). Can also be decimal format. CRITICAL RULE: Extract ONLY from written text in property documents (PDF/TXT files), NOT from images, maps, or visual content. Search the EXTRACTED TEXT from documents for explicit mentions of "Latitude", "GPS Latitude", "Lat", "LAT", or coordinate information. If GPS coordinates are NOT found as written text in any property document, you MUST return "NA". DO NOT extract from images even if coordinates are visible.
- gps_longitude: GPS Coordinates - Longitude in degrees, minutes, seconds format (e.g., "78º 18' 52.295\" E" or "78º 19' 27.999\" E"). Can also be decimal format. CRITICAL RULE: Extract ONLY from written text in property documents (PDF/TXT files), NOT from images, maps, or visual content. Search the EXTRACTED TEXT from documents for explicit mentions of "Longitude", "GPS Longitude", "Long", "LONG", or coordinate information. If GPS coordinates are NOT found as written text in any property document, you MUST return "NA". DO NOT extract from images even if coordinates are visible.

1.3 Location & Surroundings:
This subsection describes the property's location context. It appears as a gray header "1.3 Location & Surroundings" followed by:
- surrounding_land_use: Use of Surrounding Land - Primary use of land in the surrounding area. CRITICAL: If this is not explicitly mentioned in documents, analyze the uploaded images (especially surrounding views, exterior photos, location maps, Google Maps satellite views) to determine the surrounding land use. Look for:
  * "Residential" - if you see houses, apartments, residential buildings, residential colonies in surrounding area
  * "Commercial" - if you see shops, markets, malls, commercial buildings, offices in surrounding area
  * "Mixed" - if you see both residential and commercial buildings
  * "Agricultural" - if you see farmland, agricultural fields
  * "Industrial" - if you see factories, industrial buildings
  Extract based on what you see in images if not mentioned in documents. Use "NA" only if images are unclear or not available.
  NOTE: The images you should primarily use for this determination are:
  - Category 4 images (Surrounding View from Property) - shows views of the neighborhood
  - Location maps (Google Maps satellite/street view) - shows aerial/satellite view of the area
  - Exterior photos that show surrounding buildings and area
  Analyze these specific image types to determine the surrounding land use.
- surrounding_land_use_source_image: Source Image for Surrounding Land Use - CRITICAL: If surrounding_land_use was determined from images, you MUST identify which specific image(s) you used. Look at the image list provided in the prompt (images are numbered starting from Image 1, Image 2, etc. in the order they appear). If determined from documents, return "From documents". If multiple images were used, list them separated by commas (e.g., "Image 2, Image 5"). Format: "Image X" or "Image X, Image Y" or "From documents" or "NA" if not applicable. This field is REQUIRED to track which image was used for validation purposes.
- surrounding_condition: Condition of Surroundings - Quality/condition of the surrounding area. CRITICAL: If this is not explicitly mentioned in documents, analyze the uploaded images (surrounding views, exterior photos, location maps) to assess the condition. Look for:
  * "Good" or "High-end" - well-maintained buildings, good infrastructure, clean surroundings, developed area
  * "Average" or "Mid-end" - moderately maintained buildings, average infrastructure
  * "Poor" or "Low-end" - poorly maintained buildings, basic infrastructure, undeveloped area
  Assess based on building quality, infrastructure, road conditions, and overall development visible in images. Use "NA" only if images are unclear or not available.
- negative_area: Negative Area - Whether there are any negative aspects to the area. CRITICAL: If this is not explicitly mentioned in documents, analyze the uploaded images (surrounding views, location maps) to identify negative features. Look for:
  * "Yes" - if you see garbage dumps, drains/nalas, sewers, high tension wires, graveyards, industrial pollution, slums, or other negative features in surrounding area
  * "No" - if surrounding area appears clean and free of negative features
  Extract based on what you see in images. Use "NA" only if images are unclear or not available.
- outside_city_limits: Outside City Limits - Whether the property is outside city limits. CRITICAL: If this is not explicitly mentioned in documents, analyze the uploaded images (location maps, Google Maps satellite views, surrounding area photos) and address information to determine:
  * "Yes" - if location maps show the property is in a village, gram panchayat area, or clearly outside main city limits
  * "No" - if location maps show the property is within city limits or urban area
  Also check address information - if address mentions "Village", "Gram Panchayat", "GP", it's likely outside city limits. Extract based on location maps and address. Use "NA" only if information is unclear.

1.4 Property Area:
This subsection appears under "PROPERTY SPECIFIC INFORMATION" header. It contains basic property area information:
- land_area_sft: Land Area of Property (sft) - Total land area in square feet. May be prefixed with "If available" (e.g., "1656" or "If available 1350")
- plot_demarcated: Plot Demarcated? - Whether the plot boundaries are clearly marked ("Yes" or "No")
- ease_of_identification: Ease of property identification - How easy it is to identify the property (e.g., "Good", "Fair", "Poor")
- location_map_attached: Location map / description attached - Whether a location map is provided ("Yes" or "No")
- nearby_landmark: Nearby Landmark - Prominent landmark near the property (e.g., "Senthan Green Park" or "Fusion International School")

PROPERTY SPECIFIC INFORMATION - BUILT-UP AREA:
This is a major subsection under "PROPERTY SPECIFIC INFORMATION" with a gray header "BUILT-UP AREA". It contains detailed area information in a table format:
- planned_area_sft: Planned Area of Property (sft) - The planned built-up area as per approved plans (e.g., "1,224" or "3,621")
- planned_area_source: Source - Source document for planned area (e.g., "As per copy of gram panchayat plan")
- planned_area_type: Type - Type of area measurement (e.g., "Built Up Area")
- permissible_area_far_sft: Permissible Area as per FAR (sft) - Floor Area Ratio permissible area (e.g., "NA" if not specified, or a number)
- permissible_area_type: Type - Type of area for FAR (e.g., "Built Up Area" or "NA")
- actual_area_sft: Actual Area of Property (sft) - The actual measured built-up area (e.g., "1,224" or "3,621")
- actual_area_type: Type - Type of area measurement (e.g., "Built Up Area")
- area_adopted_for_valuation_sft: Area adopted for Valuation (sft) - The area used for valuation purposes (e.g., "1,224" or "3,621")
- area_adopted_type: Type - Type of area adopted (e.g., "Built Up Area")
- loading_factor: Loading factor adopted - Loading factor if applicable (e.g., "NA" or a number)
- loading_factor_type: Type - Type for loading factor (e.g., "NA")
- deviation_in_area: Deviation in Area? - Whether there is a deviation between planned and actual area ("Yes" or "No")
- deviation_percent: % deviation in area, specify - Percentage of deviation if any (e.g., "NA" or percentage like "-5%")
- deviation_acceptable: Deviation Acceptable? - Whether the deviation is acceptable ("Yes", "No", or "NA")
- area_comments: Please enter Comments, if any - Detailed explanation with measurements, sources, floor-wise breakdown, and reasoning for area adopted (e.g., "As per the copy of gram panchayat plan and sale deed provided by HSBC, 1,224 sft was identified to be the built-up area...")

FLOOR HEIGHT DEVIATION:
This subsection appears under "PROPERTY SPECIFIC INFORMATION" with a gray header "FLOOR HEIGHT DEVIATION". It contains floor height compliance information:
- permitted_floor_height_max: Permitted Floor Height of Property (ft) - Maximum - Maximum allowed floor height as per regulations (e.g., "14")
- permitted_floor_height_min: Permitted Floor Height of Property (ft) - Minimum - Minimum required floor height as per regulations (e.g., "9")
- actual_floor_height_ft: Actual Floor Height of Property (ft) - The actual measured floor height (e.g., "10")
- deviation_in_floor_height: Deviation in Floor Height? - Whether actual height deviates from permitted range ("Yes" or "No")
- floor_height_deviation_acceptable: Deviation Acceptable? - Whether the deviation is acceptable ("Yes", "No", or "NA")
- floor_height_comments: Please enter Comments, if any - Any additional comments about floor height (e.g., "NA" or detailed explanation)

SET BACK DEVIATIONS:
This subsection appears under "PROPERTY SPECIFIC INFORMATION" with a gray header "SET BACK DEVIATIONS FRONT REAR LEFT SIDE RIGHT SIDE". It contains a table with setback information for all four sides:
- permitted_setback_front_ft: Permitted Set Backs (ft) - FRONT - Permitted front setback distance (e.g., "3" or "NA" if not applicable)
- permitted_setback_rear_ft: Permitted Set Backs (ft) - REAR - Permitted rear setback distance (e.g., "2.5" or "3")
- permitted_setback_left_ft: Permitted Set Backs (ft) - LEFT SIDE - Permitted left side setback distance (e.g., "2")
- permitted_setback_right_ft: Permitted Set Backs (ft) - RIGHT SIDE - Permitted right side setback distance (e.g., "4" or "3.75")
- actual_setback_front_ft: Actual Set Backs (ft) - FRONT - Actual measured front setback (e.g., "3" or "0")
- actual_setback_rear_ft: Actual Set Backs (ft) - REAR - Actual measured rear setback (e.g., "2.5" or "1.6")
- actual_setback_left_ft: Actual Set Backs (ft) - LEFT SIDE - Actual measured left side setback (e.g., "2" or "1.6")
- actual_setback_right_ft: Actual Set Backs (ft) - RIGHT SIDE - Actual measured right side setback (e.g., "1" or "0.75")
- deviation_in_setback_front: Deviation in Set Backs? - FRONT - Whether front setback deviates ("Yes", "No", or "NA")
- deviation_in_setback_rear: Deviation in Set Backs? - REAR - Whether rear setback deviates ("Yes" or "No")
- deviation_in_setback_left: Deviation in Set Backs? - LEFT SIDE - Whether left side setback deviates ("Yes" or "No")
- deviation_in_setback_right: Deviation in Set Backs? - RIGHT SIDE - Whether right side setback deviates ("Yes" or "No")
- setback_deviation_percent_front: Specify Deviation % - FRONT - Percentage deviation for front (e.g., "NA" or percentage like "-47%")
- setback_deviation_percent_rear: Specify Deviation % - REAR - Percentage deviation for rear (e.g., "NA" or percentage like "-47%")
- setback_deviation_percent_left: Specify Deviation % - LEFT SIDE - Percentage deviation for left side (e.g., "NA" or percentage like "-20%")
- setback_deviation_percent_right: Specify Deviation % - RIGHT SIDE - Percentage deviation for right side (e.g., "NA" or percentage like "-75%")
- setback_deviations_acceptable: Deviations Acceptable? - Whether all setbacks are acceptable ("Yes", "No", or "NA")
- setback_comments: Please enter Comments, if any - Detailed explanation of setbacks and deviations (e.g., "As per the copy of gram panchayat plan provided by bank. The deviation was observed on the right side due to projection encroaching into the setback area.")

PROJECTED CONSTRUCTION:
This subsection appears under "PROPERTY SPECIFIC INFORMATION" with a gray header "PROJECTED CONSTRUCTION". It contains information about projections from the building:
- projection_balcony: Projection(s) Sighted - Balcony - Whether balconies are present. CRITICAL: If there is a blueprint/floor plan in the images, carefully examine it for balconies (open spaces attached to rooms, often labeled "Balcony" or "BAL"). Extract "Yes" if balconies are visible, "No" if not visible, or "NA" only if blueprint is unclear or not available.
- projection_portico: Projection(s) Sighted - Portico - Whether portico is present. CRITICAL: If there is a blueprint/floor plan in the images, carefully examine it for a covered entrance area or portico at the front of the building. Extract "Yes" if portico is visible, "No" if not visible, or "NA" only if blueprint is unclear or not available.
- projection_staircase: Projection(s) Sighted - staircase - Whether staircase projection is present. CRITICAL: If there is a blueprint/floor plan in the images, carefully examine it to see if the staircase extends beyond the building footprint or projects outward. Extract "Yes" if staircase projects, "No" if it doesn't project, or "NA" only if blueprint is unclear or not available.
- projection_overhead_tank: Projection(s) Sighted - Overhead tank - Number of overhead tanks. CRITICAL: If there is a blueprint/floor plan in the images, carefully examine it for overhead water tanks on the roof or terrace (usually shown as rectangular or circular structures on the top floor). Extract the count (e.g., "1", "2") if visible, "No" or "0" if not visible, or "NA" only if blueprint is unclear or not available.
- projection_terrace: Projection(s) Sighted - Terrace - Number of terraces. CRITICAL: If there is a blueprint/floor plan in the images, carefully examine it for terraces or open terrace areas (usually shown as open areas on the top floor or roof, may be labeled "Terrace" or "Open Terrace"). Extract the count (e.g., "1", "2") if visible, "No" or "0" if not visible, or "NA" only if blueprint is unclear or not available.
- projection_others: Projection(s) Sighted - Other(s) - Other types of projections. CRITICAL: If there is a blueprint/floor plan in the images, check for any other structures that extend beyond the main building footprint (e.g., chajja/canopy, pergola, extended roof, etc.). Extract description if found, or "NA" if none.
- projection_public_nuisance: Projection(s) a Public Nuisance? - Whether any projections are a public nuisance. Extract "Yes" if any projections extend into public space or violate regulations, "No" if they don't, or "NA" if information is not available.
- projection_nuisance_reason: If Yes, specify reason thereof - Reason if projections are a nuisance (e.g., "NA" or detailed explanation like "Balcony extends beyond permitted setback area")

1.5 Condition of Property:
This subsection appears as a gray header "1.5 Condition of Property". It contains information about the property's physical condition:
- year_of_construction: Year of Construction - Year when the property was constructed (e.g., "2017" or "2020")
- age_years: Age of Property (years) - Current age of the property in years. CRITICAL: Calculate this automatically from year_of_construction to the current year. Formula: age_years = current_year - year_of_construction. For example, if year_of_construction is "2020" and current year is 2025, then age_years = "5". If year_of_construction is "2017" and current year is 2025, then age_years = "8". If year_of_construction is "NA" or not found, return "NA" for age_years. NOTE: This will be automatically calculated by the system, but you should still provide it if you can calculate it.
- exterior_condition: Exterior Condition of Property - Condition of exterior (e.g., "Good", "Fair", "Poor")
- exterior_condition_reason: If Poor, then reason thereon - Reason if exterior is in poor condition (e.g., "NA" or detailed explanation)
- interior_condition: Interior Condition of Property - Condition of interior (e.g., "Good", "Fair", "Poor")
- interior_condition_reason: If Poor, then reason thereon - Reason if interior is in poor condition (e.g., "NA" or detailed explanation)
- expected_future_life_years: Expected Future Physical Life of Property (years) - Estimated remaining useful life in years (e.g., "52" or "55")

1.6 Features & Amenities:
This subsection appears as a gray header "1.6 Features & Amenities". It contains detailed information about rooms, floors, and amenities in a table format. Return each of the following keys as plain text values (use "NA" only if the document is silent):
- bedrooms: Bedroom(s) count – e.g., "2" or "6". CRITICAL: If there is a blueprint, floor plan, house plan, or architectural drawing in the images, carefully count the number of bedrooms shown in the plan. Look for rooms labeled as "Bedroom", "BR", "B/R", or rooms that appear to be bedrooms based on their location and size in the floor plan. Extract the exact count.
- bathrooms: Bathroom(s) count – e.g., "2" or "6". CRITICAL: If there is a blueprint, floor plan, house plan, or architectural drawing in the images, carefully count the number of bathrooms shown in the plan. Look for rooms labeled as "Bathroom", "Bath", "W/C", "Toilet", "WC", or rooms with bathroom fixtures shown. Extract the exact count.
- halls: Hall(s) count – e.g., "1" or "3". CRITICAL: If there is a blueprint, floor plan, house plan, or architectural drawing in the images, carefully count the number of halls/living rooms shown in the plan. Look for rooms labeled as "Hall", "Living Room", "Drawing Room", "Lounge", "Sitting Room", or large open spaces that serve as common areas. Extract the exact count.
- kitchens: Kitchen(s) count – e.g., "1" or "3". CRITICAL: If there is a blueprint, floor plan, house plan, or architectural drawing in the images, carefully count the number of kitchens shown in the plan. Look for rooms labeled as "Kitchen", "Kit", or rooms with kitchen fixtures/appliances shown. Extract the exact count.
- other_rooms: Other rooms count – e.g., "1" or "0". CRITICAL: If there is a blueprint, floor plan, house plan, or architectural drawing in the images, count any other rooms not already counted (e.g., store room, puja room, study room, balcony, etc.). Extract the exact count.
- floors_in_building: Number of floors in the overall building – e.g., "Ground + 2 Floor"
- floors_in_property: Number of floors within the subject property unit – e.g., "2"
- lifts: Number of lift(s) – e.g., "0" or "1"
- stairs: Number of stair(s) – e.g., "1" or "3"
- amenities: Other amenities. List each amenity with optional one-time and recurring charges in a human-readable sentence (for example: "Covered Car Park (one-time: NA, recurring: NA); Children's Play Area (one-time: NA, recurring: NA)"). If no amenities are mentioned, return "NA".

1.7 Occupancy Status:
This subsection appears as a gray header "1.7 Occupancy Status". It contains information about who occupies the property:
- occupancy_status: Occupancy Status - Current occupancy status (e.g., "Occupied", "Self-occupied", "Rented", "Vacant")
- occupancy_comments: Detailed comments - Detailed explanation of occupancy status (e.g., "Based on our discussions with the designated contact person provided by the bank, the subject property was observed to be self-occupied." or similar detailed explanation)

1.8 Stage of Construction:
This subsection appears as a gray header "1.8 Stage of Construction". It contains information about construction completion:
- percentage_completion: Percentage of Property Completion - How much of the property is completed. CRITICAL: Search thoroughly for this value in documents using terms like "Percentage of Completion", "Completion Percentage", "% Complete", "Completion", "Stage of Construction", "Construction Status", "Property Completion", "100%", "75%", "Fully Constructed", "Complete", "Under Construction". Extract the exact percentage as shown (e.g., "100%" or "75%"). If the property is described as "complete", "fully constructed", "ready to move", or similar terms, extract as "100%". If this value exists in the documents, you MUST extract it - do NOT return "NA" if the value is present.
- construction_comments: Valuer's Comments on Construction - Comments about construction status and quality (e.g., "NA" or detailed comments about construction stage, quality, etc.)

===============================================================================
SECTION 2 - PROPERTY VALUATION
===============================================================================
This section contains all valuation-related information. It appears after Section 1 with a header banner "SECTION 2 - PROPERTY VALUATION".

2.1 Market Comparables:
This subsection appears as a gray header "2.1 Market Comparables" under "MARKET SPECIFIC INFORMATION". Capture two comparable properties (Comparable #1 and Comparable #2). For each comparable, supply every item below as a plain text value. Use "NA" only when the information is genuinely missing in the documents.
- address_1: Address 1 - First line of address (e.g., "House on Plot No. 160/Part & 161 (As per documents)" or "House on Plot No. 153"). MUST be populated from the documents—never leave empty and never fabricate.
- Comparable #1 – address_2: Address 2 - Second line of address, often with "(As per site)" notation (e.g., "House on Plot No. 161 (As per site)" or "Green Villas Road No. 4 (As per site)"). Include the "(As per site)" qualifier when present.
- Comparable #1 – address_3: Address 3 - Survey numbers or additional location details (e.g., "Survey Nos. 1075, 1085, 1086, 1087, 1091 & 1128" or "Survey No. 277").
- Comparable #1 – address_4: Address 4 - Village or area name (e.g., "Riverside Village and G. P." or "Oakwood Village").
- Comparable #1 – building_name: Building Name - Name of the building or complex (e.g., "Maple Residency" or "Green Valley Apartments"). If documents explicitly state there is no building name, return "NA"; otherwise never invent a placeholder.
- Comparable #1 – sub_locality: Sub-Locality - Administrative sub-locality (e.g., "Northfield Mandal" or "Westside Mandal").
- Comparable #1 – locality: District / locality.locality: Locality - District or locality name (e.g., "Evergreen District" or "Springfield District").
- Comparable #1 – city: City - City name (e.g., "Springfield" or "Riverside"). Use the city stated in the documents.
- Comparable #1 – pin_code: Pin Code - Postal code (e.g., "123456" or "789012"). Preserve the exact digits (no spaces).
- Comparable #1 – date_of_transaction: Transaction date (e.g., "May-2025" or "03-Feb-2020").
- Comparable #1 – transaction_type: Transaction Type - Type of transaction (e.g., "Actual", "Registered", "Quoted", etc.).
- Comparable #1 – approx_area_sft: Approximate Area - Built-up or plot area in square feet.
- Comparable #1 – area_type: Area Type - Type of area (e.g., "Built Up Area", "Carpet Area", "Land Area", etc.).
- Comparable #1 – land_area_sft: Land Area - Land area in square feet if available.
- Comparable #1 – approx_transaction_price_inr: Approximate Transaction Price (Built-Up) – Enter the total rupee amount for the transaction as quoted/recorded (e.g., "8,500,000" or "12,000,000"). Use digits with commas; never spell out the number.
- Comparable #1 – approx_transaction_price_land_inr: Approximate Transaction Price (Land Portion) – Provide the rupee value attributable solely to land, when the documents specify it (e.g., "15,000,000" or "20,000,000"). If not provided, set to "NA".
- Comparable #1 – transaction_price_per_sft_inr: Transaction Price per Square Foot (Built-Up) – State the built-up rate per sq. ft. (e.g., "3,500" or "4,200"). Use numeric digits only.
- Comparable #1 – transaction_price_per_sft_land_inr: Transaction Price per Square Foot (Land) – State the land rate per sq. ft. if available (e.g., "9,500" or "11,000"). If not mentioned, return "NA".
- Comparable #1 – source_of_information: Source of Information – Identify the exact source text (e.g., "Local estate agent; quoted rate adjusted for negotiation", "Registered sale deed dated 03-Feb-2020"). Do not invent or summarise beyond what is provided.

- Comparable #2 – address_1: Address 1 - First line of address (e.g., "House on Plot No. 160/Part & 161 (As per documents)" or "House on Plot No. 153"). MUST be populated from the documents—never leave empty and never fabricate.
- Comparable #2 – address_2: Address 2 - Second line of address, often with "(As per site)" notation (e.g., "House on Plot No. 161 (As per site)" or "Green Villas Road No. 4 (As per site)"). Include the "(As per site)" qualifier when present.
- Comparable #2 – address_3: Address 3 - Survey numbers or additional location details (e.g., "Survey Nos. 1075, 1085, 1086, 1087, 1091 & 1128" or "Survey No. 277").
- Comparable #2 – address_4: Address 4 - Village or area name (e.g., "Riverside Village and G. P." or "Oakwood Village").
- Comparable #2 – building_name: Building Name - Name of the building or complex (e.g., "Maple Residency" or "Green Valley Apartments"). If documents explicitly state there is no building name, return "NA"; otherwise never invent a placeholder.
- Comparable #2 – sub_locality: Sub-Locality - Administrative sub-locality (e.g., "Northfield Mandal" or "Westside Mandal").
- Comparable #2 – locality: District / locality.locality: Locality - District or locality name (e.g., "Evergreen District" or "Springfield District").
- Comparable #2 – city: City - City name (e.g., "Springfield" or "Riverside"). Use the city stated in the documents.
- Comparable #2– pin_code: Pin Code - Postal code (e.g., "123456" or "789012"). Preserve the exact digits (no spaces).
- Comparable #2 – date_of_transaction: Transaction date (e.g., "May-2025" or "03-Feb-2020").
- Comparable #2 – transaction_type: Transaction Type - Type of transaction (e.g., "Actual", "Registered", "Quoted", etc.).
- Comparable #2 – approx_area_sft: Approximate Area - Built-up or plot area in square feet.
- Comparable #2 – area_type: Area Type - Type of area (e.g., "Built Up Area", "Carpet Area", "Land Area", etc.).
- Comparable #2 – land_area_sft: Land Area - Land area in square feet if available.
- Comparable #2 – approx_transaction_price_inr: Approximate Transaction Price (Built-Up) – Enter the total rupee amount for the transaction as quoted/recorded (e.g., "8,500,000" or "12,000,000"). Use digits with commas; never spell out the number.
- Comparable #2 – approx_transaction_price_land_inr: Approximate Transaction Price (Land Portion) – Provide the rupee value attributable solely to land, when the documents specify it (e.g., "15,000,000" or "20,000,000"). If not provided, set to "NA".
- Comparable #2 – transaction_price_per_sft_inr: Transaction Price per Square Foot (Built-Up) – State the built-up rate per sq. ft. (e.g., "3,500" or "4,200"). Use numeric digits only.
- Comparable #2 – transaction_price_per_sft_land_inr: Transaction Price per Square Foot (Land) – State the land rate per sq. ft. if available (e.g., "9,500" or "11,000"). If not mentioned, return "NA".
- Comparable #2 – source_of_information: Source of Information – Identify the exact source text (e.g., "Local estate agent; quoted rate adjusted for negotiation", "Registered sale deed dated 03-Feb-2020"). Do not invent or summarise beyond what is provided.

MARKET SPECIFIC INFORMATION:
This is a gray header that appears before "2.2 Prevailing Market Values" in Section 2.

2.2 Prevailing Market Values:
This subsection appears as a gray header "2.2 Prevailing Market Values" under "MARKET SPECIFIC INFORMATION". It contains market value ranges:
- market_value_range_land_psft_min: Market value range for land (psft) - Minimum - Minimum market value per square foot for land. CRITICAL: Calculate this from Comparable Property transaction prices. Use the MINIMUM value from transaction_price_per_sft_land_inr_comparable_1 and transaction_price_per_sft_land_inr_comparable_2. If only one comparable has land price, use that value for both min and max. If NO comparable properties have land transaction prices, search documents for "Market Value Range", "Land Rate", "Land Value Range", "Market Rates", "Land Price per sft", "Prevailing Market Values". If NOT found in documents, return "NA" - DO NOT use example values from prompts - these are just examples, not real data.
- market_value_range_land_psft_max: Market value range for land (psft) - Maximum - Maximum market value per square foot for land. CRITICAL: Calculate this from Comparable Property transaction prices. Use the MAXIMUM value from transaction_price_per_sft_land_inr_comparable_1 and transaction_price_per_sft_land_inr_comparable_2. If only one comparable has land price, use that value for both min and max. If NO comparable properties have land transaction prices, search documents for "Market Value Range", "Land Rate", "Land Value Range", "Market Rates", "Land Price per sft", "Prevailing Market Values". If NOT found in documents, return "NA" - DO NOT use example values from prompts - these are just examples, not real data.
- market_value_range_psft_min: Market value range (psft) - Minimum - Minimum market value per square foot for built-up area. CRITICAL: Calculate this from Comparable Property transaction prices. Use the MINIMUM value from transaction_price_per_sft_inr_comparable_1 and transaction_price_per_sft_inr_comparable_2. If only one comparable has built-up price, use that value for both min and max. If NO comparable properties have built-up transaction prices, search documents for "Market Value Range", "Built-up Rate", "Built-up Value Range", "Market Rates", "Price per sft", "Prevailing Market Values". If NOT found in documents, return "NA" - DO NOT use example values from prompts - these are just examples, not real data.
- market_value_range_psft_max: Market value range (psft) - Maximum - Maximum market value per square foot for built-up area. CRITICAL: Calculate this from Comparable Property transaction prices. Use the MAXIMUM value from transaction_price_per_sft_inr_comparable_1 and transaction_price_per_sft_inr_comparable_2. If only one comparable has built-up price, use that value for both min and max. If NO comparable properties have built-up transaction prices, search documents for "Market Value Range", "Built-up Rate", "Built-up Value Range", "Market Rates", "Price per sft", "Prevailing Market Values". If NOT found in documents, return "NA" - DO NOT use example values from prompts - these are just examples, not real data.
- market_value_information_source: Information Obtained From - Source of market value information. CRITICAL: If market values were calculated from comparable properties, use the source_of_information from those comparables (e.g., "Registered sale deed dated 03-Feb-2020" if that's the comparable source). If extracted from market research documents, use that source. If NOT found in documents, return "NA" - DO NOT invent sources.

VALUATION ANALYSIS:
This is a gray header that appears before "2.3 Defining Market Value" in Section 2.

2.3 Defining Market Value:
This subsection appears as a gray header "2.3 Defining Market Value" under "VALUATION ANALYSIS". It contains the standard definition of market value:
- market_value_definition: Standard market value definition text - The official definition of market value as per valuation standards. This is typically a long paragraph explaining what market value means. Can be extracted from documents or use the standard definition: "Market Value is defined as 'an opinion of the best price at which the sale of an interest in property would have been completed unconditionally for cash consideration on the date of the valuation, assuming (1) a willing seller; (2) that, prior to the date of valuation, there had been a reasonable period (having regard to the nature of the property and the state of the market) for the proper marketing of the interest and for the agreement of the sale price; (3) that, the state of the market, level of values and other circumstances were, on any earlier assumed date of exchange of contracts, the same as on the date of valuation; (4) that no account is taken of any additional bid by a prospective buyer with a special interest; (5) that both parties to the transaction had acted knowledgeably, prudently and without compulsion.'"

2.4 Market Value of Property:
This subsection appears as a gray header "2.4 Market Value of Property" under "VALUATION ANALYSIS". It contains the calculated market value broken down into sections:

BASE VALUE:
This appears as a bold header "BASE VALUE" within subsection 2.4:
- base_value_land_psft: Base Value of Property (for land) (Rs psft) - Base value per square foot for land portion. CRITICAL: Search thoroughly using terms like "Base Value", "Base Rate", "Base Price", "Land Rate", "Land Price", "Rate per sft for land", "Land Value per sft". Extract the exact value (e.g., "7,500" or "7,800"). If this value exists in documents, you MUST extract it.
- base_value_built_psft: Base Value of Property (Rs psft) - Base value per square foot for built-up area. CRITICAL: Search thoroughly using terms like "Base Value", "Base Rate", "Base Price", "Built-up Rate", "Built-up Price", "Rate per sft", "Price per sft", "Rate per square foot", "Built-up Value per sft". Extract the exact value (e.g., "1,800" or "2,200"). If this value exists in documents, you MUST extract it.
- base_value_type: Type - Type of area for base value (e.g., "Built Up Area" or "as on Date of Valuation")

APPLICABLE ADDITIONAL CHARGES:
This appears as a bold header "APPLICABLE ADDITIONAL CHARGES" within subsection 2.4. It contains a table with additional charges:
- fixed_furniture_fixtures: Fixed Furniture & Fixtures - Value of fixed furniture and fixtures in INR (e.g., "1,200,000" or "600,000" or "NA")
- fixed_furniture_fixtures_description: Description - Description of furniture/fixtures (e.g., "NA" or detailed description)
- preferred_location_charge: Preferred Location Charge - Additional charge for preferred location in INR (e.g., "NA" or amount)
- preferred_location_charge_description: Description - Description of preferred location charge (e.g., "NA" or description)
- external_development_charge: External Development Charge - External development charges in INR (e.g., "NA" or amount)
- external_development_charge_description: Description - Description of external development charge (e.g., "NA" or description)
- car_park_charge: Car Park - Car parking charges in INR (e.g., "NA" or amount)
- car_park_charge_description: Description - Description of car park charge (e.g., "NA" or description)
- transfer_charges: Transfer Charges (Noida Only) - Transfer charges applicable only for Noida properties (e.g., "NA" or amount)
- transfer_charges_description: Description - Description of transfer charges (e.g., "NA" or description)
- sales_tax: Sales Tax - Sales tax amount in INR (e.g., "NA" or amount)
- sales_tax_description: Description - Description of sales tax (e.g., "NA" or description)

TOTAL VALUE:
This appears as a bold header "TOTAL VALUE" within subsection 2.4. It contains the final calculated values:
- total_value_inr: Total Value of Property (INR) - Total market value of the property in Indian Rupees. 
  ⚠️ CRITICAL - THIS IS A REQUIRED FIELD: This value is ALWAYS present in property valuation documents. You MUST find and extract it.
  Search terms to look for (check ALL of these):
  • "Total Value of Property"
  • "Total Value"
  • "Market Value"
  • "Valuation Amount"
  • "Total Market Value"
  • "Property Value"
  • "Value of Property"
  • "Total Price"
  • "Sale Price"
  • "Transaction Value"
  • "Valuation"
  • "Market Price"
  • "Property Valuation"
  • "INR" followed by a large number (8+ digits)
  • "Rupees" followed by a large number
  • Any number with "lakh", "crore", or large amounts in Indian numbering
  Examples of how it might appear:
  - "Total Value of Property (INR): 16,642,800"
  - "Market Value: INR 16,642,800/-"
  - "Total Value: 16642800"
  - "Valuation Amount: ₹16,642,800"
  - "Property Value: 1,66,42,800"
  Extract the exact amount as shown (preserve commas if present, e.g., "16,642,800" or "16642800"). 
  ⚠️ CRITICAL: DO NOT extract phone numbers or contact numbers as property values. Phone numbers are typically 10 digits starting with 6, 7, 8, or 9 (e.g., 9124408627, 9885525855). Property values are typically 7-9 digits (lakhs to crores range) and are usually associated with currency symbols (INR, ₹, Rs) or value-related keywords. If you see a 10-digit number near "Contact", "Phone", "Mobile", "Tel", it is a phone number - DO NOT use it as total_value_inr.
  ⚠️ IF YOU SEE ANY LARGE NUMBER (typically 7-9 digits) RELATED TO PROPERTY VALUE IN THE DOCUMENTS, THAT IS LIKELY THE TOTAL VALUE - EXTRACT IT!
  DO NOT return "NA" unless you have searched the ENTIRE document text and confirmed the value is truly not present.

- total_value_amenities_inr: Total Value of Amenities (INR) - Total value of amenities in Indian Rupees.
  ⚠️ CRITICAL: Search thoroughly for this value using terms like:
  • "Amenities Value"
  • "Value of Amenities"
  • "Amenities Amount"
  • "Furniture Value"
  • "Fixtures Value"
  • "Fixed Furniture"
  • "Amenities Cost"
  • "Furniture & Fixtures"
  • "Value of Furniture"
  • "Value of Fixtures"
  Examples of how it might appear:
  - "Total Value of Amenities (INR): 1,200,000"
  - "Amenities Value: INR 1,200,000/-"
  - "Value of Amenities: 1200000"
  - "Furniture Value: ₹12,00,000"
  Extract the exact amount as shown (e.g., "1,200,000" or "1200000" with "as on Date of Valuation"). 
  If this value exists in the documents, you MUST extract it - do NOT return "NA" if the value is present.
- documents_provided_by: Documents provided by - Name of organization/person who provided documents (e.g., "NA" or "HSBC")
- documents_description: Description - Description of documents provided (e.g., "NA" or description)

VALUER'S COMMENTS:
This appears as a bold header "VALUER'S COMMENTS" within subsection 2.4. It contains detailed comments from the valuer:
- valuer_comments: Detailed valuer's comments with bullet points covering all aspects of the valuation. This is a comprehensive text that should include:
  • Property description and type (e.g., "The subject property is a residential independent house.")
  • Land area as per documents (e.g., "As per the copy of sale deed provided by HSBC, the land area for the subject property was identified as 150 sq yd or 1,350 sft...")
  • Built-up area consideration (e.g., "As mentioned earlier built-up area as per the copy of gram panchayat plan i.e., 3,621 sft has been considered.")
  • Valuation methodology (comparables or land and building method) (e.g., "Based on our discussions with local estate agents... the 'land and building' method has been adopted...")
  • Amenities and additional features (e.g., "On visual inspection, the subject building was observed to have additional amenities such as sump, MS gates, etc...")
  • Plot dimensions and boundary discrepancies if any
  • Property identification method
  • Deviations (unit, vertical, etc.) (e.g., "Unit Deviation – No", "Vertical Deviation - No")
  • Protected/regulated area status (e.g., "Property within 100m in all directions of protected monument / protected area (Prohibited area): No")
  • Expected future physical life (e.g., "The expected future physical life of the subject property (if applicable) is based on visual inspection.")
  • Assumptions about title and approvals (e.g., "For the purpose of this value assessment, we have assumed that the subject property has a clear title and all necessary approvals and permissions have been duly obtained.")

2.5 Replacement Value:
This subsection appears as a gray header "2.5 Replacement Value" under "VALUATION ANALYSIS". It contains replacement cost information:
- construction_cost_per_sft: Construction Cost per sft - Cost to construct per square foot in INR. CRITICAL: Search thoroughly using terms like "Construction Cost", "Building Cost", "Cost per sft", "Construction Rate", "Replacement Cost per sft", "Rebuilding Cost per sft", "Construction Rate per sft", "Cost per square foot". Extract the exact value (e.g., "2,000" or "2,340"). If this value exists in documents, you MUST extract it.
- construction_cost_type: Type - Type of area for construction cost (e.g., "Built Up Area")
- replacement_value_inr: Replacement Value of Property (INR) - Total replacement cost of the property in Indian Rupees. CRITICAL: Search thoroughly using terms like "Replacement Value", "Replacement Cost", "Reconstruction Cost", "Rebuilding Cost", "Total Replacement Value", "Replacement Value Total". Extract the exact amount (e.g., "6,638,500" or "3,208,920" with "as on Date of Valuation"). If this value exists in documents, you MUST extract it.

2.6 Valuer's Declaration:
This subsection appears as a gray header "2.6 Valuer's Declaration" under "VALUATION ANALYSIS". It contains the valuer's official declaration:
- valuer_declaration: Valuer's declaration text - Official declaration statement from the valuer. Format: "I confirm that the market value for the subject property as on [date] is INR [amount]/- [amount in words] and the value of amenities as on [date] is INR [amount]/- [amount in words] taking into consideration the market dynamics and the condition of the property, its location, and amenities available." (e.g., "I confirm that the market value for the subject property as on 26-Jun-2025 is INR 16,642,800/- [Sixteen Million Six Hundred and Forty-Two Thousand Eight Hundred Rupees] and the value of amenities as on 26-Jun-2025 is INR 1,200,000/- [One Million Two Hundred Thousand Rupees] taking into consideration the market dynamics and the condition of the property, its location, and amenities available.")

2.7 Disclaimer:
This subsection appears as a gray header "2.7 Disclaimer" under "VALUATION ANALYSIS". It contains the standard disclaimer:
- disclaimer_text: Disclaimer text - Standard disclaimer statement. Format: "Please note that the above is a valuation and not a structural survey. CBRE is not responsible to HSBC or the purchaser of the above property for any flaws and/or faults with the property not detected by the above Valuer." (Extract exactly as shown in documents or use this standard text)

Valuer Information:
This information appears at the end of subsection 2.6, showing the valuer's credentials:
- valuer_code: Valuer Code - Unique code identifying the valuer (e.g., "HYDVAL-12" or "VAL-001" or "VALCODE-123")

===============================================================================
ANNEXURE
===============================================================================
This section appears after Section 2 with a gray header "ANNEXURE". It contains a table listing all documents provided for the valuation:
- documents_list: Document entries – create one entry for every document category listed below. Each entry must contain:
  - document_name: Exact document title as stated in the supporting material.
  - provided: "Yes", "No", or "NA" depending on availability.
  - remarks: Brief notes such as permission numbers, dates, application numbers, owner names, or "NA" when no remark exists.

Populate entries for the following categories (use the exact wording found in the documents whenever possible):
- Property address – confirm whether a formal document specifying the property address was provided; note any reference numbers or citations tied to the address proof.
- Address (and contact details) of contact person – indicate if the contact person’s address/phone/email details were submitted; add any job title or relationship if mentioned.
- Land area (sft) – state whether verified land-area documentation exists and mention the area in sq. ft./sq. yd. where available.
- Type of Area (e.g., Built Up Area) – specify the area classification (carpet/built-up/super built-up/land); include both document-based and site-based descriptions when provided.
- Approved plans (including applicable FAR, ground coverage, setbacks, etc.) – record whether sanctioned plans were furnished and reference permission numbers, approval dates, issuing authority, and any stated FAR/setback data.
- Society registration certificate – indicate availability of the society/association registration document; list registration number or issuing authority if known.
- Completion certificate – confirm whether a formal completion certificate was received; note issuance date/authority if applicable.
- Occupation certificate – state whether an occupation/occupancy certificate exists; note issuing authority and date when provided.
- ULC clearance – specify availability of Urban Land Ceiling clearance or exemption orders; mention order numbers/dates where documented.
- Copy of share certificate – report whether a share certificate (for co-operative societies/apartments) was provided; reference certificate number if present.
- Copy of conveyance deed / sale deed / sale agreement – confirm submission of conveyance/sale documentation; include document number, registration office, date, and grantee/grantor names when available.
- Construction permission / commencement certificate – state whether construction permission/commencement approvals were furnished; capture permission number, date, issuing authority, and any conditions if noted.
- Property Tax Receipt – note submission of current property tax receipts; mention application/receipt numbers, billing period, owner name, and property identification numbers where stated.
- Land Use Information (Proceedings Letter) – record availability of land-use conversion/regularisation letters; include proceeding number, date, issuing authority, and the land-use classification granted.

===============================================================================
IMPORTANT INSTRUCTIONS - READ CAREFULLY:
===============================================================================
1. ACCURACY FIRST: Extract ALL information that is CLEARLY visible in the provided documents/images - BE THOROUGH
2. EXTRACT ALL VALUES: If a value exists in the documents, you MUST extract it. Do NOT default to "NA" if the information is present
3. DO NOT INVENT: If a field is genuinely not found after thorough search, use "NA" (for numbers) or "N/A" (for text) - DO NOT make up values
4. EXACT VALUES: Copy values exactly as they appear in documents (preserve commas, formatting)
5. REQUIRED FORMAT: Return ALL fields listed above, even if value is "NA" or "N/A"
6. DATE FORMAT: Extract dates as shown or convert to readable format (e.g., "August 21, 2025")
7. SEARCH MULTIPLE TERMS: For each field, search using various terms and synonyms. Don't give up after finding one term - check all variations
8. GPS COORDINATES - CRITICAL RULE: Extract GPS coordinates ONLY from written text in property documents (PDF/TXT files), NOT from images, maps, or visual content. Search the EXTRACTED TEXT from documents for explicit mentions. If coordinates are not found as written text in documents, return "NA". Format as shown in documents (e.g., "12º 34' 56.789\" N" or decimal format). DO NOT extract from images even if coordinates are visible.
9. ARRAYS: For amenities and comparables, provide proper JSON arrays - use [] if no data found
10. COMMENTS: For valuer_comments, area_comments, etc., extract from documents or use "NA" if not found
11. JSON ONLY: Return valid JSON only - no markdown code blocks, no explanations before/after JSON
12. NUMBER FORMAT: Format numbers with commas for readability (e.g., "1,496" not "1496")
13. ORDER: Maintain the exact order of sections as shown above
14. VALIDATION: Before returning, verify all required fields are present in the JSON

EXAMPLE OUTPUT STRUCTURE:
{
  "property_reference_number": "TRACKER123456789",  // Extract from "tracker" or "tracker number" in documents
  "date_of_valuation": "August 21, 2025",
  "buyer_name": "John Doe",  // Extract from "Vendee" or "Purchaser" or "Buyer" in documents
  "seller_name": "Jane Smith",  // Extract from "Vendor" or "Seller" in documents
  "contact_person": "John Doe",
  "contact_number": "+91-XXXXXXXXXX",
  "address_1": "House on Plot No. 123",
  ...
  // ALL fields must be present, use "NA" or "N/A" if not found
}

Return ONLY the JSON object, no markdown, no code blocks, no explanations.
"""
