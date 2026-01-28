"""
Create comprehensive structured database from JSON data.
Creates 10 tables with all fields extracted from JSON.
"""
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

DB_PATH = Path(__file__).parent / "property_valuations.db"


def init_database(drop_existing: bool = False):
    """
    Initialize all database tables.
    
    IMPORTANT: This function ONLY creates tables - it does NOT populate data.
    Data is ONLY saved when users upload property documents through the normal flow:
    1. User uploads documents
    2. Text is extracted
    3. LLM processes and returns JSON
    4. JSON is saved to database via insert_property_data()
    
    This function is called automatically when save_to_sqlite_database() is called,
    ensuring tables exist before saving data.
    """
    print(f"\n{'='*60}")
    print(f"📊 DATABASE FILE: {DB_PATH.name}")
    print(f"📁 FULL PATH: {DB_PATH.absolute()}")
    print(f"{'='*60}\n")
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    
    if drop_existing:
        # Drop all tables in reverse order of dependencies
        # WARNING: This will delete all existing data!
        print("⚠️ WARNING: Dropping all existing tables - all data will be lost!")
        tables = [
            "documents_list", "pricing_additional_charges", "market_value_details",
            "comparables", "property_construction_details", "property_projection_details",
            "property_setback_details", "property_area_details", "audit_trail",
            "property"
        ]
        for table in tables:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    
    # 1. property - Main property table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS property (
        property_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_reference_number TEXT,
        date_of_valuation TEXT,
        buyer_name TEXT,
        seller_name TEXT,
        contact_person TEXT,
        contact_number TEXT,
        address_1 TEXT,
        address_2 TEXT,
        address_3 TEXT,
        address_4 TEXT,
        building_name TEXT,
        sub_locality TEXT,
        locality TEXT,
        city TEXT,
        pin_code TEXT,
        gps_latitude TEXT,
        gps_longitude TEXT,
        surrounding_land_use TEXT,
        surrounding_condition TEXT,
        negative_area TEXT,
        outside_city_limits TEXT,
        land_area_sft TEXT,
        plot_demarcated TEXT,
        ease_of_identification TEXT,
        location_map_attached TEXT,
        nearby_landmark TEXT,
        year_of_construction TEXT,
        age_years TEXT,
        occupancy_status TEXT,
        occupancy_comments TEXT,
        percentage_completion TEXT,
        total_value_inr TEXT,
        total_value_amenities_inr TEXT,
        valuer_comments TEXT,
        valuer_code TEXT,
        valuer_declaration TEXT,
        disclaimer_text TEXT,
        construction_cost_per_sft TEXT,
        construction_cost_type TEXT,
        replacement_value_inr TEXT,
        documents_provided_by TEXT,
        documents_description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. property_area_details
    cur.execute("""
    CREATE TABLE IF NOT EXISTS property_area_details (
        property_area_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        planned_area_sft TEXT,
        planned_area_source TEXT,
        planned_area_type TEXT,
        permissible_area_far_sft TEXT,
        permissible_area_type TEXT,
        actual_area_sft TEXT,
        actual_area_type TEXT,
        area_adopted_for_valuation_sft TEXT,
        area_adopted_type TEXT,
        loading_factor TEXT,
        loading_factor_type TEXT,
        deviation_in_area TEXT,
        deviation_percent TEXT,
        deviation_acceptable TEXT,
        area_comments TEXT,
        permitted_floor_height_max TEXT,
        permitted_floor_height_min TEXT,
        actual_floor_height_ft TEXT,
        deviation_in_floor_height TEXT,
        floor_height_deviation_acceptable TEXT,
        floor_height_comments TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 3. property_setback_details
    cur.execute("""
    CREATE TABLE IF NOT EXISTS property_setback_details (
        setback_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        permitted_setback_front_ft TEXT,
        permitted_setback_rear_ft TEXT,
        permitted_setback_left_ft TEXT,
        permitted_setback_right_ft TEXT,
        actual_setback_front_ft TEXT,
        actual_setback_rear_ft TEXT,
        actual_setback_left_ft TEXT,
        actual_setback_right_ft TEXT,
        deviation_in_setback_front TEXT,
        deviation_in_setback_rear TEXT,
        deviation_in_setback_left TEXT,
        deviation_in_setback_right TEXT,
        setback_deviation_percent_front TEXT,
        setback_deviation_percent_rear TEXT,
        setback_deviation_percent_left TEXT,
        setback_deviation_percent_right TEXT,
        setback_deviations_acceptable TEXT,
        setback_comments TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 4. property_projection_details
    cur.execute("""
    CREATE TABLE IF NOT EXISTS property_projection_details (
        projection_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        projection_balcony TEXT,
        projection_portico TEXT,
        projection_staircase TEXT,
        projection_overhead_tank TEXT,
        projection_terrace TEXT,
        projection_others TEXT,
        projection_public_nuisance TEXT,
        projection_nuisance_reason TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 5. property_construction_details
    cur.execute("""
    CREATE TABLE IF NOT EXISTS property_construction_details (
        construction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        floors_in_building TEXT,
        floors_in_property TEXT,
        bedrooms TEXT,
        bathrooms TEXT,
        halls TEXT,
        kitchens TEXT,
        other_rooms TEXT,
        lifts TEXT,
        stairs TEXT,
        exterior_condition TEXT,
        exterior_condition_reason TEXT,
        interior_condition TEXT,
        interior_condition_reason TEXT,
        expected_future_life_years TEXT,
        amenities TEXT,
        construction_comments TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 6. comparables - Multiple rows per property
    cur.execute("""
    CREATE TABLE IF NOT EXISTS comparables (
        comparable_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        address_1 TEXT,
        address_2 TEXT,
        address_3 TEXT,
        address_4 TEXT,
        building_name TEXT,
        sub_locality TEXT,
        locality TEXT,
        city TEXT,
        pin_code TEXT,
        date_of_transaction TEXT,
        transaction_type TEXT,
        approx_area_sft TEXT,
        area_type TEXT,
        land_area_sft TEXT,
        approx_transaction_price_inr TEXT,
        approx_transaction_price_land_inr TEXT,
        transaction_price_per_sft_inr TEXT,
        transaction_price_per_sft_land_inr TEXT,
        source_of_information TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 7. market_value_details
    cur.execute("""
    CREATE TABLE IF NOT EXISTS market_value_details (
        market_value_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        market_value_range_land_psft_min TEXT,
        market_value_range_land_psft_max TEXT,
        market_value_range_psft_min TEXT,
        market_value_range_psft_max TEXT,
        base_value_land_psft TEXT,
        base_value_built_psft TEXT,
        base_value_type TEXT,
        total_value_amenities_inr TEXT,
        market_value_information_source TEXT,
        market_value_definition TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 8. pricing_additional_charges
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pricing_additional_charges (
        charges_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        fixed_furniture_fixtures TEXT,
        fixed_furniture_fixtures_description TEXT,
        preferred_location_charge TEXT,
        preferred_location_charge_description TEXT,
        external_development_charge TEXT,
        external_development_charge_description TEXT,
        car_park_charge TEXT,
        car_park_charge_description TEXT,
        transfer_charges TEXT,
        transfer_charges_description TEXT,
        sales_tax TEXT,
        sales_tax_description TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 9. documents_list - Multiple rows per property
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents_list (
        document_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        document_name TEXT NOT NULL,
        provided TEXT,
        remarks TEXT,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # 10. audit_trail / valuer_declaration
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_trail (
        declaration_id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL,
        valuer_declaration TEXT,
        valuer_name TEXT,
        valuation_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES property(property_id) ON DELETE CASCADE
    )
    """)
    
    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_ref ON property(property_reference_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_city ON property(city)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_property ON comparables(property_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_property ON documents_list(property_id)")
    
    con.commit()
    con.close()
    print(f"\n{'='*60}")
    print(f"✅ DATABASE INITIALIZED: {DB_PATH.name}")
    print(f"📁 Database Location: {DB_PATH.absolute()}")
    print(f"✓ All 10 tables created/verified:")
    print(f"   1. property")
    print(f"   2. property_area_details")
    print(f"   3. property_setback_details")
    print(f"   4. property_projection_details")
    print(f"   5. property_construction_details")
    print(f"   6. comparables")
    print(f"   7. market_value_details")
    print(f"   8. pricing_additional_charges")
    print(f"   9. documents_list")
    print(f"   10. audit_trail")
    print(f"{'='*60}\n")


def safe_get(data: Dict, key: str, default: str = "NA") -> str:
    """Safely get value from dict, converting to string."""
    value = data.get(key, default)
    if value is None:
        return "NA"
    value_str = str(value).strip()
    if value_str == "" or value_str.lower() in {"null", "none", "n/a"}:
        return "NA"
    return value_str


def insert_property_data(json_data: Dict[str, Any]) -> int:
    """
    Insert property data into all 10 tables. Returns property_id.
    
    This function saves the LLM JSON data to:
    1. property - Main property details
    2. property_area_details - Area-related values
    3. property_setback_details - Setback information
    4. property_projection_details - Projections (balcony, portico, etc.)
    5. property_construction_details - Construction & building details
    6. comparables - Comparable properties (if present in JSON)
    7. market_value_details - Valuation-related values
    8. pricing_additional_charges - Additional price components
    9. documents_list - Document list
    10. audit_trail - Valuer declaration & audit info
    """
    print(f"\n{'='*60}")
    print(f"💾 SAVING TO DATABASE: {DB_PATH.name}")
    print(f"📁 Database Path: {DB_PATH.absolute()}")
    print(f"{'='*60}\n")
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    
    try:
        # 1. Insert into property table
        cur.execute("""
        INSERT INTO property (
            property_reference_number, date_of_valuation, buyer_name, seller_name,
            contact_person, contact_number, address_1, address_2, address_3, address_4,
            building_name, sub_locality, locality, city, pin_code,
            gps_latitude, gps_longitude, surrounding_land_use, surrounding_condition,
            negative_area, outside_city_limits, land_area_sft, plot_demarcated,
            ease_of_identification, location_map_attached, nearby_landmark,
            year_of_construction, age_years, occupancy_status, occupancy_comments,
            percentage_completion, total_value_inr, total_value_amenities_inr,
            valuer_comments, valuer_code, valuer_declaration, disclaimer_text,
            construction_cost_per_sft, construction_cost_type, replacement_value_inr,
            documents_provided_by, documents_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            safe_get(json_data, "property_reference_number"),
            safe_get(json_data, "date_of_valuation"),
            safe_get(json_data, "buyer_name"),
            safe_get(json_data, "seller_name"),
            safe_get(json_data, "contact_person"),
            safe_get(json_data, "contact_number"),
            safe_get(json_data, "address_1"),
            safe_get(json_data, "address_2"),
            safe_get(json_data, "address_3"),
            safe_get(json_data, "address_4"),
            safe_get(json_data, "building_name"),
            safe_get(json_data, "sub_locality"),
            safe_get(json_data, "locality"),
            safe_get(json_data, "city"),
            safe_get(json_data, "pin_code"),
            safe_get(json_data, "gps_latitude"),
            safe_get(json_data, "gps_longitude"),
            safe_get(json_data, "surrounding_land_use"),
            safe_get(json_data, "surrounding_condition"),
            safe_get(json_data, "negative_area"),
            safe_get(json_data, "outside_city_limits"),
            safe_get(json_data, "land_area_sft"),
            safe_get(json_data, "plot_demarcated"),
            safe_get(json_data, "ease_of_identification"),
            safe_get(json_data, "location_map_attached"),
            safe_get(json_data, "nearby_landmark"),
            safe_get(json_data, "year_of_construction"),
            safe_get(json_data, "age_years"),
            safe_get(json_data, "occupancy_status"),
            safe_get(json_data, "occupancy_comments"),
            safe_get(json_data, "percentage_completion"),
            safe_get(json_data, "total_value_inr"),
            safe_get(json_data, "total_value_amenities_inr"),
            safe_get(json_data, "valuer_comments"),
            safe_get(json_data, "valuer_code"),
            safe_get(json_data, "valuer_declaration"),
            safe_get(json_data, "disclaimer_text"),
            safe_get(json_data, "construction_cost_per_sft"),
            safe_get(json_data, "construction_cost_type"),
            safe_get(json_data, "replacement_value_inr"),
            safe_get(json_data, "documents_provided_by"),
            safe_get(json_data, "documents_description")
        ))
        
        property_id = cur.lastrowid
        
        # 2. Insert into property_area_details
        cur.execute("""
        INSERT INTO property_area_details (
            property_id, planned_area_sft, planned_area_source, planned_area_type,
            permissible_area_far_sft, permissible_area_type, actual_area_sft, actual_area_type,
            area_adopted_for_valuation_sft, area_adopted_type, loading_factor, loading_factor_type,
            deviation_in_area, deviation_percent, deviation_acceptable, area_comments,
            permitted_floor_height_max, permitted_floor_height_min, actual_floor_height_ft,
            deviation_in_floor_height, floor_height_deviation_acceptable, floor_height_comments
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "planned_area_sft"),
            safe_get(json_data, "planned_area_source"),
            safe_get(json_data, "planned_area_type"),
            safe_get(json_data, "permissible_area_far_sft"),
            safe_get(json_data, "permissible_area_type"),
            safe_get(json_data, "actual_area_sft"),
            safe_get(json_data, "actual_area_type"),
            safe_get(json_data, "area_adopted_for_valuation_sft"),
            safe_get(json_data, "area_adopted_type"),
            safe_get(json_data, "loading_factor"),
            safe_get(json_data, "loading_factor_type"),
            safe_get(json_data, "deviation_in_area"),
            safe_get(json_data, "deviation_percent"),
            safe_get(json_data, "deviation_acceptable"),
            safe_get(json_data, "area_comments"),
            safe_get(json_data, "permitted_floor_height_max"),
            safe_get(json_data, "permitted_floor_height_min"),
            safe_get(json_data, "actual_floor_height_ft"),
            safe_get(json_data, "deviation_in_floor_height"),
            safe_get(json_data, "floor_height_deviation_acceptable"),
            safe_get(json_data, "floor_height_comments")
        ))
        
        # 3. Insert into property_setback_details
        cur.execute("""
        INSERT INTO property_setback_details (
            property_id, permitted_setback_front_ft, permitted_setback_rear_ft,
            permitted_setback_left_ft, permitted_setback_right_ft,
            actual_setback_front_ft, actual_setback_rear_ft,
            actual_setback_left_ft, actual_setback_right_ft,
            deviation_in_setback_front, deviation_in_setback_rear,
            deviation_in_setback_left, deviation_in_setback_right,
            setback_deviation_percent_front, setback_deviation_percent_rear,
            setback_deviation_percent_left, setback_deviation_percent_right,
            setback_deviations_acceptable, setback_comments
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "permitted_setback_front_ft"),
            safe_get(json_data, "permitted_setback_rear_ft"),
            safe_get(json_data, "permitted_setback_left_ft"),
            safe_get(json_data, "permitted_setback_right_ft"),
            safe_get(json_data, "actual_setback_front_ft"),
            safe_get(json_data, "actual_setback_rear_ft"),
            safe_get(json_data, "actual_setback_left_ft"),
            safe_get(json_data, "actual_setback_right_ft"),
            safe_get(json_data, "deviation_in_setback_front"),
            safe_get(json_data, "deviation_in_setback_rear"),
            safe_get(json_data, "deviation_in_setback_left"),
            safe_get(json_data, "deviation_in_setback_right"),
            safe_get(json_data, "setback_deviation_percent_front"),
            safe_get(json_data, "setback_deviation_percent_rear"),
            safe_get(json_data, "setback_deviation_percent_left"),
            safe_get(json_data, "setback_deviation_percent_right"),
            safe_get(json_data, "setback_deviations_acceptable"),
            safe_get(json_data, "setback_comments")
        ))
        
        # 4. Insert into property_projection_details
        cur.execute("""
        INSERT INTO property_projection_details (
            property_id, projection_balcony, projection_portico, projection_staircase,
            projection_overhead_tank, projection_terrace, projection_others,
            projection_public_nuisance, projection_nuisance_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "projection_balcony"),
            safe_get(json_data, "projection_portico"),
            safe_get(json_data, "projection_staircase"),
            safe_get(json_data, "projection_overhead_tank"),
            safe_get(json_data, "projection_terrace"),
            safe_get(json_data, "projection_others"),
            safe_get(json_data, "projection_public_nuisance"),
            safe_get(json_data, "projection_nuisance_reason")
        ))
        
        # 5. Insert into property_construction_details
        cur.execute("""
        INSERT INTO property_construction_details (
            property_id, floors_in_building, floors_in_property, bedrooms, bathrooms,
            halls, kitchens, other_rooms, lifts, stairs, exterior_condition,
            exterior_condition_reason, interior_condition, interior_condition_reason,
            expected_future_life_years, amenities, construction_comments
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "floors_in_building"),
            safe_get(json_data, "floors_in_property"),
            safe_get(json_data, "bedrooms"),
            safe_get(json_data, "bathrooms"),
            safe_get(json_data, "halls"),
            safe_get(json_data, "kitchens"),
            safe_get(json_data, "other_rooms"),
            safe_get(json_data, "lifts"),
            safe_get(json_data, "stairs"),
            safe_get(json_data, "exterior_condition"),
            safe_get(json_data, "exterior_condition_reason"),
            safe_get(json_data, "interior_condition"),
            safe_get(json_data, "interior_condition_reason"),
            safe_get(json_data, "expected_future_life_years"),
            safe_get(json_data, "amenities"),
            safe_get(json_data, "construction_comments")
        ))
        
        # 6. Insert comparables (handle multiple formats)
        comparables = []
        
        # Format 1: "comparables" array (from merge_comparables function)
        if "comparables" in json_data and isinstance(json_data["comparables"], list):
            comparables.extend(json_data["comparables"])
        
        # Format 2: "2.1_market_comparables" array
        if "2.1_market_comparables" in json_data and isinstance(json_data["2.1_market_comparables"], list):
            comparables.extend(json_data["2.1_market_comparables"])
        
        # Format 3: "comparable_1", "comparable_2" objects
        for i in [1, 2, 3, 4, 5]:
            comp_key = f"comparable_{i}"
            if comp_key in json_data and isinstance(json_data[comp_key], dict):
                comparables.append(json_data[comp_key])
        
        # Format 4: Flat structure with "_comparable_1" suffix
        comp_dicts = {}
        for key, value in json_data.items():
            if key.endswith("_comparable_1") or key.endswith("_comparable_2"):
                comp_num = key.split("_comparable_")[-1]
                field = key.replace(f"_comparable_{comp_num}", "")
                if comp_num not in comp_dicts:
                    comp_dicts[comp_num] = {}
                comp_dicts[comp_num][field] = value
        
        for comp_dict in comp_dicts.values():
            if comp_dict and any(v and str(v).strip() not in {"", "NA", "N/A"} for v in comp_dict.values()):
                comparables.append(comp_dict)
        
        for comp in comparables:
            if not comp or comp == {}:
                continue
            # Skip if all values are NA
            if all(not v or str(v).strip() in {"", "NA", "N/A"} for v in comp.values()):
                continue
            
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
        
        # 7. Insert into market_value_details
        cur.execute("""
        INSERT INTO market_value_details (
            property_id, market_value_range_land_psft_min, market_value_range_land_psft_max,
            market_value_range_psft_min, market_value_range_psft_max,
            base_value_land_psft, base_value_built_psft, base_value_type,
            total_value_amenities_inr, market_value_information_source, market_value_definition
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "market_value_range_land_psft_min"),
            safe_get(json_data, "market_value_range_land_psft_max"),
            safe_get(json_data, "market_value_range_psft_min"),
            safe_get(json_data, "market_value_range_psft_max"),
            safe_get(json_data, "base_value_land_psft"),
            safe_get(json_data, "base_value_built_psft"),
            safe_get(json_data, "base_value_type"),
            safe_get(json_data, "total_value_amenities_inr"),
            safe_get(json_data, "market_value_information_source"),
            safe_get(json_data, "market_value_definition")
        ))
        
        # 8. Insert into pricing_additional_charges
        cur.execute("""
        INSERT INTO pricing_additional_charges (
            property_id, fixed_furniture_fixtures, fixed_furniture_fixtures_description,
            preferred_location_charge, preferred_location_charge_description,
            external_development_charge, external_development_charge_description,
            car_park_charge, car_park_charge_description,
            transfer_charges, transfer_charges_description,
            sales_tax, sales_tax_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "fixed_furniture_fixtures"),
            safe_get(json_data, "fixed_furniture_fixtures_description"),
            safe_get(json_data, "preferred_location_charge"),
            safe_get(json_data, "preferred_location_charge_description"),
            safe_get(json_data, "external_development_charge"),
            safe_get(json_data, "external_development_charge_description"),
            safe_get(json_data, "car_park_charge"),
            safe_get(json_data, "car_park_charge_description"),
            safe_get(json_data, "transfer_charges"),
            safe_get(json_data, "transfer_charges_description"),
            safe_get(json_data, "sales_tax"),
            safe_get(json_data, "sales_tax_description")
        ))
        
        # 9. Insert documents_list (array)
        documents = json_data.get("documents_list", [])
        if isinstance(documents, list):
            for doc in documents:
                if isinstance(doc, dict):
                    cur.execute("""
                    INSERT INTO documents_list (property_id, document_name, provided, remarks)
                    VALUES (?, ?, ?, ?)
                    """, (
                        property_id,
                        safe_get(doc, "document_name", ""),
                        safe_get(doc, "provided", "No"),
                        safe_get(doc, "remarks", "")
                    ))
        
        # 10. Insert into audit_trail
        cur.execute("""
        INSERT INTO audit_trail (property_id, valuer_declaration, valuer_name, valuation_date)
        VALUES (?, ?, ?, ?)
        """, (
            property_id,
            safe_get(json_data, "valuer_declaration"),
            safe_get(json_data, "valuer_code"),  # Using valuer_code as valuer_name
            safe_get(json_data, "date_of_valuation")
        ))
        
        con.commit()
        
        # Verify the save was successful by querying the database
        cur.execute("SELECT COUNT(*) FROM property WHERE property_id = ?", (property_id,))
        verify_count = cur.fetchone()[0]
        
        if verify_count == 0:
            raise Exception(f"CRITICAL: Property ID {property_id} was not saved to database after commit!")
        
        # Log what was saved
        print(f"\n{'='*60}")
        print(f"✅ PROPERTY SAVED TO DATABASE: {DB_PATH.name}")
        print(f"📊 Property ID: {property_id}")
        print(f"📁 Database: {DB_PATH.absolute()}")
        print(f"✅ Verification: Property ID {property_id} confirmed in database")
        print(f"\n📋 Data saved to all tables:")
        print(f"   ✓ property: 1 row")
        print(f"   ✓ property_area_details: 1 row")
        print(f"   ✓ property_setback_details: 1 row")
        print(f"   ✓ property_projection_details: 1 row")
        print(f"   ✓ property_construction_details: 1 row")
        print(f"   ✓ comparables: {len(comparables)} row(s)")
        print(f"   ✓ market_value_details: 1 row")
        print(f"   ✓ pricing_additional_charges: 1 row")
        print(f"   ✓ documents_list: {len(documents) if isinstance(documents, list) else 0} row(s)")
        print(f"   ✓ audit_trail: 1 row")
        print(f"{'='*60}\n")
        
        return property_id
        
    except Exception as e:
        con.rollback()
        print(f"\n{'='*60}")
        print(f"❌ DATABASE SAVE FAILED: {DB_PATH.name}")
        print(f"📁 Database Path: {DB_PATH.absolute()}")
        print(f"❌ Error: {str(e)}")
        print(f"{'='*60}\n")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        raise e
    finally:
        con.close()


def load_json_files() -> List[Dict]:
    """Load all JSON files from output directory."""
    output_dir = Path(__file__).parent / "output"
    json_files = list(output_dir.glob("property_valuation_*_llm_response.json"))
    
    properties = []
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                properties.append(data)
                print(f"✓ Loaded: {json_file.name}")
        except Exception as e:
            print(f"✗ Error loading {json_file.name}: {e}")
    
    return properties


def main():
    """
    Main function - MANUAL DATABASE REBUILD FROM JSON FILES.
    
    ⚠️ WARNING: This function is ONLY for manual database rebuilding.
    It should NOT be called automatically during normal operation.
    
    The database is NORMALLY populated ONLY when users upload property documents:
     User uploads documents → Text extraction → LLM processing → Save to database
    
    This function is for:
    - Manual rebuilding from existing JSON files (if needed)
    - Development/testing purposes
    
    To use: python create_comprehensive_database.py [--drop]
    """
    import sys
    
    drop_existing = "--drop" in sys.argv
    
    print("=" * 80)
    print("⚠️  MANUAL DATABASE REBUILD FROM JSON FILES")
    print("=" * 80)
    print("\n⚠️  WARNING: This will populate the database from JSON files.")
    print("   Normal operation: Database is populated ONLY when users upload documents.")
    print("   This function is for manual rebuilding only.\n")
    
    if not drop_existing:
        response = input("Continue? This will add properties from JSON files. (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            return
    
    # Initialize database
    init_database(drop_existing=drop_existing)
    
    # Load JSON files
    print("\n📂 Loading JSON files...")
    properties = load_json_files()
    
    if not properties:
        print("❌ No JSON files found in output directory")
        return
    
    print(f"\n📊 Found {len(properties)} properties to insert\n")
    
    # Insert each property
    inserted_count = 0
    for idx, prop_data in enumerate(properties, 1):
        try:
            property_id = insert_property_data(prop_data)
            property_ref = prop_data.get("property_reference_number", "N/A")
            buyer_name = prop_data.get("buyer_name", "N/A")
            print(f"✓ [{idx}/{len(properties)}] Inserted Property ID: {property_id} | Ref: {property_ref} | Buyer: {buyer_name}")
            inserted_count += 1
        except Exception as e:
            print(f"✗ [{idx}/{len(properties)}] Error inserting property: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print(f"✅ COMPLETE: Inserted {inserted_count}/{len(properties)} properties")
    print("=" * 80)
    print(f"\nDatabase location: {DB_PATH}")
    print("\nTables created:")
    print("  1. property")
    print("  2. property_area_details")
    print("  3. property_setback_details")
    print("  4. property_projection_details")
    print("  5. property_construction_details")
    print("  6. comparables")
    print("  7. market_value_details")
    print("  8. pricing_additional_charges")
    print("  9. documents_list")
    print("  10. audit_trail")


if __name__ == "__main__":
    # This block is ONLY executed when running this file directly
    # It is NEVER called automatically during normal operation
    # The database is populated ONLY through save_to_sqlite_database() 
    # which is called from generate_report_from_files() when users upload documents
    main()

