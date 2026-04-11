"""
S3WaaS Adapter - Scraper for Standard Secure Scalable Website as a Service sites.
The majority of Indian government websites (districts, municipalities) use this template.
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import hashlib
from urllib.parse import urljoin
import urllib3

# Suppress SSL warnings for government sites with certificate issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Relevance filtering has been removed to extract ALL available documents.


class S3WaaSAdapter:
    """Adapter for scraping S3WaaS-based government websites."""
    
    # Standard S3WaaS document category paths
    DOCUMENT_PATHS = [
        "/documents/",
        "/notice_category/announcement/",
        "/notice_category/e-gazette/",
        "/notice_category/recruitment/",
        "/document-category/notices/",
        "/document-category/circulars/",
        "/document-category/orders/",
        "/document-category/notifications/",
        "/document-category/press-release/",
    ]
    
    # Tab categories to look for on homepage
    TAB_KEYWORDS = [
        "notice", "notification", "announcement", "circular", 
        "order", "press", "release", "news", "update", "latest",
        "gazette", "recruitment", "tender", "vacancy"
    ]
    
    def __init__(self, source_config: dict):
        """
        Initialize with a source configuration dict (from YAML).
        
        Args:
            source_config: Dict containing id, name, url, etc.
        """
        self.config = source_config
        self.source_id = source_config.get('id', 'unknown')
        self.base_url = source_config.get('url', '').rstrip('/')
        self.priority = source_config.get('priority', 'medium')
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def scrape(self, max_items: int = 50) -> list:
        """
        Scrape the source website for announcements.
        
        Returns:
            List of announcement dicts with: title, url, pdf_url, category, content_hash
        """
        if not self.base_url:
            return []
            
        # Try scraping with the base URL
        results = self._scrape_attempt(self.base_url, max_items)
        
        # If no results and URL is not already English, try forcing English
        if not results and "/en" not in self.base_url:
            en_url = self.base_url.rstrip('/') + "/en/"
            print(f"  ⚠ No items found. Retrying with English URL: {en_url}")
            results = self._scrape_attempt(en_url, max_items)
        
        # Deduplicate by content hash
        seen_hashes = set()
        unique_results = []
        for item in results[:max_items]:
            if item.get('content_hash') not in seen_hashes:
                seen_hashes.add(item.get('content_hash'))
                unique_results.append(item)
        
        return unique_results
        
    def _scrape_attempt(self, url_to_scrape: str, max_items: int) -> list:
        """Internal method to try scraping a specific URL."""
        results = []
        
        # Phase 0: Dynamic Discovery
        # Always fetch homepage first to discover links from Navbar
        discovered_paths = []
        try:
            response = self.session.get(url_to_scrape, verify=False, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                discovered_paths = self._discover_menu_links(soup, url_to_scrape)
                print(f"  ✓ Discovered {len(discovered_paths)} categories from Navbar.")
        except Exception as e:
            print(f"  ⚠ Navigation discovery failed: {e}")

        # Combine discovered paths with fallbacks (prioritizing discovered ones)
        # We ensure /documents/ is always checked if not discovered
        # Use set to avoid duplicates while preserving order
        all_paths = []
        seen_urls = set()
        
        # 1. Discovered Paths
        for p in discovered_paths:
            if p not in seen_urls:
                all_paths.append(p)
                seen_urls.add(p)
                
        # 2. Hardcoded Fallbacks (only if not already discovered/scraped)
        for p in self.DOCUMENT_PATHS:
            full_p = urljoin(url_to_scrape, p)
            if full_p not in seen_urls:
                all_paths.append(full_p)
                seen_urls.add(full_p)

        # Strategy 1: Iterate through all identified paths
        for page_url in all_paths:
            # print(f"    Scanning: {page_url}") 
            items = self._scrape_document_list(page_url)
            results.extend(items)
            
            if len(results) >= max_items:
                break
        
        # Strategy 2: If nothing found (highly unlikely now), try homepage tab scraping
        if not results:
            results = self._scrape_homepage_tabs(url_to_scrape)
            
        return results

    def _discover_menu_links(self, soup: BeautifulSoup, base_url: str) -> list:
        """Parse the Navigation Menu to find relevant category links."""
        links = []
        
        # Keywords to look for in Top-Level Menu Items
        target_menus = ["notice", "notification", "document", "update", "citizen", "act", "rule", "report", "publication"]
        
        # Find the main navigation menu
        # S3WaaS standard: <nav class="menu"> or id="menu-header-en"
        nav_menus = soup.find_all('nav', class_='menu')
        if not nav_menus:
            # Fallback for some themes
            nav_menus = soup.find_all('div', class_='menuWrapper')
            
        for nav in nav_menus:
            # S3WaaS menus are usually <nav><ul><li>...</li></ul></nav>
            # Find the top-level UL
            ul = nav.find('ul', recursive=False)
            if not ul:
                # Sometimes direct children are not ul, but deeper
                ul = nav.find('ul')
            
            if not ul:
                continue

            # Iterate top-level LIs
            for li in ul.find_all('li', recursive=False):
                a_tag = li.find('a', recursive=False) 
                if not a_tag:
                    # Sometimes structure is ul > li > a
                    # If recursive=False failed, finding sub li might be issue. 
                    # Let's just iterate all 'li' that contain 'sub-menu' logic or check text
                    pass
                
                # Check text of the menu item
                li_text = li.get_text(strip=True).lower()
                
                # If this menu is interesting (e.g. "Notices", "Documents")
                if any(k in li_text for k in target_menus):
                    # Get all links inside its sub-menu
                    sub_menu = li.find('ul', class_='sub-menu')
                    if sub_menu:
                        for sub_link in sub_menu.find_all('a', href=True):
                            href = sub_link['href']
                            
                            # Filter out typically useless links
                            if "archive" in href or "video" in href or "gallery" in href:
                                continue
                                
                            full_url = urljoin(base_url, href)
                            links.append(full_url)
                    else:
                        # If no submenu, maybe the link itself is the category
                        if a_tag and a_tag.get('href'):
                            full_url = urljoin(base_url, a_tag['href'])
                            links.append(full_url)
                            
        return links
    
    def _scrape_document_list(self, url: str) -> list:
        """Scrape a standard S3WaaS document listing page."""
        items = []
        
        try:
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code != 200:
                return items
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Pattern 1: Table rows (Most common)
            # Strategy: Extract "Row Context" from cells to perform better naming than just "View"
            for row in soup.select('table tbody tr'):
                cells = row.find_all('td')
                if not cells:
                    continue
                
                # Heuristic: Title is usually in the first non-numeric cell
                row_title = ""
                for cell in cells[:2]: # Check first 2 cells
                    text = cell.get_text(strip=True)
                    if len(text) > 3 and not text.isdigit():
                        row_title = text
                        break
                        
                # Date Extraction Heuristic
                # Find all DD/MM/YYYY dates in the row
                row_text = row.get_text(" ", strip=True)
                date_matches = re.findall(r'\d{2}/\d{2}/\d{4}', row_text)
                
                start_date = None
                end_date = None
                
                if len(date_matches) >= 2:
                    start_date = date_matches[0]
                    end_date = date_matches[1]
                elif len(date_matches) == 1:
                    start_date = date_matches[0]
                
                # Find ALL links in the row (supports multiple files per announcement)
                links = row.find_all('a', href=True)
                for link in links:
                    link_text = link.get_text(strip=True)
                    href = link['href']
                    
                    # Skip pagination/archive links often found in footer rows mistakenly inside tbody
                    if 'archive' in link_text.lower() or 'next' in link_text.lower():
                        continue
                        
                    # Compose meaningful title
                    # If link text is generic "View", prepend row title
                    # If link text is "Form A", make it "Row Title - Form A"
                    if row_title:
                        final_title = f"{row_title} - {link_text}"
                    else:
                        final_title = link_text
                        
                    if self._is_relevant(final_title):
                        item = self._create_item(final_title, href, url, start_date, end_date)
                        if item:
                            items.append(item)

            # Pattern 2: List items (div/ul based)
            # Typically: <li> <span>Title</span> <a href>Download</a> </li>
            for li in soup.select('.document-list li, .list-group-item'):
                # Extract text content of the list item excluding the link text for context
                # This is tricky, simpler is to just look for title class or raw text
                li_text = li.get_text(" ", strip=True) 
                
                links = li.find_all('a', href=True)
                for link in links:
                    link_text = link.get_text(strip=True)
                    href = link['href']
                    
                    # Remove link text from li_text to get the "Title"
                    # Simple heuristic: Use full li text but truncate
                    final_title = li_text
                    if len(final_title) > 200:
                         final_title = final_title[:200]
                    
                    if self._is_relevant(final_title):
                        item = self._create_item(final_title, href, url)
                        if item:
                            items.append(item)
                            
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            
        return items
    
    def _scrape_homepage_tabs(self, url: str) -> list:
        """Fallback: Scrape from homepage tabs/widgets."""
        items = []
        
        try:
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code != 200:
                return items
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find tab navigation links
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True).lower()
                
                # Check if this is a tab we're interested in
                matched_category = None
                for keyword in self.TAB_KEYWORDS:
                    if keyword in text:
                        matched_category = keyword
                        break
                
                if matched_category:
                    # Case A: Anchor link to tab content (#tab1)
                    if link['href'].startswith('#'):
                        panel_id = link['href'][1:]
                        panel = soup.find(id=panel_id)
                        if panel:
                            self._extract_from_panel(panel, items, matched_category, url)
                            
                    # Case B: Dropdown menu (like Pune) -> Scrape the new page
                    # e.g. /notice_category/announcements/
                    elif self._is_category_link(link['href']):
                        # Scrape the category page found on homepage
                        cat_href = link['href']
                        if not cat_href.startswith('http'):
                            cat_href = urljoin(url, cat_href)
                            
                        # Avoid infinite recursion or re-scraping base_url
                        if cat_href != url:
                            print(f"    Found Category: {link.get_text(strip=True)} -> {cat_href}")
                            cat_items = self._scrape_document_list(cat_href)
                            items.extend(cat_items)
            
            # Additional strategy: Look for "Latest Updates" or "Notifications" marquee/widget directly
            # unrelated to tabs
            for marquee in soup.select('.marquee, .news-scroll, .latest-news'):
                 self._extract_from_panel(marquee, items, "Notice", url)
                 
        except Exception as e:
            print(f"Error scraping homepage {url}: {e}")
            
        return items
    
    def _is_category_link(self, href):
        return "document-category" in href or "notice_category" in href

    def _extract_from_panel(self, panel, items, category, base_url):
         for item_link in panel.find_all('a', href=True):
            title = item_link.get_text(strip=True)
            href = item_link['href']
            
            if len(title) > 5 and self._is_relevant(title):
                item = self._create_item(title, href, base_url)
                if item:
                    item['category'] = category.title()
                    items.append(item)

    def _create_item(self, title: str, href: str, base_url: str, start_date: str = None, end_date: str = None) -> dict:
        """Create a standardized item dict."""
        # Make URL absolute
        if not href.startswith('http'):
            href = urljoin(base_url, href)
        
        # Generate content hash for deduplication
        content_hash = hashlib.sha256(f"{title}|{href}".encode()).hexdigest()[:16]
        
        # Detect if it's a direct document link
        pdf_url = None
        doc_exts = ('.pdf', '.doc', '.docx', '.xls', '.xlsx')
        if any(href.lower().endswith(ext) for ext in doc_exts):
            pdf_url = href
        
        return {
            'source_id': self.source_id,
            'title': title[:500],  # Limit title length
            'url': href,
            'pdf_url': pdf_url,
            'category': 'Notice',
            'start_date': start_date,
            'end_date': end_date,
            'content_hash': content_hash,
            'scraped_at': None,  # Will be filled by orchestrator
        }
    
    def _is_relevant(self, text: str) -> bool:
        """
        Check if an announcement is relevant.
        Currently returns True for everything to ensure maximum transparency.
        """
        return True
    
    def resolve_pdf(self, url: str) -> str | None:
        """
        Visit a detail page to find the actual PDF link.
        Returns the PDF URL if found.
        """
        try:
            time.sleep(0.3)  # Polite delay
            
            response = self.session.get(url, verify=False, timeout=10)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for View/Download links
            pdf_link = soup.find('a', href=True, string=re.compile(r'View|Download', re.I))
            if not pdf_link:
                pdf_link = soup.find('a', href=re.compile(r'\.pdf$', re.I))
            
            if pdf_link:
                return urljoin(url, pdf_link['href'])
                
        except Exception:
            pass
            
        return None


# Standalone test
if __name__ == "__main__":
    # Test with Pune District
    test_config = {
        "id": "dist-27-pune-coll",
        "name": "Pune District Collectorate",
        "url": "https://pune.gov.in",
        "priority": "high"
    }
    
    adapter = S3WaaSAdapter(test_config)
    results = adapter.scrape(max_items=10)
    
    print(f"\n=== Found {len(results)} items ===\n")
    for item in results:
        print(f"  [{item['category']}] {item['title'][:60]}...")
        print(f"    URL: {item['url'][:80]}")
        if item.get('pdf_url'):
            print(f"    PDF: {item['pdf_url'][:80]}")
        print()
