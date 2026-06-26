"""Debug Naukri HTML structure using httpx (no browser)."""
import sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
}

url = "https://www.naukri.com/jobs-in-chennai-0"
params = {"q": "software engineer", "experience": "0", "jobAge": "15"}

print(f"Fetching: {url}")
r = httpx.get(url, params=params, headers=HEADERS, timeout=15, follow_redirects=True)
print(f"Status: {r.status_code}  Length: {len(r.text)}")

html = r.text
soup = BeautifulSoup(html, "lxml")

# Check for __NEXT_DATA__ (Next.js SSR data)
next_data = soup.find("script", id="__NEXT_DATA__")
if next_data and next_data.string:
    try:
        data = json.loads(next_data.string)
        props = data.get("props", {}).get("pageProps", {})
        print(f"\nFound __NEXT_DATA__! pageProps keys: {list(props.keys())[:15]}")

        # Try to find job listings inside pageProps
        def find_jobs_in(obj, depth=0):
            if depth > 5:
                return
            if isinstance(obj, list) and len(obj) > 0:
                first = obj[0]
                if isinstance(first, dict) and any(k in first for k in ["title", "jobId", "companyName"]):
                    print(f"\n[!] Found job list at depth {depth}! Count: {len(obj)}")
                    print(f"    First job keys: {list(first.keys())}")
                    print(f"    Sample: title={first.get('title')}, company={first.get('companyName')}")
                    return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    find_jobs_in(v, depth+1)

        find_jobs_in(props)
    except Exception as e:
        print(f"Parse error: {e}")
else:
    print("\nNo __NEXT_DATA__ found")

# Check job-related class patterns
print("\n=== Job-related CSS classes in HTML ===")
classes = re.findall(r'class="([^"]+)"', html[:80000])
job_classes = [c for c in classes if any(k in c.lower() for k in ["job", "srp", "result", "tuple", "card", "listing"])]
unique_job_classes = list(dict.fromkeys(job_classes))[:25]
for c in unique_job_classes:
    print(f"  {c}")

# Check if there's JSON embedded for job data
print("\n=== JSON-LD / embedded job data ===")
scripts = soup.find_all("script")
for s in scripts:
    if s.string and ("jobTitle" in s.string or "hiringOrganization" in s.string):
        print("Found JSON-LD job data!")
        print(s.string[:500])
        break
    if s.string and "jobDetails" in s.string:
        print("Found jobDetails in script!")
        idx = s.string.find("jobDetails")
        print(s.string[max(0,idx-50):idx+300])
        break
