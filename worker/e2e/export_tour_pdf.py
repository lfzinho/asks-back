"""Export public/tour.html to a PDF, one page per slide (1920x1080).

Run: cd worker && uv run playwright install chromium && uv run python e2e/export_tour_pdf.py
Output: ../asksback-pitch.pdf
"""
import http.server
import io
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
OUT = ROOT / "asksback-pitch.pdf"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(PUBLIC), **k)

    def do_GET(self):
        if self.path.startswith("/__/firebase/init.json"):  # normally served by Firebase Hosting
            body = b'{"projectId":"demo-asksback","apiKey":"x","appId":"x"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *a, **k):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/tour.html"

pages = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(url)
    page.wait_for_selector(".slide.active")
    total = page.locator(".slide").count()
    for i in range(1, total + 1):
        page.evaluate(f"location.hash = '#{i}'")
        page.wait_for_timeout(2500)  # let the entrance animations finish
        pages.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB"))
    browser.close()

pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=144)
print(f"{len(pages)} slides -> {OUT}")
