"""
Find Naukri's actual XHR API endpoint by first getting cookies from
the homepage, then calling the search API with those cookies.
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.naukri.com/",
    "Origin": "https://www.naukri.com",
    "appid": "109",
    "systemid": "109",
}

# Step 1: Get cookies from homepage
print("Step 1: Fetching homepage to get cookies...")
with httpx.Client(
    headers={**HEADERS, "Accept": "text/html,*/*;q=0.8"},
    follow_redirects=True,
    timeout=15
) as client:
    home = client.get("https://www.naukri.com/")
    print(f"  Homepage: {home.status_code}, cookies: {list(client.cookies.keys())}")

    # Step 2: Try API with session cookies
    print("\nStep 2: Calling search API with session cookies...")
    endpoints = [
        "https://www.naukri.com/jobapi/v3/search",
        "https://www.naukri.com/jobapi/v4/search",
        "https://www.naukri.com/jobapi/v2/search",
    ]
    for ep in endpoints:
        resp = client.get(ep, params={
            "noOfResults": 5, "urlType": "search_by_keyword",
            "searchType": "adv", "keyword": "software engineer",
            "location": "Chennai", "experience": 0, "jobAge": 15, "pageNo": 1
        })
        print(f"  {ep}: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobDetails", [])
            print(f"    Got {len(jobs)} jobs!")
            if jobs:
                print(f"    First: {jobs[0].get('title')} @ {jobs[0].get('companyName')}")
            break
        else:
            print(f"    Response: {resp.text[:200]}")
