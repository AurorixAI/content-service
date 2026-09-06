import requests
import os
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get("AZURE_MISTRAL_API_KEY")
url = os.environ.get("AZURE_MISTRAL_ENDPOINT")

headers = {
    "api-key": key,
    "Content-Type": "application/json"
}

data = {
    "model": "mistral-ocr-latest",
    "document": {
        "type": "document_url",
        "document_url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    }
}

r = requests.post(f"{url}?api-version=2024-04-01-preview", headers=headers, json=data)
print(r.status_code, r.text[:500])
