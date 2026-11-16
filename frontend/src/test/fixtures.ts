const VERSION = {
  id: "v-1", version_number: 1, filename: "notes.pdf", mime_type: "application/pdf",
  size_bytes: 2048, is_current: true, changelog: null, created_at: "2026-10-01T08:00:00Z",
};

export const CATEGORY = { id: "c-1", name: "Notes", slug: "notes", description: null };
export const INSTITUTIONS = [
  { id: "i-1", name: "Makerere University", code: "MAK", slug: "makerere-university" },
  { id: "i-2", name: "Kyambogo University", code: "KYU", slug: "kyambogo-university" },
];
export const CATEGORIES = [CATEGORY, { id: "c-2", name: "Past papers", slug: "past-papers", description: null }];

export function summary(overrides: Record<string, unknown> = {}) {
  return {
    id: "r-1", title: "Calculus Lecture Notes", excerpt: "Limits and integrals", access_type: "FREE",
    price_ugx: null, status: "PUBLISHED", institution_id: "i-1", institution_name: "Makerere University",
    category: CATEGORY, tags: ["calculus", "math"], courses: [{ id: "co-1", code: "MTH1101", title: "Calculus" }],
    academic_year: 2023, provider_name: "Demo Provider", published_at: "2026-10-01T08:00:00Z",
    file: VERSION, is_bookmarked: false, ...overrides,
  };
}

export function viewer(overrides: Record<string, unknown> = {}) {
  return {
    is_owner: false, can_download: true, download_block_reason: null, is_bookmarked: false,
    can_review: false, can_publish: false, entitlement_status: null, ...overrides,
  };
}

export function detail(overrides: Record<string, unknown> = {}, viewerOverrides: Record<string, unknown> = {}) {
  return {
    ...summary(), description: "Full description of the notes.", preview_text: null, versions: [],
    latest_review: null, ...overrides, viewer: viewer(viewerOverrides),
  };
}

// ---------------------------------------------------------------- printing and payments
export const SHOP = {
  id: "s-1", institution_id: "i-1", name: "Main Library Print Shop", location: "Ground floor",
  is_active: true, pay_on_pickup_enabled: true,
};

export const RULES = [
  { id: "r1", kind: "PER_PAGE", paper_size: "A4", color_mode: "BW", duplex: null, option_key: null, amount_ugx: 50, is_active: true },
  { id: "r2", kind: "PER_PAGE", paper_size: "A4", color_mode: "COLOR", duplex: null, option_key: null, amount_ugx: 300, is_active: true },
  { id: "r3", kind: "PER_COPY", paper_size: null, color_mode: null, duplex: null, option_key: "staple", amount_ugx: 100, is_active: true },
];

export const DOC = { id: "d-1", filename: "notes.pdf", page_count: 3, size_bytes: 2048 };

export const QUOTE = {
  shop_id: "s-1", currency: "UGX", total_ugx: 150,
  items: [{
    document_id: "d-1", filename: "notes.pdf", page_count: 3, copies: 1, paper_size: "A4", color_mode: "BW",
    duplex: false, options: {}, unit_price_ugx: 50, line_total_ugx: 150,
  }],
  order_lines: [],
};

export function order(overrides: Record<string, unknown> = {}) {
  return {
    id: "o-1", status: "SUBMITTED", payment_method: "PAY_ON_PICKUP", payment_status: "UNPAID", total_ugx: 300,
    currency: "UGX", shop: SHOP,
    items: [{
      id: "it-1", position: 0, filename: "notes.pdf", page_count: 3, copies: 2, paper_size: "A4", color_mode: "BW",
      duplex: false, options: {}, unit_price_ugx: 50, line_total_ugx: 300, document_available: true,
    }],
    history: [{ from_status: null, to_status: "SUBMITTED", note: null, created_at: "2026-10-08T08:00:00Z" }],
    payment: null, note: null, reject_reason: null, cancel_reason: null, pickup_code: null,
    can_cancel: true, awaiting_payment: false, created_at: "2026-10-08T08:00:00Z",
    student_name: null, retention_hold: null, ...overrides,
  };
}

export function orderSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: "o-1", status: "SUBMITTED", payment_method: "PAY_ON_PICKUP", payment_status: "UNPAID", total_ugx: 300,
    shop_name: "Main Library Print Shop", item_count: 1, created_at: "2026-10-08T08:00:00Z", student_name: null,
    ...overrides,
  };
}

export function payment(overrides: Record<string, unknown> = {}) {
  return {
    id: "p-1", purpose: "PRINT_ORDER", status: "PENDING", method: "ONLINE", provider: "fake", amount_ugx: 300,
    currency: "UGX", checkout_url: "/pay/fake/p-1", print_order_id: "o-1", resource_id: null, failure_reason: null,
    created_at: "2026-10-08T08:00:00Z", paid_at: null, ...overrides,
  };
}
