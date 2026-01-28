"""
Database comparables functionality - finds similar properties from database.
Uses pincode and location (locality/sub_locality) as primary matching parameters.
Also considers: land_area_sft, actual_area_sft, year_of_construction, bedrooms (BHK).
"""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
import re

DB_PATH = Path(__file__).parent / "property_valuations.db"


def _extract_numeric(value: Optional[str]) -> Optional[float]:
    """Extract numeric value from string (e.g., '1200 sq.ft' -> 1200.0)."""
    if not value:
        return None
    # Remove commas and extract first number
    cleaned = re.sub(r'[,\s]', '', str(value))
    match = re.search(r'(\d+\.?\d*)', cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def _lower(text: Optional[str]) -> str:
    """Convert to lowercase safely."""
    return text.lower() if isinstance(text, str) else ""


def _score_property_similarity(subject: Dict, candidate: Dict) -> float:
    """
    Score how similar a candidate property is to the subject property.
    PRIMARY MATCHING: Pincode and Location (locality/sub_locality)
    SECONDARY MATCHING: land_area_sft, actual_area_sft, year_of_construction, bedrooms (BHK).
    Returns a score (higher = more similar).
    """
    score = 0.0
    
    # 1. PINCODE MATCH (HIGHEST PRIORITY - 60 points)
    subject_pincode = str(subject.get("pin_code", "")).strip()
    candidate_pincode = str(candidate.get("pin_code", "")).strip()
    if subject_pincode and candidate_pincode and subject_pincode not in {"", "NA", "N/A"} and candidate_pincode not in {"", "NA", "N/A"}:
        if subject_pincode == candidate_pincode:
            score += 60.0  # Exact pincode match - highest priority
            print(f"[Scoring] ✅ Exact pincode match: {subject_pincode}")
        else:
            # Partial pincode match (first few digits match)
            if len(subject_pincode) >= 3 and len(candidate_pincode) >= 3:
                if subject_pincode[:3] == candidate_pincode[:3]:
                    score += 40.0  # Same area code
                    print(f"[Scoring] ⚠️ Partial pincode match: {subject_pincode[:3]}...")
    
    # 2. LOCATION MATCH (Locality + Sub-locality) - HIGH PRIORITY (50 points)
    subject_locality = _lower(subject.get("locality", ""))
    candidate_locality = _lower(candidate.get("locality", ""))
    subject_sub_locality = _lower(subject.get("sub_locality", ""))
    candidate_sub_locality = _lower(candidate.get("sub_locality", ""))
    
    # Check locality match
    if subject_locality and candidate_locality:
        if subject_locality == candidate_locality:
            score += 30.0  # Exact locality match
            print(f"[Scoring] ✅ Exact locality match: {subject_locality}")
        elif subject_locality in candidate_locality or candidate_locality in subject_locality:
            score += 20.0  # Partial locality match
            print(f"[Scoring] ⚠️ Partial locality match: {subject_locality} / {candidate_locality}")
    
    # Check sub-locality match
    if subject_sub_locality and candidate_sub_locality:
        if subject_sub_locality == candidate_sub_locality:
            score += 20.0  # Exact sub-locality match
            print(f"[Scoring] ✅ Exact sub-locality match: {subject_sub_locality}")
        elif subject_sub_locality in candidate_sub_locality or candidate_sub_locality in subject_sub_locality:
            score += 10.0  # Partial sub-locality match
            print(f"[Scoring] ⚠️ Partial sub-locality match: {subject_sub_locality} / {candidate_sub_locality}")
    
    # 3. City match (medium weight - 20 points) - for additional context
    subject_city = _lower(subject.get("city", ""))
    candidate_city = _lower(candidate.get("city", ""))
    if subject_city and candidate_city:
        if subject_city == candidate_city:
            score += 20.0  # Strong city match
        elif subject_city in candidate_city or candidate_city in subject_city:
            score += 10.0  # Partial city match
    
    # Check if we have location match (pincode or locality)
    has_location_match = False
    if (subject_pincode and candidate_pincode and subject_pincode not in {"", "NA", "N/A"} and 
        candidate_pincode not in {"", "NA", "N/A"} and subject_pincode == candidate_pincode):
        has_location_match = True
    if (subject_locality and candidate_locality and 
        (subject_locality == candidate_locality or subject_locality in candidate_locality or candidate_locality in subject_locality)):
        has_location_match = True
    
    # 4. Land Area similarity - HIGHER WEIGHT if no location match (alternative matching)
    subject_land_area = _extract_numeric(subject.get("land_area_sft", ""))
    candidate_land_area = _extract_numeric(candidate.get("land_area_sft", ""))
    if subject_land_area and candidate_land_area and subject_land_area > 0:
        area_diff = abs(subject_land_area - candidate_land_area) / subject_land_area
        if not has_location_match:
            # If no location match, give higher weight to area matching (alternative matching)
            if area_diff < 0.1:  # Within 10%
                score += 40.0  # Increased from 20
            elif area_diff < 0.25:  # Within 25%
                score += 30.0  # Increased from 15
            elif area_diff < 0.5:  # Within 50%
                score += 20.0  # Increased from 10
            elif area_diff < 1.0:  # Within 100%
                score += 10.0  # Increased from 5
        else:
            # Normal weight if location matches
            if area_diff < 0.1:  # Within 10%
                score += 20.0
            elif area_diff < 0.25:  # Within 25%
                score += 15.0
            elif area_diff < 0.5:  # Within 50%
                score += 10.0
            elif area_diff < 1.0:  # Within 100%
                score += 5.0
    
    # 5. Actual Area similarity - HIGHER WEIGHT if no location match (alternative matching)
    subject_actual_area = _extract_numeric(subject.get("actual_area_sft", ""))
    candidate_actual_area = _extract_numeric(candidate.get("actual_area_sft", ""))
    if subject_actual_area and candidate_actual_area and subject_actual_area > 0:
        area_diff = abs(subject_actual_area - candidate_actual_area) / subject_actual_area
        if not has_location_match:
            # If no location match, give higher weight to area matching (alternative matching)
            if area_diff < 0.1:  # Within 10%
                score += 40.0  # Increased from 20
            elif area_diff < 0.25:  # Within 25%
                score += 30.0  # Increased from 15
            elif area_diff < 0.5:  # Within 50%
                score += 20.0  # Increased from 10
            elif area_diff < 1.0:  # Within 100%
                score += 10.0  # Increased from 5
        else:
            # Normal weight if location matches
            if area_diff < 0.1:  # Within 10%
                score += 20.0
            elif area_diff < 0.25:  # Within 25%
                score += 15.0
            elif area_diff < 0.5:  # Within 50%
                score += 10.0
            elif area_diff < 1.0:  # Within 100%
                score += 5.0
    
    # 6. Year of construction similarity (medium weight - 15 points)
    subject_year = subject.get("year_of_construction", "")
    candidate_year = candidate.get("year_of_construction", "")
    if subject_year and candidate_year:
        try:
            subj_year_match = re.search(r'\d{4}', str(subject_year))
            cand_year_match = re.search(r'\d{4}', str(candidate_year))
            if subj_year_match and cand_year_match:
                subj_year = int(subj_year_match.group())
                cand_year = int(cand_year_match.group())
                year_diff = abs(subj_year - cand_year)
                if year_diff == 0:
                    score += 15.0  # Same year
                elif year_diff <= 2:
                    score += 10.0  # Within 2 years
                elif year_diff <= 5:
                    score += 7.0  # Within 5 years
                elif year_diff <= 10:
                    score += 3.0  # Within 10 years
        except (ValueError, AttributeError):
            pass
    
    # 7. Bedrooms (BHK) match - HIGHER WEIGHT if no location match (alternative matching)
    subject_bedrooms = _extract_numeric(subject.get("bedrooms", ""))
    candidate_bedrooms = _extract_numeric(candidate.get("bedrooms", ""))
    if subject_bedrooms and candidate_bedrooms:
        if not has_location_match:
            # If no location match, give higher weight to bedrooms matching (alternative matching)
            if subject_bedrooms == candidate_bedrooms:
                score += 35.0  # Increased from 15
            elif abs(subject_bedrooms - candidate_bedrooms) == 1:
                score += 20.0  # Increased from 8
            elif abs(subject_bedrooms - candidate_bedrooms) == 2:
                score += 10.0  # Increased from 3
        else:
            # Normal weight if location matches
            if subject_bedrooms == candidate_bedrooms:
                score += 15.0  # Exact match
            elif abs(subject_bedrooms - candidate_bedrooms) == 1:
                score += 8.0  # Within 1 bedroom
            elif abs(subject_bedrooms - candidate_bedrooms) == 2:
                score += 3.0  # Within 2 bedrooms
    
    # Ensure minimum score if we have any matching data (to avoid returning empty)
    # This ensures we always return properties even with low scores
    if score == 0.0:
        # Give a small base score if we have at least some data
        if (subject_land_area or subject_actual_area or subject_bedrooms or 
            subject_pincode not in {"", "NA", "N/A"} or subject_locality):
            score = 1.0  # Minimum score to ensure property is considered
    
    return score


def find_similar_properties_from_db(subject_structured: Dict, exclude_property_id: Optional[int] = None, limit: int = 2) -> List[Dict]:
    """
    Find similar properties from the database based on comparison parameters.
    
    PRIMARY MATCHING PARAMETERS (highest priority):
    - Pincode 
    - Location: Locality + Sub-locality 
    
    SECONDARY MATCHING PARAMETERS:
    - Land Area (sft)
    - Actual Area (sft)
    - Year of Construction
    - Bedrooms (BHK)
    - City (for additional context)
    
    Parameters:
    - subject_structured: The current property's structured data
    - exclude_property_id: Property ID to exclude (current property)
    - limit: Maximum number of comparables to return
    
    Returns:
    - List of comparable property dictionaries in comparable format
    """
    if not DB_PATH.exists():
        return []
    
    try:
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        subject_pincode = subject_structured.get("pin_code", "N/A")
        subject_locality = subject_structured.get("locality", "N/A")
        subject_sub_locality = subject_structured.get("sub_locality", "N/A")
        print(f"[DB Comparables] Searching for comparables using PRIMARY: Pincode={subject_pincode}, Location={subject_locality}/{subject_sub_locality}")
        print(f"[DB Comparables] Secondary parameters: Land Area, Actual Area, Year, Bedrooms")
        
        # Get all properties except the current one, including construction details for bedrooms
        # Note: land_area_sft is in property table, not property_area_details
        # Note: date_of_transaction is NOT in property table - it will be "NA" for Comparable #2
        # (date_of_transaction is only stored in comparables table for comparables extracted from documents)
        if exclude_property_id:
            cur.execute("""
                SELECT p.*, 
                       pad.actual_area_sft, pad.area_adopted_for_valuation_sft,
                       pad.area_adopted_type,
                       pcd.bedrooms
                FROM property p
                LEFT JOIN property_area_details pad ON p.property_id = pad.property_id
                LEFT JOIN property_construction_details pcd ON p.property_id = pcd.property_id
                WHERE p.property_id != ?
                ORDER BY p.created_at DESC
            """, (exclude_property_id,))
        else:
            cur.execute("""
                SELECT p.*, 
                       pad.actual_area_sft, pad.area_adopted_for_valuation_sft,
                       pad.area_adopted_type,
                       pcd.bedrooms
                FROM property p
                LEFT JOIN property_area_details pad ON p.property_id = pad.property_id
                LEFT JOIN property_construction_details pcd ON p.property_id = pcd.property_id
                ORDER BY p.created_at DESC
            """)
        
        all_rows = cur.fetchall()
        print(f"[DB Comparables] Found {len(all_rows)} properties in database (excluding property_id={exclude_property_id})")
        
        if len(all_rows) == 0:
            print(f"[DB Comparables] ⚠️ No properties found in database (excluding current property)")
            con.close()
            return []
        
        candidates = []
        for row in all_rows:
            candidate = dict(row)
            
            # Calculate similarity score (PRIMARY: pincode + location, SECONDARY: area, year, bedrooms)
            score = _score_property_similarity(subject_structured, candidate)
            candidate['_similarity_score'] = score
            candidates.append(candidate)
            
            # Log detailed scoring with emphasis on pincode and location
            print(f"[DB Comparables] Property ID {candidate.get('property_id')}:")
            print(f"   - Score: {score:.1f}")
            print(f"   - Pincode: {candidate.get('pin_code', 'N/A')} (Subject: {subject_structured.get('pin_code', 'N/A')})")
            print(f"   - Location: {candidate.get('locality', 'N/A')} / {candidate.get('sub_locality', 'N/A')}")
            print(f"   - City: {candidate.get('city', 'N/A')}")
            print(f"   - Land Area: {candidate.get('land_area_sft', 'N/A')}")
            print(f"   - Actual Area: {candidate.get('actual_area_sft', 'N/A')}")
            print(f"   - Year: {candidate.get('year_of_construction', 'N/A')}")
            print(f"   - Bedrooms: {candidate.get('bedrooms', 'N/A')}")
        
        # Sort by similarity score (highest first)
        candidates.sort(key=lambda x: x.get('_similarity_score', 0), reverse=True)
        
        # CRITICAL: Always return properties if they exist in database
        # Even if scores are low, it's better to show comparables than "NA"
        if len(candidates) > 0:
            # Take top N candidates (best matches)
            # IMPORTANT: Return ALL candidates up to limit, regardless of score
            # This ensures we always have comparables if properties exist
            top_candidates = candidates[:limit]
            print(f"[DB Comparables] ✅ Selected {len(top_candidates)} top candidates from {len(candidates)} total candidates")
            
            # Show scores for selected candidates with matching details
            for idx, cand in enumerate(top_candidates, 1):
                score = cand.get('_similarity_score', 0)
                prop_id = cand.get('property_id', 'N/A')
                city = cand.get('city', 'N/A')
                locality = cand.get('locality', 'N/A')
                pincode = cand.get('pin_code', 'N/A')
                area = cand.get('land_area_sft') or cand.get('actual_area_sft', 'N/A')
                bedrooms = cand.get('bedrooms', 'N/A')
                print(f"[DB Comparables]   ✅ Selected #{idx}: Property ID {prop_id}")
                print(f"      - Score: {score:.1f}")
                print(f"      - Location: {locality} (Pincode: {pincode})")
                print(f"      - Area: {area} sft, Bedrooms: {bedrooms}")
                
                # Determine match type
                if score >= 60:
                    print(f"      - Match Type: Location-based (Pincode/Locality match)")
                elif score >= 40:
                    print(f"      - Match Type: Area/Bedrooms-based (Alternative matching)")
                else:
                    print(f"      - Match Type: General match (Best available)")
        else:
            # No candidates found - this should not happen if properties exist
            top_candidates = []
            print(f"[DB Comparables] ⚠️ WARNING: No candidates found despite {len(all_rows)} properties in database")
            print(f"[DB Comparables] ⚠️ This means all properties were filtered out or scoring failed")
            con.close()
            return []
        
        # CRITICAL CHECK: If we have candidates but no top_candidates, something is wrong
        if len(candidates) > 0 and len(top_candidates) == 0:
            print(f"[DB Comparables] ⚠️ ERROR: Have {len(candidates)} candidates but top_candidates is empty!")
            con.close()
            return []
        
        # Convert to comparable format
        comparables = []
        for candidate in top_candidates:
            # Calculate price per sqft if possible
            price_per_sft = "NA"
            total_value = candidate.get("total_value_inr", "NA")
            area = candidate.get("actual_area_sft") or candidate.get("land_area_sft") or candidate.get("area_adopted_for_valuation_sft", "NA")
            
            if total_value and str(total_value).strip() not in {"", "NA", "N/A"} and area and str(area).strip() not in {"", "NA", "N/A"}:
                try:
                    price_val = _extract_numeric(str(total_value))
                    area_val = _extract_numeric(str(area))
                    if price_val and area_val and area_val > 0:
                        price_per_sft = str(int(price_val / area_val))
                except:
                    pass
            
            # Get property_id for source information
            prop_id = candidate.get("property_id", "N/A")
            similarity_score = candidate.get("_similarity_score", 0)
            
            # Helper to safely get value or "NA" - ensures all empty/None/null values become "NA"
            # Handles "None None" patterns as well
            def safe_get(d, key, default="NA"):
                val = d.get(key)
                if val is None:
                    return default
                val_str = str(val).strip()
                if val_str == "":
                    return default
                val_lower = val_str.lower()
                # Check for single None/null/n/a
                if val_lower in {"null", "none", "n/a", "na"}:
                    return default
                # Check for "None None" or similar patterns (e.g., "None None", "null null")
                if val_lower.replace(" ", "") in {"nonenone", "nullnull", "nana", "n/an/a"}:
                    return default
                # Check if value contains only None/null/na words (e.g., "None None", "null null null")
                if all(word.lower() in {"none", "null", "na", "n/a"} for word in val_str.split() if word.strip()):
                    return default
                return val_str
            
            # Calculate land price per sqft if land area and total value available
            land_price_per_sft = "NA"
            land_area = safe_get(candidate, "land_area_sft")
            if land_area and land_area != "NA" and total_value and total_value != "NA":
                try:
                    land_area_val = _extract_numeric(str(land_area))
                    total_val = _extract_numeric(str(total_value))
                    if land_area_val and total_val and land_area_val > 0:
                        # For land price, we use total value as approximation
                        # In practice, land price might be separate, but we use total value as fallback
                        land_price_per_sft = str(int(total_val / land_area_val))
                except:
                    pass
            
            # Calculate land-only transaction price (approximation)
            # If we have land area and built-up area, we can estimate land value
            approx_transaction_price_land_inr = "NA"
            built_up_area = safe_get(candidate, "actual_area_sft")
            if land_area and land_area != "NA" and built_up_area and built_up_area != "NA" and total_value and total_value != "NA":
                try:
                    land_area_val = _extract_numeric(str(land_area))
                    built_up_val = _extract_numeric(str(built_up_area))
                    total_val = _extract_numeric(str(total_value))
                    if land_area_val and built_up_val and total_val and built_up_val > 0:
                        # Estimate land value based on land area proportion
                        # This is an approximation - actual land value might be different
                        land_price_estimate = int((land_area_val / built_up_val) * total_val)
                        approx_transaction_price_land_inr = str(land_price_estimate)
                except:
                    pass
            
            # Build comparable with proper field mapping based on field descriptions
            comparable = {
                # Address fields (1-4): Breakdown of property address
                # Address 1: Property type (e.g., House, Apartment, Plot)
                "address_1": safe_get(candidate, "address_1"),
                # Address 2: Building/Society/Project name (e.g., R R Homes)
                "address_2": safe_get(candidate, "address_2"),
                # Address 3: Area or village (e.g., Ameenpur Village)
                "address_3": safe_get(candidate, "address_3"),
                # Address 4: Municipality or administrative division
                "address_4": safe_get(candidate, "address_4"),
                # Building Name: Apartment/gated community name (if applicable, else NA)
                "building_name": safe_get(candidate, "building_name"),
                # Sub-Locality: Smaller region inside locality (e.g., Ameenpur Mandal)
                "sub_locality": safe_get(candidate, "sub_locality"),
                # Locality: Broader area or neighbourhood (e.g., Sangareddy District)
                "locality": safe_get(candidate, "locality"),
                # City: City where property is located
                "city": safe_get(candidate, "city"),
                # Pin Code: Postal area code
                "pin_code": safe_get(candidate, "pin_code"),
                # Date of Transaction: When property was sold OR when quoted price was provided
                # Use date_of_transaction from comparables table if available, otherwise "NA"
                # Do NOT use date_of_valuation - it's the valuation date, not transaction date
                "date_of_transaction": safe_get(candidate, "date_of_transaction") or "NA",
                "transaction_type": "Comparable Property",
                # Approx. Area of Property (sft): Built-up area of the house or building
                "approx_area_sft": safe_get(candidate, "actual_area_sft") if not area or area == "NA" else area,
                "area_type": safe_get(candidate, "area_adopted_type"),
                # Land Area of Property (sft): Total land plot area (for independent house)
                "land_area_sft": safe_get(candidate, "land_area_sft"),
                # Approx. Transaction Price (INR): Estimated sale/quoted price (built-up)
                "approx_transaction_price_inr": safe_get(candidate, "total_value_inr") if not total_value or total_value == "NA" else total_value,
                # Approx. Transaction Price (Land): Estimated land-only value
                "approx_transaction_price_land_inr": approx_transaction_price_land_inr,
                # Transaction Price per sq. ft (INR): Built-up price per square foot
                # Formula: Built-Up Price / Built-Up Area
                "transaction_price_per_sft_inr": price_per_sft,
                # Transaction Price per sq. ft (Land): Land price per square foot
                # Formula: Land Price / Land Area
                "transaction_price_per_sft_land_inr": land_price_per_sft,
                # Source of Information: Where comparable price was obtained from
                # Examples: Local real estate agent, Market enquiries, Online listings, Recent sale deeds
                "source_of_information": f"Database Property ID: {prop_id} (Similarity Score: {similarity_score:.1f}) - Market comparable from property database",
            }
            comparables.append(comparable)
            print(f"[DB Comparables] ✅ Added comparable: Property ID {prop_id}")
            print(f"   - City: {comparable.get('city')}, Locality: {comparable.get('locality')}")
            print(f"   - Address: {comparable.get('address_1')}")
            print(f"   - Area: {comparable.get('approx_area_sft')}, Price: {comparable.get('approx_transaction_price_inr')}")
        
        print(f"[DB Comparables] ✅ Returning {len(comparables)} comparables to merge into report")
        if len(comparables) > 0:
            print(f"[DB Comparables] First comparable preview: City={comparables[0].get('city')}, Locality={comparables[0].get('locality')}, Address={comparables[0].get('address_1')}")
        con.close()
        return comparables
        
    except Exception as e:
        print(f"[DB Comparables] Error finding similar properties: {e}")
        return []


def get_property_count() -> int:
    """Get total number of properties in database."""
    if not DB_PATH.exists():
        return 0
    
    try:
        con = sqlite3.connect(str(DB_PATH))
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM property")
        count = cur.fetchone()[0]
        con.close()
        return count
    except:
        return 0

