"""
Core Scraper Engine - Orchestrates scraping across all configured sources.
Loads source configs from YAML registry and dispatches to appropriate adapters.
"""

import os
import sys
import glob
import yaml
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.adapters.s3waas import S3WaaSAdapter
from scrapers.utils.downloader import FileDownloader


# Paths
BASE_DIR = Path(__file__).parent.parent.parent
REGISTRY_DIR = BASE_DIR / "sources" / "registry"
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "darshi_sources.db"


class CoreEngine:
    """
    Central orchestrator for scraping government sources.
    
    - Loads all YAML configs from the registry
    - Dispatches to appropriate adapter (S3WaaS, legacy, custom)
    - Stores results in SQLite
    - Handles deduplication via content hashing
    """
    
    def __init__(self):
        self.sources = []
        self.db_conn = None
        self.downloader = FileDownloader(str(RAW_DIR))
        self._init_database()
        
    def _init_database(self):
        """Initialize SQLite database for storing scraped announcements."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        self.db_conn = sqlite3.connect(str(DB_PATH))
        cursor = self.db_conn.cursor()
        
        # Announcements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                pdf_url TEXT,
                local_path TEXT,
                category TEXT,
                start_date TEXT,
                end_date TEXT,
                scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT 0
            )
        ''')
        
        # Check if local_path exists (migration)
        cursor.execute("PRAGMA table_info(announcements)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'local_path' not in columns:
            cursor.execute("ALTER TABLE announcements ADD COLUMN local_path TEXT")
        if 'start_date' not in columns:
            cursor.execute("ALTER TABLE announcements ADD COLUMN start_date TEXT")
        if 'end_date' not in columns:
            cursor.execute("ALTER TABLE announcements ADD COLUMN end_date TEXT")
        
        # Sources tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT,
                scraper_type TEXT,
                last_scraped DATETIME,
                status TEXT DEFAULT 'pending',
                item_count INTEGER DEFAULT 0
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_id ON announcements(source_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_hash ON announcements(content_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scraped_at ON announcements(scraped_at)')
        
        self.db_conn.commit()
        print(f"✓ Database initialized: {DB_PATH}")
    
    def load_sources(self, priority_filter: list = None):
        """
        Load all source configurations from YAML registry.
        
        Args:
            priority_filter: Optional list like ['high', 'medium'] to filter sources
        """
        self.sources = []
        
        yaml_pattern = str(REGISTRY_DIR / "**" / "*.yaml")
        yaml_files = glob.glob(yaml_pattern, recursive=True)
        
        for yaml_path in yaml_files:
            # Skip meta files
            if os.path.basename(yaml_path).startswith('_'):
                continue
                
            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    
                if not config:
                    continue
                    
                # Apply priority filter
                if priority_filter:
                    source_priority = config.get('priority', 'medium')
                    if source_priority not in priority_filter:
                        continue
                
                # Only include sources with URLs
                if config.get('url'):
                    config['_yaml_path'] = yaml_path
                    self.sources.append(config)
                    
            except Exception as e:
                print(f"Warning: Could not load {yaml_path}: {e}")
        
        print(f"✓ Loaded {len(self.sources)} sources from registry")
        return self.sources
    
    def scrape_source(self, source_config: dict, max_items: int = 50, metadata_only: bool = False) -> int:
        """
        Scrape a single source and store results.
        
        Args:
            metadata_only: If True, skips file download
            
        Returns:
            Number of new items added
        """
        source_id = source_config.get('id', 'unknown')
        scraper_type = source_config.get('scraper_type', 's3waas')
        
        print(f"\n→ Scraping: {source_config.get('name', source_id)}")
        print(f"  URL: {source_config.get('url')}")
        print(f"  Type: {scraper_type}")
        
        # Select adapter based on scraper_type
        if scraper_type in ['s3waas', 'unknown']:
            adapter = S3WaaSAdapter(source_config)
        else:
            # TODO: Add legacy NIC adapter
            print(f"  ⚠ Unsupported scraper type: {scraper_type}, using S3WaaS")
            adapter = S3WaaSAdapter(source_config)
        
        # Scrape
        try:
            items = adapter.scrape(max_items=max_items)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            self._update_source_status(source_id, 'error')
            return 0
        
        # Store results
        new_count = 0
        download_count = 0
        cursor = self.db_conn.cursor()
        
        for item in items:
            item['scraped_at'] = datetime.now().isoformat()
            
            # Check if exists to avoid downloading if already there
            cursor.execute("SELECT id FROM announcements WHERE content_hash = ?", (item['content_hash'],))
            exists = cursor.fetchone()
            
            item['local_path'] = None
            
            # Download Logic: Only if NOT metadata_only
            if not metadata_only and not exists and item.get('pdf_url'):
                print(f"    Downloading {item['title'][:30]}...")
                local_path = self.downloader.download(
                    item['pdf_url'],
                    source_id,
                    content_hash=item['content_hash']
                )
                if local_path:
                    item['local_path'] = local_path
                    download_count += 1
            else:
                 # Just logging that we found it
                 # print(f"    Found: {item['title'][:30]} (Metadata Only)")
                 pass
            
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO announcements 
                    (source_id, content_hash, title, url, pdf_url, local_path, category, start_date, end_date, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item['source_id'],
                    item['content_hash'],
                    item['title'],
                    item['url'],
                    item.get('pdf_url'),
                    item.get('local_path'),
                    item.get('category'),
                    item.get('start_date'),
                    item.get('end_date'),
                    item['scraped_at']
                ))
                
                if cursor.rowcount > 0:
                    new_count += 1
                    
            except sqlite3.IntegrityError:
                pass
        
        self.db_conn.commit()
        
        # Update source tracking
        self._update_source_status(source_id, 'active', new_count)
        
        mode_msg = "metadata only" if metadata_only else "files downloaded"
        print(f"  ✓ Found {len(items)} items, {new_count} new ({mode_msg})")
        return new_count
    
    def _update_source_status(self, source_id: str, status: str, item_count: int = 0):
        """Update source tracking in database."""
        cursor = self.db_conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sources (id, name, url, last_scraped, status, item_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            source_id,
            source_id,  # Placeholder name
            '',
            datetime.now().isoformat(),
            status,
            item_count
        ))
        self.db_conn.commit()
    
    def export_json(self, output_file: str = "darshi_master_seed.json"):
        """Export all announcements to a master JSON file for seeding."""
        print(f"\n→ Exporting master seed JSON to {output_file}...")
        
        cursor = self.db_conn.cursor()
        
        # Fetch all announcements joined with source info if needed
        # For now just dump announcements
        cursor.execute('''
            SELECT source_id, title, url, pdf_url, category, start_date, end_date, scraped_at 
            FROM announcements
        ''')
        
        columns = [col[0] for col in cursor.description]
        results = []
        
        rows = cursor.fetchall()
        for row in rows:
            results.append(dict(zip(columns, row)))
            
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"✓ Exported {len(results)} items.")

    def run(self, priority: list = None, limit: int = None, metadata_only: bool = False):
        """
        Run the full scraping pipeline.
        
        Args:
            priority: Filter by priority levels ['high', 'medium', 'low']
            limit: Maximum number of sources to scrape (for testing)
            metadata_only: If True, skips downloads
        """
        print("\n" + "="*60)
        print("DARSHI CORE ENGINE - Starting Scrape Run")
        if metadata_only:
            print("MODE: Metadata Export Only (No Downloads)")
        print("="*60)
        
        self.load_sources(priority_filter=priority)
        
        if limit:
            self.sources = self.sources[:limit]
            print(f"⚠ Limited to {limit} sources for testing")
        
        total_new = 0
        success_count = 0
        
        for source in self.sources:
            try:
                new_items = self.scrape_source(source, metadata_only=metadata_only)
                total_new += new_items
                if new_items > 0:
                    success_count += 1
            except Exception as e:
                print(f"  ✗ Fatal error: {e}")
        
        print("\n" + "="*60)
        print(f"COMPLETE: Scraped {len(self.sources)} sources")
        print(f"  - Successful: {success_count}")
        print(f"  - New items: {total_new}")
        print(f"  - Database: {DB_PATH}")
        print("="*60)
        
        if metadata_only:
            self.export_json()
        
        return total_new
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.db_conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM announcements')
        total_items = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT source_id) FROM announcements')
        sources_with_data = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM sources WHERE status = "active"')
        active_sources = cursor.fetchone()[0]
        
        return {
            'total_announcements': total_items,
            'sources_with_data': sources_with_data,
            'active_sources': active_sources
        }
    
    def close(self):
        """Close database connection."""
        if self.db_conn:
            self.db_conn.close()


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Darshi Core Scraper Engine')
    parser.add_argument('--priority', nargs='+', choices=['high', 'medium', 'low'],
                        default=['high'], help='Priority levels to scrape')
    parser.add_argument('--limit', type=int, help='Limit number of sources (for testing)')
    parser.add_argument('--stats', action='store_true', help='Show database stats only')
    parser.add_argument('--metadata-only', action='store_true', help='Skip file downloads, export JSON')
    
    args = parser.parse_args()
    
    engine = CoreEngine()
    
    if args.stats:
        stats = engine.get_stats()
        print("\n=== Database Stats ===")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    else:
        engine.run(priority=args.priority, limit=args.limit, metadata_only=args.metadata_only)
    
    engine.close()


if __name__ == "__main__":
    main()
