const NUMBER = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Money is integer Ugandan shillings: no decimals, never floating point. */
export function formatUgx(amount: number): string {
  return `UGX ${NUMBER.format(amount)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileKind(mime: string): string {
  const kinds: Record<string, string> = {
    "application/pdf": "PDF",
    "image/png": "PNG",
    "image/jpeg": "JPG",
    "text/plain": "TXT",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  };
  return kinds[mime] ?? "FILE";
}
