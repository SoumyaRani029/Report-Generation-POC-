"""
Comparables merging functionality.
Generates PDF-compatible comparable fields with _comparable_1 and _comparable_2 suffixes.

Comparable #1 = Subject property 
Comparable #2 = Best matching property from database based on Comparable #1's parameters
"""
from typing import Dict, List


def _convert_subject_to_comparable(subject_structured: Dict) -> Dict:
    """
    Convert the subject property (input property) into Comparable #1 format.
    
    Field Descriptions:
    - Address 1-4: Breakdown of property address (Property type, Building name, Area/village, Municipality)
    - Building Name: Apartment/gated community name (if applicable, else NA)
    - Sub-Locality: Smaller region inside locality (e.g., Ameenpur Mandal)
    - Locality: Broader area or neighbourhood (e.g., Sangareddy District)
    - City: City where property is located
    - Pin Code: Postal area code
    - Date of Transaction: When property was sold or quoted price was provided
    - Approx. Area of Property (sft): Built-up area of the house or building
    - Land Area of Property (sft): Total land plot area (for independent house)
    - Approx. Transaction Price (INR): Estimated sale/quoted price (built-up)
    - Approx. Transaction Price (Land): Estimated land-only value
    - Transaction Price per sq. ft (INR): Built-up price per square foot (Built-Up Price / Built-Up Area)
    - Transaction Price per sq. ft (Land): Land price per square foot (Land Price / Land Area)
    - Source of Information: Where comparable price was obtained from
    
    Args:
        subject_structured: The subject property's structured data from LLM extraction
    
    Returns:
        Dict with all comparable fields filled from subject property
    """
    # Calculate built-up price per sqft if area and price are available
    price_per_sft = "NA"
    total_value = subject_structured.get("total_value_inr", "NA")
    built_up_area = subject_structured.get("actual_area_sft") or "NA"
    land_area = subject_structured.get("land_area_sft", "NA")
    
    if total_value and str(total_value).strip() not in {"", "NA", "N/A"} and built_up_area and str(built_up_area).strip() not in {"", "NA", "N/A"}:
        try:
            # Helper to extract numeric value
            def extract_numeric(val_str):
                if not val_str:
                    return None
                val_str = str(val_str).strip().replace(",", "").replace(" ", "")
                # Remove currency symbols and text
                import re
                numbers = re.findall(r'\d+', val_str)
                if numbers:
                    return float(''.join(numbers))
                return None
            
            price_val = extract_numeric(str(total_value))
            area_val = extract_numeric(str(built_up_area))
            if price_val and area_val and area_val > 0:
                # Transaction Price per sq. ft (INR): Built-up price per square foot
                # Formula: Built-Up Price / Built-Up Area
                price_per_sft = str(int(price_val / area_val))
        except:
            pass
    
    # Calculate land price per sqft if land area available
    land_price_per_sft = "NA"
    approx_transaction_price_land_inr = "NA"
    if land_area and land_area != "NA" and total_value and total_value != "NA":
        try:
            def extract_numeric(val_str):
                if not val_str:
                    return None
                val_str = str(val_str).strip().replace(",", "").replace(" ", "")
                import re
                numbers = re.findall(r'\d+', val_str)
                if numbers:
                    return float(''.join(numbers))
                return None
            
            land_area_val = extract_numeric(str(land_area))
            built_up_val = extract_numeric(str(built_up_area)) if built_up_area != "NA" else None
            total_val = extract_numeric(str(total_value))
            
            if land_area_val and total_val and land_area_val > 0:
                # Approximate land value (if we have both land and built-up, estimate proportion)
                if built_up_val and built_up_val > 0:
                    # Estimate land value based on area proportion
                    land_price_estimate = int((land_area_val / built_up_val) * total_val)
                    approx_transaction_price_land_inr = str(land_price_estimate)
                    # Transaction Price per sq. ft (Land): Land price per square foot
                    # Formula: Land Price / Land Area
                    land_price_per_sft = str(int(land_price_estimate / land_area_val))
                else:
                    # If no built-up area, use total value as land value approximation
                    approx_transaction_price_land_inr = str(int(total_val))
                    land_price_per_sft = str(int(total_val / land_area_val))
        except:
            pass
    
    # Build comparable with proper field descriptions
    comparable = {
        # Address fields (1-4): Breakdown of property address
        # Address 1: Property type (e.g., House, Apartment, Plot)
        "address_1": subject_structured.get("address_1", "NA"),
        # Address 2: Building/Society/Project name (e.g., R R Homes)
        "address_2": subject_structured.get("address_2", "NA"),
        # Address 3: Area or village (e.g., Ameenpur Village)
        "address_3": subject_structured.get("address_3", "NA"),
        # Address 4: Municipality or administrative division
        "address_4": subject_structured.get("address_4", "NA"),
        # Building Name: Apartment/gated community name (if applicable, else NA)
        "building_name": subject_structured.get("building_name", "NA"),
        # Sub-Locality: Smaller region inside locality (e.g., Ameenpur Mandal)
        "sub_locality": subject_structured.get("sub_locality", "NA"),
        # Locality: Broader area or neighbourhood (e.g., Sangareddy District)
        "locality": subject_structured.get("locality", "NA"),
        # City: City where property is located
        "city": subject_structured.get("city", "NA"),
        # Pin Code: Postal area code
        "pin_code": subject_structured.get("pin_code", "NA"),
        # Date of Transaction: When property was sold OR when quoted price was provided
        # Use date_of_transaction from LLM extraction (sale/quote date)
        # Do NOT use date_of_valuation - it's the valuation date, not transaction date
        "date_of_transaction": subject_structured.get("date_of_transaction", "NA"),
        "transaction_type": "Subject Property",
        # Approx. Area of Property (sft): Built-up area of the house or building
        "approx_area_sft": built_up_area if built_up_area != "NA" else (subject_structured.get("actual_area_sft") or subject_structured.get("land_area_sft") or "NA"),
        "area_type": subject_structured.get("area_adopted_type", "NA"),
        # Land Area of Property (sft): Total land plot area (for independent house)
        "land_area_sft": land_area,
        # Approx. Transaction Price (INR): Estimated sale/quoted price (built-up)
        "approx_transaction_price_inr": total_value if total_value and total_value != "NA" else "NA",
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
        "source_of_information": "Subject Property Details - Current property being valued",
    }
    
    # Clean up values - ensure all empty/None/null values become "NA"
    # Handle cases like "None None", "null null", etc.
    for key, val in comparable.items():
        if val is None:
            comparable[key] = "NA"
        else:
            val_str = str(val).strip()
            if val_str == "":
                comparable[key] = "NA"
            else:
                val_lower = val_str.lower()
                # Check for single None/null/n/a
                if val_lower in {"null", "none", "n/a", "na"}:
                    comparable[key] = "NA"
                # Check for "None None" or similar patterns (e.g., "None None", "null null")
                elif val_lower.replace(" ", "") in {"nonenone", "nullnull", "nana", "n/an/a"}:
                    comparable[key] = "NA"
                # Check if value contains only None/null/na words (e.g., "None None", "null null null")
                elif all(word.lower() in {"none", "null", "na", "n/a"} for word in val_str.split() if word.strip()):
                    comparable[key] = "NA"
                else:
                    comparable[key] = val_str
    
    return comparable


