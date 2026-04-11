import os
import requests
import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

class FileDownloader:
    """
    Handles downloading and storage of files (PDFs, etc.) from government sources.
    """
    
    def __init__(self, base_storage_path: str):
        self.base_path = Path(base_storage_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def download(self, url: str, source_id: str, content_hash: str = None) -> str | None:
        """
        Download a file and save it to the local store.
        
        Args:
            url: URL to download
            source_id: Source ID for directory organization
            content_hash: Optional pre-calculated hash (if not provided, will be calculated from content)
            
        Returns:
            Absolute path to downloaded file, or None if failed.
        """
        if not url:
            return None
            
        try:
            # Create source directory
            source_dir = self.base_path / source_id
            source_dir.mkdir(parents=True, exist_ok=True)
            
            # Fetch content
            response = self.session.get(url, stream=True, verify=False, timeout=30)
            response.raise_for_status()
            
            # Verify it's a file we want (basic check)
            content_type = response.headers.get('Content-Type', '').lower()
            if 'html' in content_type:
                # Sometimes we get redirected to a login page or error page
                print(f"    ⚠ Skipped: Content-Type is {content_type} (likely not a document)")
                return None
                
            # Read content to calculate hash and validity
            content = response.content
            
            if not content_hash:
                content_hash = hashlib.sha256(content).hexdigest()
            
            # Determine extension
            ext = self._guess_extension(url, content_type)
            
            # Save file
            filename = f"{content_hash}{ext}"
            file_path = source_dir / filename
            
            if file_path.exists():
                # Already downloaded
                return str(file_path.absolute())
                
            with open(file_path, 'wb') as f:
                f.write(content)
                
            return str(file_path.absolute())
            
        except Exception as e:
            print(f"    ✗ Download failed for {url}: {e}")
            return None
            
    def _guess_extension(self, url: str, content_type: str) -> str:
        """Guess file extension from URL or Content-Type."""
        # Try URL first
        parsed = urlparse(url)
        path = parsed.path
        ext = os.path.splitext(path)[1].lower()
        
        if ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']:
            return ext
            
        # Try mime
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            return guessed
            
        # Default
        return ".bin"
