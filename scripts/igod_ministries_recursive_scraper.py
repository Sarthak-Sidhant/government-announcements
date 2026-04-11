import json
import os
import re
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import yaml

# --- CONFIGURATION ---
BASE_REGISTRY_PATH = Path("/home/sidhant/Desktop/the-darshi-stack/sourcegov/government-announcements/sources/registry/01_union_of_india/ministries")

# Targeted run for all
TARGETS = [
  { "name": "Ministry of AYUSH (MoA)", "url": "https://igod.gov.in/organization/Rc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Agriculture and Farmers Welfare (MoAFW)", "url": "https://igod.gov.in/organization/FM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Chemicals and Fertilizers (MoCF)", "url": "https://igod.gov.in/organization/Fc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Civil Aviation (MoCA)", "url": "https://igod.gov.in/organization/Fs4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Coal", "url": "https://igod.gov.in/organization/F84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Commerce and Industry (MoCI)", "url": "https://igod.gov.in/organization/GM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Communications (MoC)", "url": "https://igod.gov.in/organization/Gc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Consumer Affairs, Food and Public Distribution (MoCAFP)", "url": "https://igod.gov.in/organization/Gs4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Cooperation", "url": "https://igod.gov.in/organization/3p8Len0BjXgo0VKujWP3" },
  { "name": "Ministry of Corporate Affairs (MCA)", "url": "https://igod.gov.in/organization/G84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Culture", "url": "https://igod.gov.in/organization/HM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Defence (MoD)", "url": "https://igod.gov.in/organization/Hc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Development of North Eastern Region (MDONER)", "url": "https://igod.gov.in/organization/Q84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Earth Sciences (MoES)", "url": "https://igod.gov.in/organization/Hs4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Education (MoE)", "url": "https://igod.gov.in/organization/J84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Electronics and Information Technology (MeitY)", "url": "https://igod.gov.in/organization/RM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Environment, Forest and Climate Change (MoEFCC)", "url": "https://igod.gov.in/organization/H84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of External Affairs (MEA)", "url": "https://igod.gov.in/organization/IM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Finance (MoF)", "url": "https://igod.gov.in/organization/Ic4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Fisheries, Animal Husbandry and Dairying (MoFAHD)", "url": "https://igod.gov.in/organization/SM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Food Processing Industries (MoFPI)", "url": "https://igod.gov.in/organization/Is4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Health and Family Welfare (MoHFW)", "url": "https://igod.gov.in/organization/I84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Heavy Industries (MoHI)", "url": "https://igod.gov.in/organization/JM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Home Affairs (MHA)", "url": "https://igod.gov.in/organization/Jc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Housing and Urban Affairs (MoHUA)", "url": "https://igod.gov.in/organization/Js4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Information and Broadcasting (MIB)", "url": "https://igod.gov.in/organization/KM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Jal Shakti (MoJS)", "url": "https://igod.gov.in/organization/eqNfInUBxrox_NfiSIBI" },
  { "name": "Ministry of Labour and Employment (MoLE)", "url": "https://igod.gov.in/organization/Kc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Law and Justice (MoLJ)", "url": "https://igod.gov.in/organization/Ks4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Micro, Small & Medium Enterprises (MSME)", "url": "https://igod.gov.in/organization/aNJDHHUBGGphvn7wU-S7" },
  { "name": "Ministry of Mines (MoM)", "url": "https://igod.gov.in/organization/K84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Minority Affairs (MoMA)", "url": "https://igod.gov.in/organization/LM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of New and Renewable Energy (MNRE)", "url": "https://igod.gov.in/organization/Lc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Panchayati Raj (MoPR)", "url": "https://igod.gov.in/organization/Ls4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Parliamentary Affairs (MPA)", "url": "https://igod.gov.in/organization/L84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Personnel, Public Grievances and Pensions (MoPPGP)", "url": "https://igod.gov.in/organization/MM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Petroleum and Natural Gas (MoPNG)", "url": "https://igod.gov.in/organization/Mc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Planning (MoP)", "url": "https://igod.gov.in/organization/5wPlNYYB77KrIrzWr9-k" },
  { "name": "Ministry of Ports, Shipping and Waterways (MoPSW)", "url": "https://igod.gov.in/organization/Rs4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Power", "url": "https://igod.gov.in/organization/Ms4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Railways (MoR)", "url": "https://igod.gov.in/organization/M84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Road Transport and Highways (MoRTH)", "url": "https://igod.gov.in/organization/Ns4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Rural Development (MoRD)", "url": "https://igod.gov.in/organization/NM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Science and Technology (MST)", "url": "https://igod.gov.in/organization/Nc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Skill Development and Entrepreneurship (MSDE)", "url": "https://igod.gov.in/organization/R84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Social Justice and Empowerment (MoSJE)", "url": "https://igod.gov.in/organization/nxKd9XkBmn7FjzzhzCSZ" },
  { "name": "Ministry of Statistics and Programme Implementation (MoSPI)", "url": "https://igod.gov.in/organization/Oc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Steel (MoS)", "url": "https://igod.gov.in/organization/Os4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Textiles (MoT)", "url": "https://igod.gov.in/organization/O84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Tourism", "url": "https://igod.gov.in/organization/PM4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Tribal Affairs (MoTA)", "url": "https://igod.gov.in/organization/Pc4zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Women and Child Development (MoWCD)", "url": "https://igod.gov.in/organization/P84zv3QBGZk0jujBKgGW" },
  { "name": "Ministry of Youth Affairs and Sports (MoYAS)", "url": "https://igod.gov.in/organization/QM4zv3QBGZk0jujBKgGW" }
]

