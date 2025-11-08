from playwright.sync_api import sync_playwright

# We'd load these from a file, not hard-code them
my_cookies = [
    { "name": "sessionid", "value": "abc123xyz789", "domain": ".linkedin.com", "path": "/" }
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    
    # 1. Create the context FIRST
    context = browser.new_context()
    
    # 2. Load the cookies into the context
    context.add_cookies(my_cookies)
    
    # 3. Create a NEW page *from that context*
    page = context.new_page()
    
    # --- From here, it's the same as before ---
    
    # 4. Now we navigate (we'll appear logged in)
    page.goto("https://www.linkedin.com/feed/")
    
    # 5. We wait for the dynamic content
    feed_locator = page.locator('div#main-feed')
    feed_locator.wait_for(state='visible')
    
    # 6. We scrape the content
    html_content = feed_locator.inner_html()
    
    browser.close()

# And now we have our HTML_content, ready for BeautifulSoup
print(html_content)