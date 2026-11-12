"""Local conversion server for the PDF Converter page.

Serves index.html and a single endpoint:
    POST /api/convert?to=<ext>   body = raw file bytes, header X-Filename = original name
Responds with the converted file. Listens on 127.0.0.1 only: nothing leaves this machine.

Engines:
    LibreOffice  - Word / Excel / PowerPoint / OpenDocument / RTF / TXT / HTML conversions
    pdf2docx     - PDF -> DOCX
    Pillow       - image <-> image (incl. HEIC, TIFF) and image -> PDF
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8765"))
MAX_BYTES = 200 * 1024 * 1024
SOFFICE_TIMEOUT = 180

SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
# A dedicated LibreOffice profile so we never fight with a LibreOffice window you have open.
LO_PROFILE = Path(tempfile.gettempdir()) / "pdf-converter-lo-profile"
lo_lock = threading.Lock()  # LibreOffice headless handles one conversion at a time.

# ---- What converts to what ------------------------------------------------------------

GROUPS = {
    "document": {"in": ["docx", "doc", "odt", "rtf", "txt", "html", "htm"],
                 "out": ["pdf", "docx", "odt", "rtf", "txt", "html"]},
    "spreadsheet": {"in": ["xlsx", "xls", "ods", "csv"],
                    "out": ["pdf", "xlsx", "ods", "csv"]},
    "presentation": {"in": ["pptx", "ppt", "odp", "key"],
                     "out": ["pdf", "pptx", "odp"]},
    "pdf": {"in": ["pdf"], "out": ["docx"]},  # pdf -> png/jpg/txt happen in the browser
    "image": {"in": ["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif"],
              "out": ["png", "jpg", "webp", "gif", "bmp", "tiff", "pdf"]},
}

LO_FILTERS = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "txt:Text (encoded):UTF8",
    "html": "html:HTML (StarWriter)",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "ods": "ods",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1",
    "pptx": "pptx:Impress MS PowerPoint 2007 XML",
    "odp": "odp",
}

MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "rtf": "application/rtf", "txt": "text/plain; charset=utf-8", "html": "text/html; charset=utf-8",
    "csv": "text/csv; charset=utf-8", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
    "gif": "image/gif", "bmp": "image/bmp", "tiff": "image/tiff",
}


class ConversionError(Exception):
    pass


def group_of(ext):
    return next((g for g, spec in GROUPS.items() if ext in spec["in"]), None)


def safe_name(name):
    name = os.path.basename(name or "file")
    name = re.sub(r"[^\w.\- ]+", "_", name).strip() or "file"
    return name[:150]


# ---- Engines ----------------------------------------------------------------------------

def convert_libreoffice(src: Path, target: str, workdir: Path) -> Path:
    if not Path(SOFFICE).exists():
        raise ConversionError("LibreOffice is not installed.")
    cmd = [SOFFICE, f"-env:UserInstallation=file://{LO_PROFILE}", "--headless", "--norestore",
           "--convert-to", LO_FILTERS[target], "--outdir", str(workdir / "out")]
    if src.suffix.lower() in (".html", ".htm"):
        cmd.append("--infilter=HTML (StarWriter)")  # open HTML as a Writer document, not a web page
    cmd.append(str(src))
    with lo_lock:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SOFFICE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ConversionError("LibreOffice took too long on this file.")
    outs = list((workdir / "out").glob("*"))
    if not outs:
        detail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["no output"]
        raise ConversionError(f"LibreOffice could not convert this file ({detail[0]}).")
    return outs[0]


def convert_pdf_to_docx(src: Path, workdir: Path) -> Path:
    from pdf2docx import Converter
    out = workdir / (src.stem + ".docx")
    cv = Converter(str(src))
    try:
        cv.convert(str(out))
    finally:
        cv.close()
    return out


def convert_image(src: Path, target: str, workdir: Path) -> Path:
    from PIL import Image, ImageOps
    import pillow_heif
    pillow_heif.register_heif_opener()
    out = workdir / f"{src.stem}.{target}"
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # respect phone photo rotation
        if target in ("jpg", "pdf", "bmp") and im.mode not in ("RGB", "L"):
            # These formats have no transparency: flatten onto white.
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        fmt = {"jpg": "JPEG", "tiff": "TIFF"}.get(target, target.upper())
        kwargs = {"quality": 92} if target in ("jpg", "webp") else {}
        if target == "pdf":
            kwargs = {"resolution": 72.0}
        im.save(out, fmt, **kwargs)
    return out


def convert(data: bytes, filename: str, target: str):
    src_ext = Path(filename).suffix.lower().lstrip(".")
    group = group_of(src_ext)
    if not group:
        raise ConversionError(f"Unsupported file type: .{src_ext or '?'}")
    if target not in GROUPS[group]["out"]:
        raise ConversionError(f"Can't convert .{src_ext} to .{target}.")
    norm = {"jpeg": "jpg", "htm": "html", "tif": "tiff", "heif": "heic"}
    if norm.get(src_ext, src_ext) == target:
        raise ConversionError(f"That file is already .{target}.")

    with tempfile.TemporaryDirectory(prefix="pdfconv-") as tmp:
        workdir = Path(tmp)
        src = workdir / safe_name(filename)
        src.write_bytes(data)
        if group == "image":
            out = convert_image(src, target, workdir)
        elif group == "pdf":
            out = convert_pdf_to_docx(src, workdir)
        else:
            out = convert_libreoffice(src, target, workdir)
        return out.read_bytes(), f"{Path(filename).stem}.{target}"


# ---- HTTP -------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/formats":
            self.send_json(200, {"groups": GROUPS, "libreoffice": Path(SOFFICE).exists()})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/api/convert":
            return self.send_json(404, {"error": "Not found"})
        # Only accept requests from this page, not from other websites you have open.
        origin = self.headers.get("Origin")
        if origin and not re.fullmatch(r"http://(localhost|127\.0\.0\.1):%d" % PORT, origin):
            return self.send_json(403, {"error": "Forbidden origin"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self.send_json(400, {"error": "Empty file."})
        if length > MAX_BYTES:
            return self.send_json(413, {"error": "File is larger than 200 MB."})
        target = (parse_qs(url.query).get("to") or [""])[0].lower()
        filename = self.headers.get("X-Filename", "file")
        try:
            from urllib.parse import unquote
            filename = unquote(filename)
            data = self.rfile.read(length)
            out, out_name = convert(data, filename, target)
        except ConversionError as e:
            return self.send_json(422, {"error": str(e)})
        except Exception as e:  # unexpected: report, keep serving
            self.log_message("convert failed: %r", e)
            return self.send_json(500, {"error": f"Conversion failed: {e}"})
        ext = out_name.rsplit(".", 1)[-1]
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(out)))
        self.send_header("X-Filename", out_name.encode("ascii", "replace").decode())
        self.end_headers()
        self.wfile.write(out)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PDF Converter running at http://localhost:{PORT}  (LibreOffice: {Path(SOFFICE).exists()})", flush=True)
    server.serve_forever()