def generate_pdf_comparables(comparables: List[Dict]) -> Dict:
    """
    Generate comparable fields exactly as required by the PDF template.
    
    Args:
        comparables: List of comparable property dicts from database.
                    Each dict should have all the fields needed for a comparable.
    
    Returns:
        Dict with fields named as: address_1_comparable_1, address_2_comparable_1, etc.
        For both comparable_1 and comparable_2.
    """
    # Fields mapped to PDF layout
    pdf_fields = [
        "address_1",
        "address_2",
        "address_3",
        "address_4",
        "building_name",
        "sub_locality",
        "locality",
        "city",
        "pin_code",
        "date_of_transaction",
        "approx_area_sft",
        "land_area_sft",
        "approx_transaction_price_inr",
        "approx_transaction_price_land_inr",
        "transaction_price_per_sft_inr",
        "transaction_price_per_sft_land_inr",
        "source_of_information"
    ]
    
    result = {}
    
    # Process comparable_1 and comparable_2
    for idx in range(1, 3):
        slot = idx - 1
        
        if slot < len(comparables) and comparables[slot]:
            comp_raw = comparables[slot]
            
            # Fill fields from comparable dict
            for key in pdf_fields:
                dest_key = f"{key}_comparable_{idx}"
                val = comp_raw.get(key, "NA")
                
                # Date of Transaction: When property was sold OR when quoted price was provided
                # Do NOT use date_of_valuation as fallback - it's the valuation date, not transaction date
                # If date_of_transaction is not available, keep as "NA"
                if key == "date_of_transaction" and (not val or val == "NA"):
                    # Try to get from alternative fields, but prefer "NA" over date_of_valuation
                    # Only use date_of_valuation if absolutely no transaction date exists
                    val = comp_raw.get("date_of_transaction") or "NA"
                
                # Clean up value - ensure all empty/None/null values become "NA"
                # Handle cases like "None None", "null null", etc.
                if val is None:
                    result[dest_key] = "NA"
                else:
                    val_str = str(val).strip()
                    if val_str == "":
                        result[dest_key] = "NA"
                    else:
                        val_lower = val_str.lower()
                        # Check for single None/null/n/a
                        if val_lower in {"null", "none", "n/a", "na"}:
                            result[dest_key] = "NA"
                        # Check for "None None" or similar patterns (e.g., "None None", "null null")
                        elif val_lower.replace(" ", "") in {"nonenone", "nullnull", "nana", "n/an/a"}:
                            result[dest_key] = "NA"
                        # Check if value contains only None/null/na words (e.g., "None None", "null null null")
                        elif all(word.lower() in {"none", "null", "na", "n/a"} for word in val_str.split() if word.strip()):
                            result[dest_key] = "NA"
                        else:
                            result[dest_key] = val_str
        else:
            # No comparable -> Fill NA for all fields
            for key in pdf_fields:
                result[f"{key}_comparable_{idx}"] = "NA"
    
    return result


