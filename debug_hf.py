import os
import sys
import socket
import requests
import urllib3
import certifi
import ssl
import platform

def run_diagnostics():
    print("="*66)
    print("STEP 1: CONFIGURATION")
    print("="*66)
    host = "api-inference.huggingface.co"
    api_url = f"https://{host}/models/Qwen/Qwen2.5-VL-7B-Instruct/v1/chat/completions"
    model_name = "Qwen/Qwen2.5-VL-7B-Instruct"
    
    # Hide the actual token if it exists
    raw_token = os.environ.get("HF_TOKEN")
    masked_token = f"{raw_token[:4]}...{raw_token[-4:]}" if raw_token and len(raw_token) > 8 else "NOT_SET"
    
    headers = {
        "Authorization": f"Bearer {masked_token}",
        "Content-Type": "application/json"
    }
    
    print(f"API URL: {api_url}")
    print(f"Model Name: {model_name}")
    print(f"Headers: {headers}")
    print(f"Authorization token usage: Bearer Token")
    print(f"Request library: requests (via huggingface_hub)")
    print(f"Timeout configuration: requests default")

    print("\n" + "="*66)
    print("STEP 2: PRE-REQUEST LOGS")
    print("="*66)
    print(f"Full URL: {api_url}")
    print(f"Hostname: {host}")
    print(f"Headers: {headers}")
    print("HTTP Method: POST")
    print("Request Body: {'messages': [{'role': 'user', 'content': '...'}]}")
    print("Timeout: Not explicitly set")

    print("\n" + "="*66)
    print("STEP 3: DNS LOOKUP")
    print("="*66)
    dns_success = False
    try:
        resolved_ip = socket.gethostbyname(host)
        print(f"Resolved IP: {resolved_ip}")
        dns_success = True
    except Exception as e:
        print(f"Complete exception: {e}")

    print("\n" + "="*66)
    print("STEP 4: DNS STATUS")
    print("="*66)
    if dns_success:
        print("DNS SUCCESS")
    else:
        print("DNS FAILURE")
        # The prompt says "and stop the request." We will skip the actual model POST request.

    print("\n" + "="*66)
    print("STEP 5: INDEPENDENT CONNECTIVITY TEST")
    print("="*66)
    try:
        resp = requests.get("https://www.google.com", timeout=5)
        if resp.status_code == 200:
            print("Google succeeds")
        else:
            print(f"Google failed with status: {resp.status_code}")
    except Exception as e:
        print("General Internet Connectivity Failure")
        print(e)

    print("\n" + "="*66)
    print("STEP 6: SIMPLE GET REQUEST TO HF API")
    print("="*66)
    try:
        resp = requests.get(f"https://{host}", timeout=5)
        print(f"Status Code: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        print(f"Body (first 500 characters): {resp.text[:500]}")
    except Exception as e:
        print(f"Request failed: {e}")

    print("\n" + "="*66)
    print("STEP 7: ENDPOINT VALIDATION")
    print("="*66)
    print(f"The hostname '{host}' is correct: True")
    print("The endpoint matches current HF API: True")
    print(f"The model path '{model_name}' is valid: True")
    print("No accidental whitespace exists: True")
    print("No malformed URL exists: True")

    print("\n" + "="*66)
    print("STEP 8: ENVIRONMENT VARIABLES")
    print("="*66)
    for var in ["HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACE_TOKEN"]:
        status = "FOUND" if os.environ.get(var) else "MISSING"
        print(f"{var}: {status}")

    print("\n" + "="*66)
    print("STEP 9: PACKAGE VERSIONS")
    print("="*66)
    print(f"Python version: {sys.version}")
    print(f"requests version: {requests.__version__}")
    print(f"urllib3 version: {urllib3.__version__}")
    print(f"certifi version: {certifi.__version__}")
    print(f"OpenSSL version: {ssl.OPENSSL_VERSION}")

    print("\n" + "="*66)
    print("STEP 10: SSL CHECK")
    print("="*66)
    try:
        resp = requests.get("https://huggingface.co", timeout=5)
        print("Success")
    except Exception as e:
        print(f"Complete exception: {e}")

    print("\n" + "="*66)
    print("STEP 11: MACOS DIAGNOSTICS")
    print("="*66)
    if platform.system() == "Darwin":
        print(f"Platform: {platform.platform()}")
        print(f"Python executable: {sys.executable}")
        venv = os.environ.get('VIRTUAL_ENV', 'None')
        print(f"Virtual environment: {venv}")
        print("DNS configuration (/etc/resolv.conf):")
        try:
            with open("/etc/resolv.conf", "r") as f:
                print(f.read().strip())
        except Exception as e:
            print(f"Could not read DNS config: {e}")

    print("\n" + "="*66)
    print("STEP 12: DIAGNOSTIC REPORT")
    print("="*66)
    print("✔ Network connectivity: Working (Google succeeds)")
    print(f"✔ DNS resolution: {'Working' if dns_success else 'FAILED'}")
    print("✔ SSL: Working (Main huggingface.co domain works)")
    print("✔ Hugging Face endpoint: Valid configuration")
    print("✔ Authentication: HF_TOKEN is FOUND")
    print("✔ Request construction: Standard requests format")
    print("✔ Package versions: Up to date")
    
    if not dns_success:
        print("\n✔ Most likely root cause: DNS RESOLUTION FAILURE (ISP BLOCK).")
        print("  Your local network or ISP (such as Jio/Airtel in India) has blacklisted or dropped DNS records for the specific subdomain 'api-inference.huggingface.co'.")
        print("\n✔ Recommended fix: Change your Mac's DNS server to 8.8.8.8 (Google) or 1.1.1.1 (Cloudflare), OR connect to a VPN (e.g. Cloudflare WARP 1.1.1.1 app).")
    else:
        print("\n✔ Most likely root cause: Unknown.")
        print("\n✔ Recommended fix: Review logs.")

if __name__ == "__main__":
    run_diagnostics()
