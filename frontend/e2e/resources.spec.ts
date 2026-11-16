import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API } from "./env";

const PASSWORD = "Demo-password-123";
const STUDENT = "student@demo.oars.test";
const ADMIN = "admin@demo.oars.test";
const FREE_TITLE = "Introduction to Programming - Lecture Notes";
const PREMIUM_TITLE = "Data Structures - Past Paper 2024";

async function apiLogin(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/auth/login`, { data: { email, password: PASSWORD } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).data.access_token as string;
}

async function uiLogin(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
}

async function resourceId(request: APIRequestContext, title: string): Promise<string> {
  const response = await request.get(`${API}/search`, { params: { q: title.split(" - ")[0] ?? title } });
  const items = (await response.json()).data as { id: string; title: string }[];
  const match = items.find((item) => item.title === title);
  expect(match, `${title} should be seeded`).toBeTruthy();
  return match!.id;
}

test("a visitor can find and open a free resource but must sign in to download it", async ({ page }) => {
  await page.goto("/resources");
  await page.getByLabel(/search notes/i).fill("programming");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: FREE_TITLE }).click();

  await expect(page.getByRole("heading", { name: FREE_TITLE })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in to download" })).toBeVisible();
  await expect(page.getByRole("button", { name: /download/i })).toHaveCount(0);
});

test("a signed-in student downloads a free resource", async ({ page }) => {
  await uiLogin(page, STUDENT);
  await page.goto("/resources");
  await page.getByRole("link", { name: FREE_TITLE }).click();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /download/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
});

test("a premium resource is refused without an entitlement and allowed after an admin grants it", async ({ page, request }) => {
  const id = await resourceId(request, PREMIUM_TITLE);
  const adminToken = await apiLogin(request, ADMIN);
  const studentToken = await apiLogin(request, STUDENT);
  const me = await request.get(`${API}/me`, { headers: { Authorization: `Bearer ${studentToken}` } });
  const studentId = (await me.json()).data.user.id as string;
  const admin = { Authorization: `Bearer ${adminToken}` };

  // start from a known state (ignore "nothing to revoke")
  await request.delete(`${API}/resources/${id}/entitlements/${studentId}`, { headers: admin });

  await uiLogin(page, STUDENT);
  await page.goto(`/resources/${id}`);
  await expect(page.getByRole("heading", { name: "Premium resource" })).toBeVisible();
  await expect(page.getByRole("button", { name: /download/i })).toHaveCount(0);

  // The backend, not the page, enforces this: a direct API call is refused too.
  const refused = await request.post(`${API}/resources/${id}/download`, { headers: { Authorization: `Bearer ${studentToken}` } });
  expect(refused.status()).toBe(403);

  const granted = await request.post(`${API}/resources/${id}/entitlements`, { headers: admin, data: { user_id: studentId } });
  expect(granted.status()).toBe(201);

  await page.reload();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /download/i }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(/\.pdf$/);
});

test("unpublished resources are not visible to the public", async ({ request }) => {
  const response = await request.get(`${API}/resources/00000000-0000-0000-0000-000000000042`);
  expect(response.status()).toBe(404);
});
