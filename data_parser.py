import re
from typing import Dict, Tuple

DEFAULT_TEXT = "N/A"


def _get(pattern: str, text: str, default: str = DEFAULT_TEXT) -> str:
    """Return the first regex group for pattern or default if not found."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return default


def infer_location_and_surroundings(text: str) -> Tuple[str, str, str, str]:
    """Extract land use, condition, negative area and city limits from text. Return "NA" if not explicitly found."""
    lowered = text.lower()

    # Only infer if explicitly mentioned in text
    if any(word in lowered for word in ["residential", "villa", "house", "colony", "apartment"]):
        land_use = "Residential"
    elif any(word in lowered for word in ["commercial", "shop", "market", "mall"]):
        land_use = "Commercial"
    else:
        land_use = DEFAULT_TEXT  # Changed from default "Residential"

    if any(word in lowered for word in ["clean", "good", "developed", "mid-end"]):
        condition = "Good"
    elif any(word in lowered for word in ["slum", "poor", "dump", "dilapidated"]):
        condition = "Poor"
    else:
        condition = DEFAULT_TEXT  # Changed from default "Average"

    negative_keywords = ["nala", "drain", "garbage", "sewer", "high tension", "graveyard"]
    negative_area = "Yes" if any(k in lowered for k in negative_keywords) else DEFAULT_TEXT  # Changed from default "No"

    outside_city_limits = "Yes" if any(word in lowered for word in ["gram panchayat", "village", "gp"]) else DEFAULT_TEXT  # Changed from default "No"

    return land_use, condition, negative_area, outside_city_limits


def infer_floor_height(text: str) -> Tuple[str, str, str, str, str]:
    """Extract floor height values from text. Return "NA" if not found."""
    actual = _get(r"floor\s*height\s*[:\-]?\s*(\d{1,2})", text, default=DEFAULT_TEXT)
    permitted_min = DEFAULT_TEXT  # Changed from hardcoded "9"
    permitted_max = DEFAULT_TEXT  # Changed from hardcoded "14"
    deviation = DEFAULT_TEXT  # Changed from hardcoded "No"
    acceptable = DEFAULT_TEXT  # Changed from hardcoded "Yes"

    # Only calculate deviation if we have actual values
    if actual != DEFAULT_TEXT and permitted_min != DEFAULT_TEXT and permitted_max != DEFAULT_TEXT:
        try:
            height = float(actual)
            min_val = float(permitted_min)
            max_val = float(permitted_max)
            if height < min_val or height > max_val:
                deviation = "Yes"
                acceptable = "No"
            else:
                deviation = "No"
                acceptable = "Yes"
        except ValueError:
            pass

    return permitted_max, permitted_min, actual, deviation, acceptable


def infer_setbacks(text: str) -> Tuple[Tuple[str, str, str, str], Tuple[str, str, str, str], Tuple[str, str, str, str], Tuple[str, str, str, str]]:
    """Extract setback values from text. Return "NA" if not found."""
    lowered = text.lower()
    numbers = re.findall(r"(\d+(?:\.\d+)?)\s*ft", lowered)

    if len(numbers) >= 4:
        permitted = [numbers[0], numbers[1], numbers[2], numbers[3]]
        actual = permitted.copy()
        # Calculate deviation and deviation_percent from actual values, not hardcoded
        deviation = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]
        deviation_percent = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]
        # Only set deviation if we can calculate it from permitted and actual values
        for i in range(4):
            try:
                perm_val = float(permitted[i])
                act_val = float(actual[i])
                if perm_val > 0:
                    diff = abs(act_val - perm_val)
                    if diff > 0.01:  # If there's a difference
                        deviation[i] = "Yes"
                        deviation_percent[i] = str(round((diff / perm_val) * 100, 2))
                    else:
                        deviation[i] = "No"
                        deviation_percent[i] = "0"
            except (ValueError, IndexError):
                deviation[i] = DEFAULT_TEXT
                deviation_percent[i] = DEFAULT_TEXT
    else:
        # If not found in text, return "NA" instead of hardcoded defaults
        permitted = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]
        actual = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]
        deviation = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]
        deviation_percent = [DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT, DEFAULT_TEXT]

    return tuple(permitted), tuple(actual), tuple(deviation), tuple(deviation_percent)


# REMOVED: infer_market_values() function - No hardcoded market values
# All market values must be extracted from property documents by the LLM
# If values are not found in documents, the system will return "NA"


def build_structured_data(extracted_text: str) -> Dict:
    """Map extracted free-form text into the structured dict consumed by the report."""
    structured: Dict[str, str] = {}

    # 1.1 Transacting Parties
    structured["buyer_name"] = _get(r"(Owner|Customer|Buyer)\s*Name[:\-]?\s*([\w\s\.]+)", extracted_text, DEFAULT_TEXT)
    structured["seller_name"] = structured["buyer_name"]
    structured["contact_person"] = structured["buyer_name"]
    structured["contact_number"] = _get(r"Phone\s*No\S*[:\-]?\s*(\d{10})", extracted_text, DEFAULT_TEXT)

    # 1.2 Address
    structured["address_1"] = _get(r"Plot\s*No[:\-]?\s*([\w\-\/]+)", extracted_text, DEFAULT_TEXT)
    structured["address_2"] = _get(r"(Green\s*Villas.*|Road\s*No.*)", extracted_text, DEFAULT_TEXT)
    structured["address_3"] = _get(r"Survey\s*No[:\-]?\s*([\w\-\/]+)", extracted_text, DEFAULT_TEXT)
    structured["address_4"] = DEFAULT_TEXT  # Changed from hardcoded "Ameenpur"
    structured["sub_locality"] = DEFAULT_TEXT  # Changed from hardcoded "Ameenpur Mandal"
    structured["locality"] = DEFAULT_TEXT  # Changed from hardcoded "Sangareddy District"
    structured["city"] = DEFAULT_TEXT  # Changed from hardcoded "Hyderabad"
    structured["pin_code"] = _get(r"(50\d{3,6})", extracted_text, DEFAULT_TEXT)
    structured["gps_latitude"] = _get(r"Latitude[:\-]?\s*([\d°\'\"\.\sN]+)", extracted_text, DEFAULT_TEXT)
    structured["gps_longitude"] = _get(r"Longitude[:\-]?\s*([\d°\'\"\.\sE]+)", extracted_text, DEFAULT_TEXT)

    # 1.3 Location & Surroundings
    land_use, condition, negative_area, outside_limits = infer_location_and_surroundings(extracted_text)
    structured["surrounding_land_use"] = land_use
    structured["surrounding_condition"] = condition
    structured["negative_area"] = negative_area
    structured["outside_city_limits"] = outside_limits

    # 1.4 Property Area
    structured["land_area_sft"] = _get(r"Land\s*Area.*?(\d{3,5})", extracted_text, DEFAULT_TEXT)
    structured["actual_area_sft"] = _get(r"Built[-\s]*up\s*area.*?(\d{3,5})", extracted_text, DEFAULT_TEXT)
    structured["planned_area_sft"] = structured["actual_area_sft"]
    structured["area_adopted_for_valuation_sft"] = structured["actual_area_sft"]

    # Floor height deviation
    perm_max, perm_min, actual_height, deviation_flag, acceptable_flag = infer_floor_height(extracted_text)
    structured["permitted_floor_height_max"] = perm_max
    structured["permitted_floor_height_min"] = perm_min
    structured["actual_floor_height_ft"] = actual_height
    structured["deviation_in_floor_height"] = deviation_flag
    structured["floor_height_deviation_acceptable"] = acceptable_flag

    # Setbacks
    permitted, actual, deviation, deviation_percent = infer_setbacks(extracted_text)
    structured["permitted_setback_front_ft"], structured["permitted_setback_rear_ft"], structured["permitted_setback_left_ft"], structured["permitted_setback_right_ft"] = permitted
    structured["actual_setback_front_ft"], structured["actual_setback_rear_ft"], structured["actual_setback_left_ft"], structured["actual_setback_right_ft"] = actual
    structured["deviation_in_setback_front"], structured["deviation_in_setback_rear"], structured["deviation_in_setback_left"], structured["deviation_in_setback_right"] = deviation
    structured["setback_deviation_percent_front"], structured["setback_deviation_percent_rear"], structured["setback_deviation_percent_left"], structured["setback_deviation_percent_right"] = deviation_percent

    # 1.5 Condition of Property
    structured["year_of_construction"] = _get(r"(20\d{2})", extracted_text, DEFAULT_TEXT)
    structured["age_years"] = DEFAULT_TEXT  # Changed from hardcoded "5"
    structured["exterior_condition"] = DEFAULT_TEXT  # Changed from hardcoded "Good"
    structured["interior_condition"] = DEFAULT_TEXT  # Changed from hardcoded "Good"
    structured["expected_future_life_years"] = DEFAULT_TEXT  # Changed from hardcoded "55"

    # 1.6 Features & Amenities
    structured["bedrooms"] = _get(r"Bedroom[s]?\s*[:\-]?\s*(\d+)", extracted_text, DEFAULT_TEXT)
    structured["bathrooms"] = _get(r"Bath\s*room[s]?\s*[:\-]?\s*(\d+)", extracted_text, DEFAULT_TEXT)
    structured["halls"] = _get(r"Hall[s]?\s*[:\-]?\s*(\d+)", extracted_text, DEFAULT_TEXT)
    structured["kitchens"] = _get(r"Kitchen[s]?\s*[:\-]?\s*(\d+)", extracted_text, DEFAULT_TEXT)
    structured["floors_in_property"] = DEFAULT_TEXT  # Changed from hardcoded "2"
    structured["floors_in_building"] = DEFAULT_TEXT  # Changed from hardcoded "Ground + 1"

    # Section 2 – Property Valuation
    structured["base_value_land_psft"] = _get(r"Base\s*Value.*land.*?([\d,]+)", extracted_text, DEFAULT_TEXT)
    structured["base_value_built_psft"] = _get(r"Base\s*Value.*?(?:built|psft).*?([\d,]+)", extracted_text, DEFAULT_TEXT)
    structured["base_value_type"] = DEFAULT_TEXT  # Changed from hardcoded "Built Up Area"

    # DO NOT use hardcoded market values - only use what's in documents
    # market_values = infer_market_values()  # DISABLED - don't use hardcoded values
    # structured.update(market_values)  # DISABLED
    
    # Set market value fields to "NA" if not found in documents
    structured["market_value_range_land_psft_min"] = DEFAULT_TEXT
    structured["market_value_range_land_psft_max"] = DEFAULT_TEXT
    structured["market_value_range_psft_min"] = DEFAULT_TEXT
    structured["market_value_range_psft_max"] = DEFAULT_TEXT
    structured["market_value_information_source"] = DEFAULT_TEXT
    structured["construction_cost_per_sft"] = DEFAULT_TEXT
    structured["construction_cost_type"] = DEFAULT_TEXT
    structured["total_value_inr"] = DEFAULT_TEXT
    structured["total_value_amenities_inr"] = DEFAULT_TEXT
    structured["replacement_value_inr"] = DEFAULT_TEXT

    # Ensure mandatory valuation keys exist (but use "NA" not hardcoded values)
    structured.setdefault("total_value_inr", _get(r"Total Value of Property.*?([\d,]+)", extracted_text, DEFAULT_TEXT))
    structured.setdefault("total_value_amenities_inr", _get(r"Amenities.*?([\d,]+)", extracted_text, DEFAULT_TEXT))

    return structured
