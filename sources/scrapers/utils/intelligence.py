import os
import time
import google.generativeai as genai
from dotenv import load_dotenv

# Load env
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

class IntelligenceEngine:
    """
    Handles interactions with Gemini API for document processing.
    """
    
    def __init__(self, model_name="gemini-2.0-flash-exp"):
        self.model_name = model_name
        self.api_available = bool(API_KEY)
        
    def summarize_pdfs(self, pdf_paths: list[str], prompt: str = None) -> str:
        """
        Uploads PDFs and generates a summary using Gemini.
        """
        if not self.api_available:
            return "❌ API Key not found. Please set GEMINI_API_KEY."
            
        if not pdf_paths:
            return "No PDFs provided for summarization."

        uploaded_files = []
        try:
            print(f"  → Uploading {len(pdf_paths)} files to Gemini...")
            for path in pdf_paths:
                if not os.path.exists(path):
                    print(f"    ⚠ File not found: {path}")
                    continue
                
                # Upload file
                # Display name is filename
                display_name = os.path.basename(path)
                file_ref = genai.upload_file(path, display_name=display_name)
                uploaded_files.append(file_ref)
                print(f"    ✓ Uploaded: {display_name}")
            
            if not uploaded_files:
                return "No valid files uploaded."

            # Wait for processing
            print("  → Waiting for file processing...")
            for f in uploaded_files:
                while f.state.name == "PROCESSING":
                    time.sleep(1)
                    f = genai.get_file(f.name)
                
                if f.state.name == "FAILED":
                    print(f"    ✗ Processing failed for {f.display_name}")

            # Generate content
            print(f"  → Generating summary with {self.model_name}...")
            model = genai.GenerativeModel(self.model_name)
            
            default_prompt = """
            You are a civic intelligence analyst. Analyze the following government documents.
            Provide a concise summary of the key announcements. 
            Group them by category (e.g., Elections, Health, Environment, Infrastructure).
            Identify any immediate actions required by citizens.
            """
            
            user_prompt = prompt if prompt else default_prompt
            
            response = model.generate_content([user_prompt, *uploaded_files])
            return response.text

        except Exception as e:
            return f"Error interacting with Gemini: {e}\n(Note: {self.model_name} might be invalid, try gemini-1.5-flash)"
        
        finally:
            # Cleanup files to avoid cluttering storage? 
            # Usually good practice to delete them after use if not needed cached.
            # But for this script, we'll leave them or maybe delete them.
            # Google AI files are temporary anyway.
            pass
