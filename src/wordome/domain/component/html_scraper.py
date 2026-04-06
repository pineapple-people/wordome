from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("https://www.amazon.com/product-reviews/B09YL81PWH/ref=cm_cr_dp_d_show_all_btm?ie=UTF8")

    # scroll to trigger review loading
    #page.mouse.wheel(0, 2000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    try:
        page.wait_for_selector("[data-hook='review']", timeout=10000)
        print("✅ Reviews loaded")
    except:
        print("⚠️ Reviews not found")

    content = page.content()
    assert 'data-hook="review"' in content, "❌ Reviews not found in HTML!"

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "html.parser")

    reviews = soup.select("[data-hook='review']")
    print(f"Found {len(reviews)} reviews")

    browser.close()