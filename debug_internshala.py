import sys, httpx
sys.stdout.reconfigure(encoding="utf-8")
from bs4 import BeautifulSoup

r = httpx.get(
    "https://internshala.com/jobs/software-engineer-jobs-in-chennai",
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,*/*",
    },
    timeout=20, follow_redirects=True,
)
soup = BeautifulSoup(r.text, "lxml")

# Find and print a sample card's full HTML
cards = soup.select("div[class*='individual_internship']")
print(f"Total individual_internship cards: {len(cards)}")

if cards:
    c = cards[0]
    print("\n=== First card HTML ===")
    print(c.prettify()[:2000])

# Also try container
container = soup.select_one("div#internship_list_container_1, div[id*='internship_list']")
if container:
    print(f"\nContainer found: {container.get('id')} children: {len(container.find_all())}")
else:
    print("\nNo internship_list_container found by id")

# Find all anchors with jobs/detail
job_links = soup.select("a[href*='/jobs/detail']")
print(f"\nJob detail links: {len(job_links)}")
for a in job_links[:5]:
    print(f"  text='{a.get_text(strip=True)[:50]}' href='{a.get('href','')[:80]}'")

# Find all anchors with job-title-href class
title_links = soup.select("a.job-title-href")
print(f"\na.job-title-href links: {len(title_links)}")
for a in title_links[:5]:
    print(f"  '{a.get_text(strip=True)[:60]}'")
