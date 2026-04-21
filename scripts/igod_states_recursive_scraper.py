import json
import os
import re
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import yaml

# --- CONFIGURATION ---
BASE_REGISTRY_PATH = Path("/home/sidhant/Desktop/the-darshi-stack/sourcegov/government-announcements/sources/registry/02_states_and_uts")

# Filter targets. If empty, processes all states found on /sg/states.
TARGETS = [] 

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

def read_yaml(path):
    if not path.exists():
        return None
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def create_yaml(path, data):
    os.makedirs(path.parent, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)

async def scrape_lazy_list(page, url):
    """Scrolls down to load all items in a lazy-loaded list, returns only main items (no sidebar)."""
    print(f"    [LAZY] Navigating to: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception as e:
        print(f"      [!] Timeout: {e}")
        return []
        
    prev_count = 0
    items = []
    
    while True:
        # Note: We must select inside the main content area, e.g. .search-result-row or .search-content
        # to avoid capturing sidebar "New Additions" items.
        elements = await page.query_selector_all(".search-content .search-result-row .search-title")
        count = len(elements)
        
        if count == prev_count:
            if count == 0:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            elements = await page.query_selector_all(".search-content .search-result-row .search-title")
            if len(elements) == count:
                break
        
        prev_count = count
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        
    for el in elements:
        text = (await el.inner_text()).strip()
        if text: items.append(text)
        
    return items

async def scrape_detail_page(page, url):
    """From ministry scraper: Extracts contact, directory, sub-org categories."""
    print(f"\n[DETAIL] Navigating to: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        if page.url.rstrip('/') in ["https://igod.gov.in", "https://igod.gov.in/home"]:
            print(f"  [!] Redirected to IGOD Homepage: {url}")
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

    try:
        cat_links = await page.query_selector_all(".cat-box h4 a")
        for link in cat_links:
            cat_name_raw = await link.inner_text()
            cat_url = await link.get_attribute("href")
            if cat_url and "/organization/" not in cat_url:
                continue
            cat_name = re.sub(r'\s*\(\d+\)$', '', cat_name_raw)
            data["sub_org_categories"].append({"name": cat_name, "url": cat_url})
    except: pass

    return data

async def scrape_list_page(page, url):
    """From ministry scraper: Isolates main results from list pages."""
    print(f"\n[LIST] Navigating to: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector(".search-title, a.btn-detail, .search-result-item, .no-result", timeout=15000)
    except:
        pass
        
    entities = []
    try:
        all_buttons = await page.query_selector_all("a.btn-detail")
        for btn in all_buttons:
            is_in_focus = await btn.evaluate("el => el.closest('.in-focus, .sidebar, aside') !== null")
            if is_in_focus: continue
            
            detail_url = await btn.get_attribute("href")
            container = await btn.evaluate_handle("el => el.closest('li, .search-result-row, .search-row, .search-result-item')")
            
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
            
        all_titles = await page.query_selector_all(".search-title")
        for t in all_titles:
            is_in_focus = await t.evaluate("el => el.closest('.in-focus, .sidebar, aside') !== null")
            if is_in_focus: continue
            
            name = (await t.inner_text()).strip()
            if any(e["name"] == name for e in entities): continue
            
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

async def process_department_recursive(page, name, url, depth=0):
    if url is None:
        return {"name": name, "website": None, "status": "active_no_link"}

    norm_url = url.rstrip('/')
    if norm_url in visited_urls or depth > 5:
        return None
    visited_urls.add(norm_url)
    
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
        
        for cat in data["sub_org_categories"]:
            if "Departments" in cat["name"] and depth == 0: continue
            items = await scrape_list_page(page, cat["url"])
            for item in items:
                sub_data = await process_department_recursive(page, item["name"], item["url"], depth + 1)
                if sub_data:
                    sub_data["category"] = cat["name"]
                    entity_data["sub_organizations"].append(sub_data)
                else:
                    entity_data["sub_organizations"].append({
                        "name": item["name"], "website": item["url"], "category": cat["name"], "status": "external_link"
                    })
        return entity_data
    else:
        return {"name": name, "website": url, "status": "external_link"}

MAX_CONCURRENT_PAGES = 5
sem = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

async def scrape_state_districts(context, url):
    """Scrapes districts and their sub-districts/blocks from a districts listing URL concurrently."""
    print(f"  [DISTRICTS] Processing districts from: {url}")
    page = await context.new_page()
    await page.goto(url, wait_until="networkidle", timeout=60000)
    
    # 1. Grab all districts listed
    rows = await page.query_selector_all(".search-content .search-result-row")
    
    districts_data = []
    for row in rows:
        title_tag = await row.query_selector(".search-title")
        if not title_tag: continue
        
        name = (await title_tag.inner_text()).strip()
        ext_url = await title_tag.get_attribute("href")
        
        # Look for subdistricts / blocks links within options
        opts = await row.query_selector_all(".search-opts .btn-detail")
        sub_districts_url = None
        blocks_url = None
        
        for opt in opts:
            text = (await opt.inner_text()).strip().lower()
            href = await opt.get_attribute("href")
            if "sub districts" in text: sub_districts_url = href
            elif "blocks" in text: blocks_url = href
            
        districts_data.append({
            "name": name,
            "website": ext_url,
            "sub_districts_url": sub_districts_url,
            "blocks_url": blocks_url
        })
        
    await page.close()
    print(f"  [INFO] Found {len(districts_data)} districts to map.")
    
    async def process_district(d):
        district_obj = {
            "name": d["name"],
            "website": d["website"],
            "sub_districts": [],
            "blocks": []
        }
        
        async with sem:
            new_page = await context.new_page()
            if d["sub_districts_url"]:
                district_obj["sub_districts"] = await scrape_lazy_list(new_page, d["sub_districts_url"])
            if d["blocks_url"]:
                district_obj["blocks"] = await scrape_lazy_list(new_page, d["blocks_url"])
            await new_page.close()
            
        return district_obj
        
    districts = await asyncio.gather(*(process_district(d) for d in districts_data))
        
    return districts

async def update_state_meta(state_path, districts):
    meta_path = state_path / "_state_meta.yaml"
    
    data = {"id": f"state-{state_path.name}", "name": state_path.name.replace('_', ' ').title(), "type": "state_government"}
    
    if meta_path.exists():
        new_data = read_yaml(meta_path)
        if new_data: data = new_data
        
    if "administrative_divisions" not in data:
        data["administrative_divisions"] = {}
        
    data["administrative_divisions"]["districts"] = districts
    create_yaml(meta_path, data)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("[START] Loading states index...")
        await page.goto("https://igod.gov.in/sg/states", wait_until="networkidle")
        
        state_links = await page.query_selector_all(".cat-box.state ul li a")
        states_to_visit = []
        for sl in state_links:
            name = (await sl.inner_text()).strip()
            url = await sl.get_attribute("href")
            
            if TARGETS and not any(t.lower() in name.lower() for t in TARGETS):
                continue
                
            states_to_visit.append({"name": name, "url": url})
            
        print(f"[INFO] Found {len(states_to_visit)} states to process.")
        
        for state in states_to_visit:
            print(f"\n==========================================")
            print(f" PROCESSING STATE: {state['name']}")
            print(f"==========================================")
            
            state_slug = sanitize_slug(state['name'])
            state_path = BASE_REGISTRY_PATH / state_slug
            os.makedirs(state_path, exist_ok=True)
            
            await page.goto(state['url'], wait_until="networkidle")
            
            cat_boxes = await page.query_selector_all(".cat-post-container .cat-box")
            
            state_organizations = []
            
            # Extract basic structure and URLs without holding onto element handles
            categories_found = []
            for box in cat_boxes:
                h3 = await box.query_selector("h3")
                if not h3: continue
                cat_name = (await h3.inner_text()).strip()
                
                # Check for "View All" link
                view_all = await box.query_selector("a strong")
                view_all_link = None
                if view_all:
                    parent_a = await box.evaluate_handle("el => el.querySelector('a:has(strong)')")
                    if parent_a: view_all_link = await parent_a.get_attribute("href")
                
                # Fallback if no specific format
                if not view_all_link:
                    link_elem = await box.query_selector("a[href*='/organizations']")
                    if link_elem: view_all_link = await link_elem.get_attribute("href")
                    
                links_data = []    
                if not view_all_link:
                    # Fallback to links inside the box directly
                    links = await box.query_selector_all("ul li a.search-title")
                    for l in links:
                        name = (await l.inner_text()).strip()
                        url = await l.get_attribute("href")
                        links_data.append({"name": name, "url": url, "is_internal": False})
                        
                categories_found.append({
                    "name": cat_name,
                    "view_all_link": view_all_link,
                    "links_data": links_data
                })
                
            for cat in categories_found:
                print(f"\n  >> Category: {cat['name']}")
                
                if cat['name'] == "Districts":
                    if cat['view_all_link']:
                        districts = await scrape_state_districts(context, cat['view_all_link'])
                        await update_state_meta(state_path, districts)
                    continue
                    
                elif cat['name'] == "Departments":
                    if not cat['view_all_link']: continue
                    items = await scrape_list_page(page, cat['view_all_link'])
                    for item in items:
                        if item["url"] and "igod.gov.in/organization/" in item["url"]:
                            dept_slug = sanitize_slug(item['name'])
                            dept_path = state_path / "departments" / dept_slug
                            print(f"    Recursing into Department: {item['name']}")
                            
                            dept_data = await process_department_recursive(page, item['name'], item['url'], depth=0)
                            if dept_data:
                                create_yaml(dept_path / f"{dept_slug}.yaml", {k: v for k, v in dept_data.items() if k != "sub_organizations"})
                                if dept_data.get("sub_organizations"):
                                    create_yaml(dept_path / "organizations" / "organizations.yaml", {
                                        "parent_department": item['name'],
                                        "organizations": dept_data["sub_organizations"]
                                    })
                        else:
                            dept_slug = sanitize_slug(item['name'])
                            print(f"    Saving External/Dead-end Department: {item['name']}")
                            create_yaml(state_path / "departments" / dept_slug / f"{dept_slug}.yaml", {
                                "name": item['name'], "website": item['url'], "status": "external_or_no_details"
                            })
                            
                else:
                    # Generic Organization Category (Boards, Commissions, etc.)
                    items = []
                    if cat['view_all_link']:
                        items = await scrape_list_page(page, cat['view_all_link'])
                    else:
                        items = cat['links_data']
                    
                    for item in items:
                        # Try to go deeper if internal
                        if item.get("is_internal") and item["url"] and "igod.gov.in/organization/" in item["url"]:
                            sub_data = await process_department_recursive(page, item['name'], item['url'], depth=1)
                            if sub_data:
                                sub_data["category"] = cat["name"]
                                state_organizations.append(sub_data)
                            else:
                                state_organizations.append({
                                    "name": item['name'], "website": item['url'], "category": cat["name"], "status": "active_no_link"
                                })
                        else:
                            state_organizations.append({
                                "name": item['name'], "website": item['url'], "category": cat["name"], "status": "external_link"
                            })
                            
            if state_organizations:
                create_yaml(state_path / "organizations" / "organizations.yaml", {
                    "parent_state": state['name'],
                    "organizations": state_organizations
                })
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
