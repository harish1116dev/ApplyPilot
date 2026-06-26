"""Debug Naukri HTML to find correct selectors."""
import sys
import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()
from utils.browser import new_browser

url = "https://www.naukri.com/full-stack-developer-jobs-in-chennai?experience=0&jobAge=7"
print(f"Fetching: {url}")

pw, browser, context = new_browser(headless=True)
page = context.new_page()
try:
    page.goto(url, timeout=20000, wait_until="domcontentloaded")
    import time; time.sleep(4)
    page.evaluate("window.scrollTo(0, 600)")
    time.sleep(2)

    # Try all known selectors and report counts
    selectors = [
        "article[data-jobid]",
        "div.srp-jobtuple-wrapper",
        "div.jobTupleHeader",
        "[class*='jobtuple']",
        "[class*='jobTuple']",
        "article.jobTuple",
        "div[data-job-id]",
        "li[data-job-id]",
        "div.job-post",
        "[class*='job-post']",
        "[class*='srp-jobtuple']",
        "div[type='jobTuple']",
        "div.cust-job-tuple",
        "[class*='cust-job']",
        "a[class*='title'][href*='naukri']",
        "div[class*='row1']",
        "li.jobTuple",
        "section.listContainer li",
        "div#listContainer li",
        "div.list li",
    ]

    print("\nSelector counts:")
    found_any = False
    for sel in selectors:
        try:
            count = len(page.query_selector_all(sel))
            if count > 0:
                print(f"  [OK] {sel}: {count}")
                found_any = True
            else:
                print(f"  [ ] {sel}: 0")
        except Exception as e:
            print(f"  [ERR] {sel}: {e}")

    # Dump body HTML to find class names
    html = page.evaluate("document.body.innerHTML")
    print(f"\nPage HTML length: {len(html)} chars")
    
    if len(html) < 5000:
        print("\n[WARNING] Very short page - likely blocked or CAPTCHA")
        print(html[:1000])
    else:
        # Find class patterns around 'tuple' or 'job'
        import re
        classes = re.findall(r'class="([^"]*(?:tuple|job-list|jobtuple|srp|cust-job)[^"]*)"', html[:50000], re.IGNORECASE)
        unique_classes = list(dict.fromkeys(classes))[:30]
        print("\nRelevant CSS classes found in page:")
        for c in unique_classes:
            print(f"  {c}")
        
        # Also check page title
        title = page.title()
        print(f"\nPage title: {title}")

finally:
    page.close(); context.close(); browser.close(); pw.stop()