def merge_comparables(subject_structured: Dict, housing_comps: List[Dict], source: str = "database") -> Dict:
    """
    Merge comparables into subject structured data.
    Generates PDF-compatible fields with _comparable_1 and _comparable_2 suffixes.
    
    LOGIC:
    - Comparable #1 = Subject property (input property being uploaded)
    - Comparable #2 = Best matching property from database based on Comparable #1's parameters
    
    Args:
        subject_structured: The subject property's structured data
        housing_comps: List of comparable properties (from database) - these are OTHER properties
        source: Source of comparables ("database" or "none")
    
    Returns:
        Dict with comparables added as:
        - comparables list (for backward compatibility with report builder)
        - address_1_comparable_1, address_2_comparable_1, etc. (PDF-compatible fields)
        - address_1_comparable_2, address_2_comparable_2, etc.
    """
    merged = dict(subject_structured)
    
    # Build final comparables list
    comparables = []
    
    # Comparable #1: ALWAYS the subject property (input property being uploaded)
    comp1 = _convert_subject_to_comparable(subject_structured)
    comparables.append(comp1)
    print(f"[Merge Comparables] ✅ Comparable #1 (Subject Property): {comp1.get('city', 'N/A')}, {comp1.get('locality', 'N/A')}")
    
    # Comparable #2: Best match from database based on Comparable #1's parameters
    if housing_comps and len(housing_comps) > 0:
        print(f"[Merge Comparables] Found {len(housing_comps)} matching property(ies) from database")
        # Use the best match from database as Comparable #2
        comp2 = housing_comps[0]  # Best match (already sorted by similarity score)
        comparables.append(comp2)
        print(f"[Merge Comparables] ✅ Comparable #2 (From Database): {comp2.get('city', 'N/A')}, {comp2.get('locality', 'N/A')}")
    else:
        # No matching properties found in database - Comparable #2 shows NA
        print(f"[Merge Comparables] No matching properties found in database - Comparable #2 will show NA")
        comparables.append({
            "address_1": "NA",
            "address_2": "NA",
            "address_3": "NA",
            "address_4": "NA",
            "building_name": "NA",
            "sub_locality": "NA",
            "locality": "NA",
            "city": "NA",
            "pin_code": "NA",
            "date_of_transaction": "NA",
            "transaction_type": "NA",
            "approx_area_sft": "NA",
            "area_type": "NA",
            "land_area_sft": "NA",
            "approx_transaction_price_inr": "NA",
            "approx_transaction_price_land_inr": "NA",
            "transaction_price_per_sft_inr": "NA",
            "transaction_price_per_sft_land_inr": "NA",
            "source_of_information": "NA",
        })

    # Ensure exactly 2 comparables
    comparables = comparables[:2]
    
    # Keep backward compatibility: add comparables list
    merged["comparables"] = comparables
    
    # Generate PDF-compatible fields with _comparable_1 and _comparable_2 suffixes
    pdf_comparable_fields = generate_pdf_comparables(comparables)
    merged.update(pdf_comparable_fields)
    
    print(f"[Merge Comparables] ✅ Generated PDF-compatible comparable fields")
    print(f"[Merge Comparables]   - Fields added: {len(pdf_comparable_fields)} fields")
    print(f"[Merge Comparables]   - Comparable #1 (Subject): {comparables[0].get('city', 'N/A')}, {comparables[0].get('locality', 'N/A')}")
    if len(comparables) > 1 and comparables[1].get("city") != "NA":
        print(f"[Merge Comparables]   - Comparable #2 (Database): {comparables[1].get('city', 'N/A')}, {comparables[1].get('locality', 'N/A')}")
    
    return merged

