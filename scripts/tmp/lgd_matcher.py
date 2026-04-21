import json
import re
from pathlib import Path

# --- INPUT LIST ---
INSTITUTIONS = [
    "Alnavar Town Panchayat, Karnataka",
    "Alur Town Panchayat, Karnataka",
    "Ankola Town Panchayat, Karnataka",
    "Arakkalagudu Town Panchayat, Karnataka",
    "Bagalkote District",
    "Belgaum City Corporation, Karnataka",
    "Belthangady Town Panchayat, Karnataka",
    "Bhatkal Town Municipal Council, Karnataka",
    "Channagiri Municipality, Karnataka",
    "Channapatna Municipality, Karnataka",
    "Chickmagalur City Municipal Council, Karnataka",
    "Chitradurga City Municipal Council, Karnataka",
    "City Municipal Council, Raichur, Karnataka",
    "Connore Municipality, Karnataka",
    "Devanahalli Town Municipal Council, Karnataka",
    "District Panchayat Yadagiri, Karnataka",
    "Gokak City Municipal Council, karnataka",
    "Gudibande Town Panchayat, Karnataka",
    "Haliyala Municipality, Karnataka",
    "Hanur Town Panchayat, Karnataka",
    "Hassan Municipality, Karnataka",
    "Haveri City Municipal Council, karnataka",
    "Hdcote Municipality, Karnataka",
    "Hirekeroor Town Panchayat, Karnataka",
    "Holalkere Town Panchayath, Karnataka",
    "Honnali Town Panchayat, Karnataka",
    "Honnavara Town Panchayat, Karnataka",
    "Hookery Municipality, Karnataka",
    "Hoovinahadagali Town Municipal Council, Karnataka",
    "Hosakote Municipality, Karnataka",
    "Hosanagara Town Panchayat, Karnataka",
    "Hungund Municipality, Karnataka",
    "Jewargi Town Panchayat, Karnataka",
    "Kalaghatagi Town Panchayat, Karnataka",
    "Kamalapura Town Panchayat, Karnataka",
    "Kampli Municipality, Karnataka",
    "Kerura Town Panchayat, Karnataka",
    "Koppa Town Panchayat, Karnataka",
    "Koratagere Town Panchayat, Karnataka",
    "Kudachi Municipality, Karnataka",
    "Kudalagi Town Panchayat, Karnataka",
    "Kundagol Town Panchayat, Karnataka",
    "Kundapur Town Municipal Council, Karnataka",
    "Kushalnagar Town Panchayat, Karnataka",
    "MOLAKALMURU Town Panchayath",
    "Mandya District",
    "Mangalore City Corporation, Karnataka",
    "Monday Township Panchayat, Karnataka",
    "Mudgal Municipality, Karnataka",
    "Mulagunda Town Panchayat, Karnataka",
    "Mulki Town Panchayat, Karnataka",
    "Nagamangala Town Panchayat, Karnataka",
    "Narasimharajapura Town Panchayat, Karnataka",
    "Pandavapura Town Panchayath, Karnataka",
    "Panorama Of Aura Town Panchayath, Karnataka",
    "Periyapatna Town Panchayat, Karnataka",
    "Raibag Town Panchayat, Karnataka",
    "Sadalga Town Municipal Council, Karnataka",
    "Saligrama Town Panchayat, Karnataka",
    "Sargur Town Panchayat, Karnataka",
    "Udupi Zilla Panchayat, Karnataka",
    "Virajpet Town Panchayat, Karnataka",
    "Yelandur Town Panchayat, Karnataka",
    "Yellapura Town Panchayat, Karnataka",
    "Zilla Panchayat Karwar, Karnataka",
    "Sorab Town Panchayat, Karnataka",
    "Suliah Town Panchayat, Karnataka",
    "TH. Narasipura Municipality, Karnataka",
    "Tekkalakote Town Panchayath, Karnataka",
    "Turuvekere Town Panchayat, Karnataka",
    "Zilla Panchayat, Raichur, Karnataka",
    "Zilla Panchayat, Tumkuru, Karnataka",
    "Shirahatti Town Panchayat, Karnataka",
    "Shringeri Town Panchayat, Karnataka",
    "Siddapura Town Panchayat, Karnataka",
    "Sirsi City Municipal Council, Karnataka",
    "Siruguppa City Municipal Council, Karnataka"
]

# --- PATHS ---
RESOURCES_DIR = Path("/home/sidhant/Desktop/the-darshi-stack/sourcegov/government-announcements/resources")
DISTRICTS_JSON = RESOURCES_DIR / "LGD-districts.json"
PINCODE_JSON = RESOURCES_DIR / "LGD-pincode.json"

def clean_name(name):
    """Extracts the core name from strings like 'Alnavar Town Panchayat, Karnataka'."""
    n = name.replace(", Karnataka", "").replace(", karnataka", "")
    n = re.sub(r'Town Panchayat|Town Panchayath|City Municipal Council|Town Municipal Council|Municipality|Zilla Panchayat|District Panchayat|City Corporation|District', '', n, flags=re.IGNORECASE)
    return n.strip()

def run_matcher():
    print(f"Loading resources from {RESOURCES_DIR}...")
    
    with open(DISTRICTS_JSON, 'r') as f:
        districts_data = json.load(f)["records"]
    
    with open(PINCODE_JSON, 'r') as f:
        pincode_data = json.load(f)["records"]

    # Filter for Karnataka
    ka_districts = [d["district_name_english"].lower() for d in districts_data if d["state_name_english"] == "Karnataka"]
    ka_local_bodies = [p for p in pincode_data if p["stateNameEnglish"] == "Karnataka"]

    results = []
    matched_count = 0

    print(f"\nMatching {len(INSTITUTIONS)} institutions...\n")
    print(f"{'Institution':<50} | {'Matched Name':<20} | {'LGD Code':<10} | {'Inferred District'}")
    print("-" * 100)

    for inst in INSTITUTIONS:
        core = clean_name(inst)
        
        # 1. Try exact match in LGD-pincode
        match = next((lb for lb in ka_local_bodies if lb["localBodyNameEnglish"].lower() == core.lower()), None)
        
        # 2. Try inferred district from the name itself
        inferred_district = "Unknown"
        for d in ka_districts:
            if d in inst.lower():
                inferred_district = d.capitalize()
                break
        
        if match:
            matched_count += 1
            print(f"{inst[:48]:<50} | {match['localBodyNameEnglish']:<20} | {match['localBodyCode']:<10} | {inferred_district}")
            results.append({
                "original": inst,
                "core": core,
                "lgd_code": match['localBodyCode'],
                "district": inferred_district,
                "type": match['localBodyTypeName']
            })
        else:
            print(f"{inst[:48]:<50} | {'NO MATCH':<20} | {'-':<10} | {inferred_district}")
            results.append({
                "original": inst,
                "core": core,
                "lgd_code": None,
                "district": inferred_district,
                "type": "Unknown"
            })

    print("-" * 100)
    print(f"\nSummary: Matched {matched_count}/{len(INSTITUTIONS)} items.")

if __name__ == "__main__":
    run_matcher()
