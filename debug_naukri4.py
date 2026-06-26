import sys, re, httpx
sys.stdout.reconfigure(encoding="utf-8")

r = httpx.get(
    "https://www.naukri.com/software-engineer-jobs-in-chennai",
    params={"experience": "0", "jobAge": "15"},
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
    },
    timeout=15,
    follow_redirects=True,
)
print("Status:", r.status_code, "Length:", len(r.text))

# Search for any job titles in the HTML
html = r.text
titles_pattern = re.findall(r'"title"\s*:\s*"([^"]{5,80})"', html[:80000])
print("'title' fields found:", len(titles_pattern), "->", titles_pattern[:5])

company_pattern = re.findall(r'"companyName"\s*:\s*"([^"]{2,60})"', html[:80000])
print("'companyName' fields found:", len(company_pattern), "->", company_pattern[:5])

jd_pattern = re.findall(r'"jdURL"\s*:\s*"([^"]+)"', html[:80000])
print("'jdURL' fields found:", len(jd_pattern), "->", jd_pattern[:3])

# Check if page is SSR or CSR
print("\nSSR check:")
print("  Has __NEXT_DATA__:", "__NEXT_DATA__" in html)
print("  Has 'jobDetails':", "jobDetails" in html)
print("  Has 'SoftwareEngineer':", "SoftwareEngineer" in html or "software-engineer" in html.lower())
print("\nFirst 800 chars of body:")
print(html[:800])
