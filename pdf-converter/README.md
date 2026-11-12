# PDF Converter

Convert documents, spreadsheets, slides, PDFs and images. Drop files in, pick a format, done.
Files are processed in your browser and never uploaded.

## What it converts

| From | To |
|---|---|
| Word (.docx) | PDF, HTML, TXT |
| TXT, Markdown, HTML | PDF, Word, HTML, TXT |
| Excel (.xlsx, .xls), .ods, .csv | PDF, Excel, ODS, CSV, HTML |
| PowerPoint (.pptx) | PDF, Word, TXT, HTML (slide text only) |
| PDF | Word, TXT, PNG, JPG |
| Images: PNG, JPG, WebP, GIF, BMP, TIFF, HEIC | PDF, PNG, JPG, WebP, GIF, BMP, TIFF |

Drop several files to convert them together, or combine any mix of them into one PDF.

## Desktop mode (optional, higher fidelity)

The browser version is good for most files, but Word → PDF and PowerPoint → PDF can't match
Office's exact layout, and some formats (.doc, .rtf, .odt, .ppt, .odp, Keynote) need a real office suite.
Run the page with the bundled local server and it automatically switches to LibreOffice for those:

```bash
brew install --cask libreoffice
python3 -m venv .venv && .venv/bin/pip install pdf2docx pymupdf pillow pillow-heif
.venv/bin/python server.py
```

Then open http://localhost:8765. The server only listens on your own computer.
