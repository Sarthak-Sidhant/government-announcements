#!/usr/bin/env python3
import requests
import json
import re
from bs4 import BeautifulSoup
import urllib3
import os
import sys
from urllib.parse import urlparse, urljoin
import concurrent.futures
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from dotenv import load_dotenv

load_dotenv()

urllib3.disable_warnings()

# NVIDIA NIMS Configuration
MODEL = "nvidia/nemotron-3-super-120b-a12b"

llm = ChatNVIDIA(
    model=MODEL,
    api_key=os.environ["NVIDIA_API_KEY"],
    temperature=0.1,
    top_p=0.95,
    reasoning_budget=1024, # Enabled for structural analysis
)
# Note: Using the same model ID to ensure stability, but using reasoning-focused prompt
reasoning_llm = ChatNVIDIA(
    model=MODEL,
    api_key=os.environ["NVIDIA_API_KEY"],
    temperature=0.1
)

def strip_boilerplate(html):
    """Remove head, headers, footers, nav, and scripts to focus on content."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["head", "script", "style", "nav", "footer", "header", "svg", "form", "aside"]):
        tag.decompose()
    return soup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDLIST_FILE = os.path.join(BASE_DIR, "data", "s3waas_wordlist.txt")


def ask_llm(paths_data, domain):
    """
    Analyze sitemap structure and group paths by category using NVIDIA NIMS.
    Returns a dictionary with grouped paths, site overview, and subsite explanations.
    """
    category_keywords = [
        "recruitment", "result", "appointment", "vacancy", "hiring", "tender", "bid", "quotation", "nit", "notice",
        "announcement", "circular", "office order", "memorandum", "guideline", "scheme", "document", "press release",
        "gazette", "census", "statistical", "report", "admission", "forms", "application"
    ]
    interesting_paths = [p for p in paths_data if any(k in p.lower() for k in category_keywords)]
    if len(interesting_paths) < 150:
        remaining = [p for p in paths_data if p not in interesting_paths]
        interesting_paths.extend(remaining[:150 - len(interesting_paths)])
    
    prompt = f"""
    Analyze the structure of the Indian government website: https://{domain}/
    Based on these URL paths, provide:
    1. A concise overview of the site and its purpose.
    2. Explanations of any significant subsites or logical sections (e.g. departments, services).
    3. Categorization of the paths into groups like "Documents", "Recruitment", "Tenders" with priority rankings.
    
    Paths: {json.dumps(interesting_paths[:150])}
    
    Return ONLY a JSON object:
    {{
      "site_overview": "...",
      "subsite_analysis": [
         {{"name": "...", "explanation": "..."}}
      ],
      "categories": [
        {{"category": "Documents & Notices", "paths": ["/documents/"], "priority": "high", "description": "Official circulars and gazettes"}},
        ...
      ]
    }}
    """

    print(f"Calling NVIDIA NIMS ({MODEL}) for agentic site analysis...")
    try:
        response = llm.invoke(prompt)
        content = response.content
        
        # Robust JSON extraction
        match = re.search(r"({.*})", content, re.DOTALL)
        if match:
            json_str = match.group(1)
            parsed = json.loads(json_str)
            parsed["raw_paths"] = paths_data
            
            if response.additional_kwargs and "reasoning_content" in response.additional_kwargs:
                print("\n  🧠 LLM Thinking Process Summary:")
                reasoning = response.additional_kwargs["reasoning_content"]
                print(f"  {reasoning[:300]}...")
                
            return parsed
        else:
            raise ValueError(f"No JSON object found in response. Raw content: {content[:500]}")
            
    except Exception as e:
        print(f"  ⚠ LLM analysis failed: {e}")
        return {"categories": [], "raw_paths": paths_data, "error": str(e)}


def get_fallback_categories(paths_data):
    """
    Provide hardcoded high priority paths if LLM fails.
    """
    high_priority_keywords = ["document", "notice", "announcement", "circular", "order", "press", "release", "gazette", "recruitment", "tender", "directory", "contact"]
    fallback_paths = []
    for path in paths_data:
        if any(k in path.lower() for k in high_priority_keywords):
            fallback_paths.append(path)
            
    if fallback_paths:
        return {"categories": [{"category": "Priority Documents (Fallback)", "paths": fallback_paths, "priority": "high"}]}
    return {"categories": []}


def discover_selectors(html_content, url):
    """
    Identify CSS selectors for repeating data elements (cards, rows, entries).
    """
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "svg", "path", "footer", "header", "nav", "aside"]):
        tag.decompose()
    
    clean_html = soup.prettify()[:10000]

    prompt = f"""
    Analysis: {url}
    Identify the CSS selector for repeating information "containers" (e.g. info cards, table rows, list items).
    If the page is a static informational page with NO repeating containers, return null for "container_selector".
    
    Return a JSON object:
    {{
      "container_selector": "css selector or null",
      "fields": {{
         "title": "css selector relative to container",
         "description": "css selector relative to container",
         "link": "css selector relative to container"
      }}
    }}
    
    HTML Snippet:
    {clean_html}
    """

    try:
        response = reasoning_llm.invoke(prompt)
        content = response.content
        match = re.search(r"({.*})", content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"  ⚠ Selector discovery failed: {e}")
    return None
def fetch_page_content(url, session):
    """
    Fetch and analyze a single page.
    1. Extract structural data (tables, assets, links).
    2. Extract semantic data using dynamic LLM-discovered selectors.
    3. Generate a grounded summary using reasoning_llm.
    """
    import time
    for attempt in range(2):
        try:
            resp = session.get(url, timeout=30, verify=False)
            if resp.status_code != 200:
                return None
            
            soup = BeautifulSoup(resp.content, "html.parser")
            data_soup = BeautifulSoup(resp.content, "html.parser") # Fresh soup for extraction
            
            # 1. Structural Extraction (Tables) - Enhanced for Linkage
            tables_data = []
            try:
                for table in data_soup.find_all("table"):
                    rows = []
                    for tr in table.find_all("tr"):
                        row_cells = []
                        for cell in tr.find_all(["td", "th"]):
                            text = cell.get_text(strip=True)
                            # Capture any links in the cell to maintain context linkage
                            cell_links = cell.find_all("a", href=True)
                            if cell_links:
                                link_str = " | ".join([urljoin(url, a['href']) for a in cell_links])
                                # If the text is just "View" or similar, use the URL as more descriptive
                                if len(text) < 5 and "http" in link_str:
                                    row_cells.append(f"{text} [{link_str}]")
                                else:
                                    row_cells.append(f"{text} ({link_str})")
                            else:
                                row_cells.append(text)
                        if row_cells: rows.append(row_cells)
                    if rows: tables_data.append(rows)
            except Exception as e:
                print(f"  ⚠ Table extraction error on {url}: {e}")
            
            # 2. Asset Extraction (PDFs, Docs, etc)
            asset_links = []
            doc_exts = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip")
            for a in data_soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(href.endswith(ext) for ext in doc_exts):
                    asset_links.append({"text": a.get_text(strip=True), "url": urljoin(url, a["href"])})
            
            # 3. Dynamic Selector Discovery & Semantic Extraction
            extracted_items = []
            selectors = discover_selectors(resp.text, url)
            if selectors and selectors.get("container_selector"):
                try:
                    containers = data_soup.select(selectors["container_selector"])
                    for container in containers:
                        item = {}
                        for field, selector in selectors.get("fields", {}).items():
                            if not selector: continue # Skip null selectors
                            element = container.select_one(selector)
                            if element:
                                if field == 'link' and element.get('href'):
                                    item[field] = urljoin(url, element['href'])
                                else:
                                    item[field] = element.get_text(strip=True)
                        if item: extracted_items.append(item)
                except Exception as e:
                    print(f"  ⚠ Selector error for {url}: {e}")

            # 4. Grounded Summarization
            cleaned_html = strip_boilerplate(resp.text)
            title_str = soup.title.string.strip() if soup.title else "No Title"
            
            # Context Building
            tables_context = ""
            if tables_data:
                tables_context = "TABLES DATA:\n" + json.dumps(tables_data[:5], indent=2)[:3000] # Limit size
            assets_context = ""
            if asset_links:
                assets_context = "ASSETS FOUND:\n" + "\n".join([f"- {a['text']}: {a['url']}" for a in asset_links[:10]])
            items_context = ""
            if extracted_items:
                items_context = "STRUCTURED ITEMS:\n" + json.dumps(extracted_items[:10], indent=2)

            prompt = f"""
            Analyze this Indian Government page: {url}
            Title: {title_str}
            
            CONTEXT FROM EXTRACTION:
            {items_context}
            {tables_context}
            {assets_context}
            
            PAGE CONTENT (HTML SNIPPET):
            {str(cleaned_html)[:5000]}
            
            TASK:
            Summarize the purpose and key content of this page naturally.
            - If it's a directory (NGOs, Tenders, Contacts), mention what kind of entities are listed and highlight key details (like phone numbers or dates) found in the tables/items.
            - Keep it informative for a citizen. 
            - DO NOT say "The page does not list X" or "X is missing". Just focus on what IS there.
            - DO NOT hallucinate names or numbers.
            """

            try:
                res = reasoning_llm.invoke(prompt)
                page_purpose = res.content.strip()
            except Exception as e:
                print(f"  ⚠ LLM Summarization failed for {url}: {e}")
                page_purpose = f"Summary generated from metadata. (LLM Error: {type(e).__name__}). Assets: {len(asset_links)}, Tables: {len(tables_data)}."

            return {
                "url": url,
                "title": title_str,
                "knowledge": {
                    "url": url,
                    "page_purpose": page_purpose,
                    "structured_knowledge": {"extracted_items": extracted_items},
                    "extracted_tables": tables_data,
                    "discovered_assets": asset_links
                },
                "discovered_paths": [] 
            }
            
        except Exception as e:
            msg = str(e)
            if "Max retries exceeded" in msg or "Failed to resolve" in msg:
                print(f"  ⚠ Network/DNS error for {url} (Attempt {attempt+1})")
            else:
                print(f"  ⚠ Connectivity error for {url} (Attempt {attempt+1}): {e}")
            
            if attempt < 1: 
                time.sleep(5) # Longer sleep for network issues
                continue
            else: 
                return None
    return None


def load_wordlist():
    """Load common S3WaaS paths from wordlist file."""
    paths = set()
    if os.path.exists(WORDLIST_FILE):
        with open(WORDLIST_FILE, "r") as f:
            for line in f:
                p = line.strip()
                if p and len(p) > 1:
                    paths.add(p)
    return list(paths)


def probe_paths(domain, paths, session):
    """Check which paths from wordlist exist on the domain."""
    valid_paths = set()
    
    def check_path(path):
        url = urljoin(f"https://{domain}/", path)
        try:
            # Using HEAD first to be polite and fast
            r = session.head(url, verify=False, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                return path
        except:
            pass
        return None

    print(f"  -> Probing {len(paths)} common S3WaaS paths...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_path, paths)
        for p in results:
            if p:
                valid_paths.add(p)
    
    if valid_paths:
        print(f"  ✓ Discovered {len(valid_paths)} valid paths via wordlist probing.")
    return valid_paths


def spider_domain(domain, max_depth=10, extract_all=False): # Added extract_all flag
    print(f"Starting Universal Discovery Agent on {domain} (Depth: {max_depth})...")

    visited = set()
    to_visit = {f"https://{domain}/", f"https://{domain}/site-map/"}

    unique_paths = set()

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for depth in range(max_depth):
        print(f" -> Crawling Depth {depth} (Queue: {len(to_visit)})")
        next_visit = set()

        def fetch(url):
            try:
                r = session.get(url, verify=False, timeout=10)
                if "text/html" in r.headers.get("Content-Type", ""):
                    return url, r.text
            except:
                pass
            return url, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            for url, html in executor.map(fetch, to_visit):
                visited.add(url)
                if not html: continue

                # CLEAN HTML early to find links better and save space
                soup = strip_boilerplate(html)
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if (href.startswith(("javascript:", "#", "mailto:"))): continue

                    full_url = urljoin(url, href).split("#")[0]
                    # Specific handler for pagination to avoid depth traps
                    if "/page/" in full_url:
                        # Allow pagination links regardless of depth if they are within domain
                        pass 

                    parsed = urlparse(full_url)
                    if parsed.netloc in (domain, f"www.{domain}"):
                        path = parsed.path or "/"
                        # Filter obvious non-human pages
                        if path.lower().endswith((".jpg", ".png", ".css", ".js", ".mp4", ".zip")):
                            continue
                        
                        unique_paths.add(path)
                        if full_url not in visited:
                            next_visit.add(full_url)

        to_visit = next_visit - visited
        if not to_visit:
            break

    paths_list = list(unique_paths)
    print(f"Spider completed. Discovered {len(paths_list)} unique internal paths via crawling.")

    # Active Discovery: Probe wordlist for common paths not found via crawling
    wordlist = load_wordlist()
    if wordlist:
        probed_paths = probe_paths(domain, wordlist, session)
        unique_paths.update(probed_paths)
        paths_list = list(unique_paths)

    sitemap_analysis = ask_llm(paths_list, domain)
    if not sitemap_analysis.get("categories"):
        print("  ⚠ Using fallback categorization due to LLM failure...")
        sitemap_analysis = get_fallback_categories(paths_list)

    content_results = []
    high_priority_paths = []

    if sitemap_analysis.get("categories"):
        for cat in sitemap_analysis["categories"]:
            if isinstance(cat, dict) and cat.get("priority") == "high":
                paths = cat.get("paths", [])
                if isinstance(paths, list):
                    for p in paths:
                        high_priority_paths.append(p)
                elif isinstance(paths, str):
                    high_priority_paths.append(paths)

    # Deduplicate while preserving order
    seen_paths = set()
    unique_high_priority = []
    for p in high_priority_paths:
        if p not in seen_paths:
            unique_high_priority.append(p)
            seen_paths.add(p)

    # Parallelize page fetching to handle 100s of pages quickly
    # Increasing max_workers to 10 for speed as requested
    extraction_targets = paths_list if extract_all else unique_high_priority
    print(f"  -> Agentically observing/extracting {len(extraction_targets)} paths (Extract All: {extract_all})...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_page_content, f"https://{domain}{p}" if not p.startswith("http") else p, session): p for p in extraction_targets}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                content = future.result()
                if content:
                    content_results.append(content)
                    print(f"  ✓ Knowledge Captured: {future_to_url[future]} (Total: {len(content_results)})")
                else:
                    print(f"  ❌ Knowledge Extraction FAILED: {future_to_url[future]} (Possible Timeout/Connection Error)")
            except Exception as e:
                print(f"  ❌ Critical failure on {future_to_url[future]}: {e}")

    # Deduplicate assets across the entire site
    all_assets = []
    for res in content_results:
        knowledge = res.get("knowledge", {})
        all_assets.extend(knowledge.get("discovered_assets", []))
    
    unique_asset_urls = {a["url"] for a in all_assets if "url" in a}
    print(f"\n✅ TOTAL UNIQUE ASSETS DISCOVERED: {len(unique_asset_urls)}")
    
    return {
        "domain": domain,
        "total_paths_discovered": len(paths_list),
        "site_overview": sitemap_analysis.get("site_overview", "N/A"),
        "subsite_analysis": sitemap_analysis.get("subsite_analysis", []),
        "categories": sitemap_analysis.get("categories", []),
        "knowledge_base": content_results,
        "all_paths": paths_list,
        "total_unique_assets": len(unique_asset_urls)
    }


def update_wordlist(new_paths):
    os.makedirs(os.path.dirname(WORDLIST_FILE), exist_ok=True)
    existing = set()
    if os.path.exists(WORDLIST_FILE):
        with open(WORDLIST_FILE, "r") as f:
            for line in f:
                if line.strip():
                    existing.add(line.strip())

    added = 0
    with open(WORDLIST_FILE, "a") as f:
        for path in new_paths:
            path = path.strip()
            if not path.startswith("/"):
                path = "/" + path
            if not path.endswith("/"):
                path = path + "/"

            if path not in existing and len(path) > 2:
                f.write(path + "\n")
                existing.add(path)
                added += 1

    print(f"Added {added} new paths to global wordlist.")
    print(f"Total wordlist size: {len(existing)}")


def main():
    target = "ranchi.nic.in"
    if len(sys.argv) > 1:
        target = sys.argv[1]

    print(f"Starting Universal Discovery Agent on {target} (Exhaustive Depth: 20, Full extraction)...")
    result = spider_domain(target, max_depth=20, extract_all=True)

    print("\n" + "=" * 60)
    print(f"SITEMAP ANALYSIS: {target}")
    print("=" * 60)

    print(f"\n📂 SITE OVERVIEW:\n{result['site_overview']}")

    if result.get("subsite_analysis"):
        print("\n🏛 SUBSITES & SECTIONS:")
        for sub in result["subsite_analysis"]:
            print(f"   - {sub.get('name')}: {sub.get('explanation')}")

    print(f"\nTotal paths discovered: {result['total_paths_discovered']}")

    print("\n📂 CATEGORIZED PATH GROUPS:")
    for cat in result["categories"]:
        if not isinstance(cat, dict):
            continue
        priority_marker = "🔴" if cat.get("priority") == "high" else "🟡"
        print(
            f"\n{priority_marker} {cat.get('category', 'Unknown')} ({cat.get('priority', 'medium')} priority)"
        )
        print(f"   Description: {cat.get('description', 'N/A')}")
        paths = cat.get("paths", [])
        if isinstance(paths, list):
            print(f"   Paths: {', '.join(paths[:5])}")
        else:
            print(f"   Paths: {paths}")

    print(f"\n📄 FETCHED KNOWLEDGE BASE: {len(result['knowledge_base'])} items")
    for i, item in enumerate(result["knowledge_base"]):
        print(f"\n--- Item {i + 1}: {item['url']} ---")
        print(f"Title: {item.get('title', 'N/A')}")
        knowledge = item.get("knowledge", {})
        print(f"Purpose: {knowledge.get('page_purpose', 'N/A')}")
        if knowledge.get("extracted_tables"):
            print(f"Tables found: {len(knowledge['extracted_tables'])}")
        if knowledge.get("discovered_assets"):
            print(f"Assets found: {len(knowledge['discovered_assets'])}")

    wordlist_paths = []
    for cat in result["categories"]:
        if isinstance(cat, dict):
            paths = cat.get("paths", [])
            if isinstance(paths, list):
                wordlist_paths.extend(paths)
            elif isinstance(paths, str):
                wordlist_paths.append(paths)

    if wordlist_paths:
        update_wordlist(wordlist_paths)

    # Save results to JSON for downstream processing
    output_file = os.path.join(BASE_DIR, "data", f"{target}_results.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        # Save full result for agentic processing
        json.dump(result, f, indent=2)
    print(f"\n✅ Results saved to: {output_file}")


if __name__ == "__main__":
    main()
