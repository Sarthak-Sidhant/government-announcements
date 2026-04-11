import json
import os
import requests
import csv
import re
from pathlib import Path
import yaml

# --- CONFIGURATION ---
BASE_REGISTRY_PATH = Path("/home/sidhant/Desktop/the-darshi-stack/sourcegov/government-announcements/sources/registry/01_union_of_india")
ENTITIES_LIST_PATH = Path("/home/sidhant/.gemini/antigravity/brain/d2dcbfd2-62cc-4b54-89c1-5fab1bb386b8/browser/scratchpad_e0mwhapg.md") # We'll extract JSON from here

def sanitize_slug(name):
    # Standardize slugs: lowercase, no special chars, underscores instead of spaces
    slug = name.lower()
    # Remove acronyms in parens like (MoA) or (MCA)
    slug = re.sub(r'\(.*?\)', '', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = slug.strip().replace(' ', '_')
    slug = re.sub(r'_+', '_', slug)
    return slug

def get_id_from_url(url):
    if not url: return "unknown"
    return url.split('/')[-1]

def fetch_csv(entity_id):
    csv_url = f"https://igod.gov.in/child_organizations/{entity_id}"
    try:
        response = requests.get(csv_url, timeout=15)
        response.raise_for_status()
        text = response.text
        # The CSV has some quotes that might trip up simple split
        # We'll use csv.DictReader on the multiline string
        lines = text.splitlines()
        reader = csv.DictReader(lines)
        return list(reader)
    except Exception as e:
        print(f"Error fetching CSV for {entity_id}: {e}")
        return []

def create_yaml(path, data):
    os.makedirs(path.parent, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)

def process_entity_recursive(entity_name, details_url, current_type, parent_path):
    entity_id = get_id_from_url(details_url)
    slug = sanitize_slug(entity_name)
    current_path = parent_path / slug
    os.makedirs(current_path, exist_ok=True)
    
    # Entity YAML
    entity_data = {
        "id": entity_id,
        "name": entity_name,
        "type": "ministry" if current_type == "ministries" else "department",
        "jurisdiction": "national",
        "igod_url": details_url,
        "status": "active"
    }
    
    yaml_filename = f"{slug}.yaml"
    create_yaml(current_path / yaml_filename, entity_data)
    
    # Process Organizations/Sub-departments
    print(f"  Fetching child organizations for: {entity_name} ({entity_id})")
    children = fetch_csv(entity_id)
    
    for child in children:
        child_name = child.get("Organization Title")
        child_type = child.get("Organization Type")
        child_url = child.get("Url")
        
        if not child_name: continue
        
        # Determine if it's a department or just an organization
        # The CSV label for type is "Departments" for nested departments
        if child_type == "Departments":
            print(f"    Found nested department: {child_name}")
            # Recursively process the department
            # Usually departments are under ministry/departments/
            dept_parent_path = current_path / "departments"
            process_entity_recursive(child_name, child_url, "departments", dept_parent_path)
        else:
            # Regular Organization
            org_slug = sanitize_slug(child_name)
            org_path = current_path / "organizations" / f"{org_slug}.yaml"
            
            org_data = {
                "id": get_id_from_url(child_url or "external"),
                "name": child_name,
                "entity_type": child_type,
                "website": child_url,
                "parent_id": entity_id
            }
            create_yaml(org_path, org_data)

def main():
    # Load entities from scratchpad
    if not ENTITIES_LIST_PATH.exists():
        print(f"Error: {ENTITIES_LIST_PATH} not found.")
        return
        
    with open(ENTITIES_LIST_PATH, 'r') as f:
        content = f.read()
    
    # Extract JSON block
    match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if not match:
        print("Could not find JSON block in scratchpad")
        return
    
    data = json.loads(match.group(1))
    
    # Process Independent Departments
    print("Processing Independent Departments...")
    for entity in data.get("Independent Departments", []):
        process_entity_recursive(entity['name'], entity['detailsUrl'], "independent_departments", BASE_REGISTRY_PATH / "independent_departments")
        
    # Process Ministries
    print("\nProcessing Ministries...")
    for entity in data.get("Ministries", []):
        process_entity_recursive(entity['name'], entity['detailsUrl'], "ministries", BASE_REGISTRY_PATH / "ministries")

if __name__ == "__main__":
    main()
