import requests
import os
import base64
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get("AZURE_MISTRAL_API_KEY")
url = os.environ.get("AZURE_MISTRAL_ENDPOINT")

print(f"Key: {key[:5]}... URL: {url}")
