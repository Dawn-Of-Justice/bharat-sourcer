"""Isolated text extraction for bounded PDF source documents (no OCR or JavaScript)."""

import io
import sys


def main():
    # Cloud Run/Linux enforces a process memory ceiling as well as the parent's timeout.
    if sys.platform != "win32":
        import resource

        limit = 96 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(2_000_001)
    if len(data) > 2_000_000 or not data.startswith(b"%PDF-"):
        raise ValueError("Unsupported PDF")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")
    text = ""
    for page in reader.pages[:10]:
        text += (page.extract_text() or "") + "\n"
        if len(text) >= 20000:
            break
    sys.stdout.buffer.write(text[:20000].encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
