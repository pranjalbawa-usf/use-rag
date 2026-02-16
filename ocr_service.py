"""
OCR Service using USF Vision API
=================================
Extracts text and structured JSON from images using the USF vision model.
"""

import base64
import httpx
import json
from pathlib import Path
from typing import Optional, Dict, Any


class OCRService:
    """
    OCR service that uses USF vision API to extract text from images.
    """
    
    def __init__(
        self,
        api_url: str = "https://api.us.inc/usf/v1/chat/completions",
        api_key: str = "ec040bd9-b594-44bc-a196-1da99949a514"
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = 120.0  # Vision requests can take longer
    
    def _encode_image_to_base64(self, image_path: str) -> str:
        """Convert image file to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _get_mime_type(self, image_path: str) -> str:
        """Get MIME type from file extension."""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        return mime_types.get(ext, "image/png")
    
    def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from an image using the USF vision API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Extracted text from the image
        """
        try:
            # Encode image to base64
            image_base64 = self._encode_image_to_base64(image_path)
            mime_type = self._get_mime_type(image_path)
            
            # Build the vision request
            messages = [
                {
                    "role": "system",
                    "content": """You are an OCR (Optical Character Recognition) assistant. 
Your task is to extract ALL text visible in the image.

Instructions:
1. Extract every piece of text you can see in the image
2. Preserve the structure and layout as much as possible
3. Include headers, labels, buttons, menus, and any other text
4. If there are tables, format them clearly
5. If text is unclear, make your best guess and note it
6. Do NOT describe the image - only extract the text
7. If there is no text, say "No text detected in image."

Output the extracted text directly without any preamble."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "Extract all text from this image. Output only the extracted text, preserving structure where possible."
                        }
                    ]
                }
            ]
            
            # Make the API request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": "gpt-4o",  # Vision-capable model
                "messages": messages,
                "max_tokens": 4096,
                "temperature": 0.1  # Low temperature for accurate extraction
            }
            
            print(f"  [OCR] Extracting text from: {Path(image_path).name}")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_msg = f"OCR API error: {response.status_code} - {response.text[:200]}"
                    print(f"  [OCR] {error_msg}")
                    return f"[OCR Error: {error_msg}]"
                
                result = response.json()
                
                # Extract the text from the response
                if "choices" in result and len(result["choices"]) > 0:
                    extracted_text = result["choices"][0]["message"]["content"]
                    print(f"  [OCR] Successfully extracted {len(extracted_text)} characters")
                    return extracted_text
                else:
                    return "[OCR Error: No response from vision model]"
                    
        except FileNotFoundError:
            return f"[OCR Error: Image file not found: {image_path}]"
        except Exception as e:
            print(f"  [OCR] Error: {str(e)}")
            return f"[OCR Error: {str(e)}]"
    
    def extract_structured_json(self, image_path: str) -> Dict[str, Any]:
        """
        Extract structured JSON data from an image (invoice, form, document).
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with extracted structured data
        """
        try:
            image_base64 = self._encode_image_to_base64(image_path)
            mime_type = self._get_mime_type(image_path)
            
            messages = [
                {
                    "role": "system",
                    "content": """You are a document data extraction AI. Extract ALL data from the document image into a structured JSON format.

For INVOICES, extract:
- invoice_number, invoice_date, due_date
- vendor (name, address, phone, email, tax_id)
- customer (name, address, phone, email)
- line_items (array with: description, quantity, unit_price, tax, amount)
- subtotal, tax_total, total, currency
- payment_terms, bank_details

For CONTRACTS/AGREEMENTS, extract:
- document_type, document_number, date
- parties (array with: name, role, address)
- terms, conditions, effective_date, expiry_date
- signatures

For FORMS/APPLICATIONS, extract:
- form_type, form_number, date
- fields (key-value pairs of all form fields)
- applicant_info

For OTHER DOCUMENTS, extract:
- document_type, title, date
- key_information (important fields as key-value pairs)
- entities (people, companies, locations mentioned)
- amounts (any monetary values)
- dates (any dates mentioned)

Output ONLY valid JSON. No explanations."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "Extract all data from this document into structured JSON format. Output only the JSON."
                        }
                    ]
                }
            ]
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": messages,
                "max_tokens": 4096,
                "temperature": 0.1
            }
            
            print(f"  [OCR] Extracting structured JSON from: {Path(image_path).name}")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    return {"error": f"API error: {response.status_code}"}
                
                result = response.json()
                
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    # Clean up the response - remove markdown code blocks if present
                    content = content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                    
                    try:
                        extracted_json = json.loads(content)
                        print(f"  [OCR] Successfully extracted structured JSON")
                        return extracted_json
                    except json.JSONDecodeError:
                        return {"raw_text": content, "parse_error": "Could not parse as JSON"}
                else:
                    return {"error": "No response from vision model"}
                    
        except Exception as e:
            print(f"  [OCR] JSON extraction error: {str(e)}")
            return {"error": str(e)}
    
    def extract_text_from_pdf_page(self, pdf_path: str, page_num: int = 0) -> str:
        """
        Extract text from a PDF page by converting it to an image first.
        Useful for scanned PDFs.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number to extract (0-indexed)
            
        Returns:
            Extracted text from the PDF page
        """
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            if page_num >= len(doc):
                return f"[OCR Error: Page {page_num} does not exist]"
            
            page = doc[page_num]
            
            # Convert page to image
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)
            
            # Save to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                tmp_path = tmp.name
            
            # Extract text from the image
            text = self.extract_text_from_image(tmp_path)
            
            # Clean up
            Path(tmp_path).unlink()
            doc.close()
            
            return text
            
        except ImportError:
            return "[OCR Error: PyMuPDF not installed for PDF processing]"
        except Exception as e:
            return f"[OCR Error processing PDF: {str(e)}]"
    
    def extract_text_from_scanned_pdf(self, pdf_path: str, max_pages: int = 10) -> str:
        """
        Extract text from all pages of a scanned PDF.
        
        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to process
            
        Returns:
            Combined extracted text from all pages
        """
        try:
            import fitz
            
            doc = fitz.open(pdf_path)
            num_pages = min(len(doc), max_pages)
            doc.close()
            
            all_text = []
            for page_num in range(num_pages):
                print(f"  [OCR] Processing PDF page {page_num + 1}/{num_pages}")
                page_text = self.extract_text_from_pdf_page(pdf_path, page_num)
                if page_text and not page_text.startswith("[OCR Error"):
                    all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
            
            if all_text:
                return "\n\n".join(all_text)
            else:
                return "[No text could be extracted from this PDF]"
                
        except Exception as e:
            return f"[OCR Error: {str(e)}]"


# Create a singleton instance
ocr_service = OCRService()


# Quick test
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        print(f"Testing OCR on: {image_path}")
        text = ocr_service.extract_text_from_image(image_path)
        print("\n--- Extracted Text ---")
        print(text)
    else:
        print("Usage: python ocr_service.py <image_path>")