# Track visited to prevent infinite loops
visited_urls = set()

def sanitize_slug(name):
    if not name: return "unknown"
    slug = name.lower()
    slug = re.sub(r'\(.*?\)', '', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = slug.strip().replace(' ', '_')
    slug = re.sub(r'_+', '_', slug)
    return slug

def create_yaml(path, data):
    os.makedirs(path.parent, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)

async def scrape_detail_page(page, url):
    """Extracts contact, directory, and sub-org categories from a detail page."""
    print(f"\n[DETAIL] Navigating to: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Security Guard: Prevent leaks from homepage redirects
        if page.url.rstrip('/') in ["https://igod.gov.in", "https://igod.gov.in/home"]:
            print(f"  [!] Redirected to IGOD Homepage (Link Broken): {url}")
            return None
            
        await page.wait_for_selector(".contact-box, .cat-box, h1", timeout=15000)
    except Exception as e:
        print(f"  [!] Detail Page Timeout: {e}")
        return None
    
    data = {
        "official_website": None,
        "contact_details": {},
        "organization_directory": [],
        "sub_org_categories": []
    }
    
    # 1. Contact Details
    try:
        contact_ps = await page.query_selector_all(".contact-box p")
        for p in contact_ps:
            text = await p.inner_text()
            if "Address:" in text: data["contact_details"]["address"] = text.replace("Address:", "").strip()
            elif "Phone No:" in text: data["contact_details"]["phone"] = text.replace("Phone No:", "").strip()
            elif "Fax:" in text: data["contact_details"]["fax"] = text.replace("Fax:", "").strip()
            elif "Email:" in text: data["contact_details"]["email"] = text.split("Email:")[-1].strip()
            elif "Website:" in text:
                link = await p.query_selector("a")
                if link: data["official_website"] = await link.get_attribute("href")
    except: pass

    # 2. Organization Directory
    try:
        dir_table = await page.query_selector("tbody#conDirDataCnt")
        if dir_table:
            rows = await page.query_selector_all("tbody#conDirDataCnt tr.table-row")
            for row in rows:
                cols = await row.query_selector_all("td")
                if len(cols) >= 2:
                    data["organization_directory"].append({
                        "name": (await cols[0].inner_text()).strip(),
                        "designation": (await cols[1].inner_text()).strip(),
                        "organization": (await cols[2].inner_text()).strip() if len(cols) > 2 else None,
                        "contact": (await cols[3].inner_text()).strip() if len(cols) > 3 else None,
                        "email": (await cols[4].inner_text()).strip() if len(cols) > 4 else None
                    })
    except: pass

    # 3. Sub-organization Categories (links to list pages)
    try:
        cat_links = await page.query_selector_all(".cat-box h4 a")
        for link in cat_links:
            cat_name_raw = await link.inner_text()
            cat_url = await link.get_attribute("href")
            
            # Filter: Only follow organization-based category links to prevent global leaks
            if cat_url and "/organization/" not in cat_url:
                continue
                
            cat_name = re.sub(r'\s*\(\d+\)$', '', cat_name_raw)
            data["sub_org_categories"].append({"name": cat_name, "url": cat_url})
    except: pass

    return data

async def scrape_list_page(page, url):
    """Deeply robust list scraper that isolates main results."""
    print(f"\n[LIST] Navigating to: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector(".search-title, a.btn-detail, .search-result-item, .no-result", timeout=15000)
    except:
        pass
        
    entities = []
    try:
        # Greedy strategy: Look for 'li' or '.search-row' containers in the main area
        # We also look for isolated 'a.btn-detail' as a failsafe
        
        # 1. Strategy A: All button-driven entities (internal IGOD pages)
        all_buttons = await page.query_selector_all("a.btn-detail")
        for btn in all_buttons:
            is_in_focus = await btn.evaluate("el => el.closest('.in-focus, .sidebar, aside') !== null")
            if is_in_focus: continue
            
            detail_url = await btn.get_attribute("href")
            container = await btn.evaluate_handle("el => el.closest('li, .search-result-row, .search-row, .search-result-item')")
            
            # Extract name: Check for .search-title class, else clean up container text
            name_elem = await container.query_selector(".search-title")
            if name_elem:
                name = (await name_elem.inner_text()).strip()
            else:
                raw_text = await container.inner_text()
                btn_text = await btn.inner_text()
                name = raw_text.replace(btn_text, "").split('\n')[0].strip()
            
            entities.append({
                "name": name,
                "url": detail_url,
                "is_internal": True
            })
            
        # 2. Strategy B: External-only titles (those without buttons)
        all_titles = await page.query_selector_all(".search-title")
        for t in all_titles:
            is_in_focus = await t.evaluate("el => el.closest('.in-focus, .sidebar, aside') !== null")
            if is_in_focus: continue
            
            name = (await t.inner_text()).strip()
            # If we already got this from a button, skip
            if any(e["name"] == name for e in entities): continue
            
            # Check for link
            tag_name = await t.evaluate("el => el.tagName.toLowerCase()")
            ext_url = await t.get_attribute("href") if tag_name == "a" else None
            if not ext_url:
                link_child = await t.query_selector("a")
                if link_child: ext_url = await link_child.get_attribute("href")
            
            entities.append({
                "name": name,
                "url": ext_url,
                "is_internal": False
            })
            
        print(f"  [INFO] Extracted {len(entities)} items.")
    except Exception as e:
        print(f"  [!] List extraction failure: {e}")
        
    return entities

async def process_entity_recursive(page, name, url, depth=0):
    """Recursively extracts data and returns a structured dictionary."""
    if url is None:
        return {
            "name": name,
            "website": None,
            "status": "active_no_link"
        }

    norm_url = url.rstrip('/')
    if norm_url in visited_urls or depth > 5:
        return None
    visited_urls.add(norm_url)
    
    # Internal detail page
    if "igod.gov.in/organization/" in url and not url.endswith("/list"):
        data = await scrape_detail_page(page, url)
        if not data: return None
        
        entity_data = {
            "name": name,
            "website": data["official_website"],
            "contact": data["contact_details"],
            "directory": data["organization_directory"],
            "sub_organizations": []
        }
        
        # Traverse Categories
        for cat in data["sub_org_categories"]:
            if "Departments" in cat["name"] and depth == 0:
                # We handle Departments at the main loop level to keep them in separate folders
                continue
                
            items = await scrape_list_page(page, cat["url"])
            for item in items:
                sub_data = await process_entity_recursive(page, item["name"], item["url"], depth + 1)
                if sub_data:
                    sub_data["category"] = cat["name"]
                    entity_data["sub_organizations"].append(sub_data)
                else:
                    entity_data["sub_organizations"].append({
                        "name": item["name"],
                        "website": item["url"],
                        "category": cat["name"],
                        "status": "external_link"
                    })
        return entity_data
    else:
        return {
            "name": name,
            "website": url,
            "status": "external_link"
        }

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        for target in TARGETS:
            print(f"\n[START] Root: {target['name']}")
            ministry_slug = sanitize_slug(target['name'])
            ministry_path = BASE_REGISTRY_PATH / ministry_slug
            
            # --- RESUME CHECK ---
            if (ministry_path / "ministry.yaml").exists():
                print(f"  [RESUME] Skipping {target['name']} (already processed).")
                continue
            
            # 1. Scrape Ministry Details
            data = await scrape_detail_page(page, target['url'])
            if not data: continue
            
            create_yaml(ministry_path / "ministry.yaml", {
                "name": target['name'],
                "website": data["official_website"],
                "contact": data["contact_details"],
                "directory": data["organization_directory"],
                "status": "active"
            })
            
            ministry_orgs = []
            for cat in data["sub_org_categories"]:
                items = await scrape_list_page(page, cat["url"])
                
                if "Departments" in cat["name"]:
                    for item in items:
                        if item["url"] and "igod.gov.in/organization/" in item["url"]:
                            dept_slug = sanitize_slug(item['name'])
                            dept_path = ministry_path / "departments" / dept_slug
                            print(f"  Recursing into Department: {item['name']}")
                            
                            dept_data = await process_entity_recursive(page, item['name'], item['url'], depth=0)
                            if dept_data:
                                # Save department.yaml
                                create_yaml(dept_path / f"{dept_slug}.yaml", {
                                    k: v for k, v in dept_data.items() if k != "sub_organizations"
                                })
                                # Consolidated organizations.yaml
                                if dept_data.get("sub_organizations"):
                                    create_yaml(dept_path / "organizations" / "organizations.yaml", {
                                        "parent_department": item['name'],
                                        "organizations": dept_data["sub_organizations"]
                                    })
                        else:
                            dept_slug = sanitize_slug(item['name'])
                            print(f"  Saving External/Dead-end Department: {item['name']}")
                            create_yaml(ministry_path / "departments" / dept_slug / f"{dept_slug}.yaml", {
                                "name": item['name'], "website": item['url'], "status": "external_or_no_details"
                            })
                else:
                    # Non-department organizations directly under ministry
                    for item in items:
                        sub_data = await process_entity_recursive(page, item['name'], item['url'], depth=1)
                        if sub_data:
                            sub_data["category"] = cat["name"]
                            ministry_orgs.append(sub_data)
                        else:
                            ministry_orgs.append({
                                "name": item['name'], "website": item['url'], "category": cat["name"], "status": "external_link"
                            })
            
            if ministry_orgs:
                create_yaml(ministry_path / "organizations" / "organizations.yaml", {
                    "parent_ministry": target['name'],
                    "organizations": ministry_orgs
                })
            
        await browser.close()
    print("\n✅ Flattened Recursive scrape complete.")

if __name__ == "__main__":
    asyncio.run(main())
