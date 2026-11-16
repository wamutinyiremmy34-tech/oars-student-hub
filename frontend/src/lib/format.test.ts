import { describe, expect, it } from "vitest";
import { fileKind, formatBytes, formatUgx } from "@/lib/format";

describe("format", () => {
  it("formats shillings as whole numbers with separators", () => {
    expect(formatUgx(5000)).toBe("UGX 5,000");
    expect(formatUgx(1250000)).toBe("UGX 1,250,000");
  });
  it("formats file sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
  it("names file kinds from MIME types and falls back safely", () => {
    expect(fileKind("application/pdf")).toBe("PDF");
    expect(fileKind("application/x-unknown")).toBe("FILE");
  });
});
