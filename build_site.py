"""Wrap web/dashboard.html into a standalone site/index.html (for GitHub Pages)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
body = (ROOT / "web" / "dashboard.html").read_text()
page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}</style>\n'
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n")
(ROOT / "site").mkdir(exist_ok=True)
(ROOT / "site" / "index.html").write_text(page)
print("wrote site/index.html")
