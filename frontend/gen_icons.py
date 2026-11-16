"""Generate minimal but valid PNG icons for the OARS PWA."""
import struct
import zlib

BRAND_RGB = (91, 33, 182)   # #5B21B6 — OARS primary colour


def make_png(size: int, rgb: tuple[int, int, int]) -> bytes:
    r, g, b = rgb

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)

    # Build raw scanlines: filter byte 0 (None) + RGB pixels
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter byte
        for x in range(size):
            rows.extend([r, g, b])

    compressed = zlib.compress(bytes(rows), level=9)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


BASE = "c:/Users/REMMY.W/Downloads/oars-student-solutions-phases1-9/oars-student-solutions/frontend/public"

for size in (192, 512):
    data = make_png(size, BRAND_RGB)
    path = f"{BASE}/icon-{size}.png"
    with open(path, "wb") as f:
        f.write(data)
    print(f"Created {path} ({len(data)} bytes)")
