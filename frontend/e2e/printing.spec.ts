import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Demo-password-123";
const STUDENT = "student@demo.oars.test";
const OPERATOR = "operator@demo.oars.test";

/** A structurally valid PDF with `pages` blank pages (the server counts pages itself to price the order). */
function pdf(pages: number): Buffer {
  const kids = Array.from({ length: pages }, (_, i) => `${3 + i} 0 R`).join(" ");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Kids [${kids}] /Count ${pages} >>`,
    ...Array.from({ length: pages }, () => "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"),
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
}

/** Student: choose the demo shop, upload a 3-page PDF, review the server's price. */
async function prepareOrder(page: Page) {
  await page.goto("/print");
  await page.getByLabel("Print shop").selectOption({ label: "Main Library Print Shop (Ground floor, Main Library)" });
  await page.getByLabel(/upload a pdf or image/i).setInputFiles({ name: "lecture.pdf", mimeType: "application/pdf", buffer: pdf(3) });
  await expect(page.getByText(/lecture\.pdf · 3 pages/)).toBeVisible();
  await page.getByRole("button", { name: "Review price" }).click();
  await expect(page.getByText("UGX 150").first()).toBeVisible(); // 3 pages x UGX 50, calculated by the server
}

test("pay-on-pickup: order, operator processes it, cash is recorded, pickup is confirmed", async ({ browser }) => {
  const student = await (await browser.newContext()).newPage();
  await signIn(student, STUDENT);
  await prepareOrder(student);
  await student.getByLabel("Pay when I collect it").check();
  await student.getByRole("button", { name: "Place order" }).click();
  await expect(student.getByText("Waiting for the shop").first()).toBeVisible();
  const orderUrl = student.url();

  const operator = await (await browser.newContext()).newPage();
  await signIn(operator, OPERATOR);
  await operator.goto(orderUrl.replace("/print/orders/", "/operator/orders/"));
  await expect(operator.getByRole("heading", { name: "Demo Student" })).toBeVisible();
  await operator.getByRole("button", { name: "Accept" }).click();
  await operator.getByRole("button", { name: "Start printing" }).click();
  await operator.getByRole("button", { name: "Mark ready for pickup" }).click();
  await expect(operator.getByRole("button", { name: "Record cash payment" })).toBeVisible();

  await student.goto(orderUrl);
  const code = (await student.getByLabel("Pickup code").textContent())?.trim() ?? "";
  expect(code).toHaveLength(6); // only the student ever sees this

  await operator.getByRole("button", { name: "Record cash payment" }).click();
  await expect(operator.getByText("Paid").first()).toBeVisible();
  await operator.getByLabel("Customer's pickup code").fill(code);
  await operator.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(operator.getByText("This order is closed.")).toBeVisible();

  await student.reload();
  await expect(student.getByText("Completed").first()).toBeVisible();
});

test("online payment with the FakeProvider: the order only proceeds after the server confirms payment", async ({ browser }) => {
  const student = await (await browser.newContext()).newPage();
  await signIn(student, STUDENT);
  await prepareOrder(student);
  await student.getByLabel("Pay online now").check();
  await student.getByRole("button", { name: "Place order and pay" }).click();

  await expect(student.getByText(/development checkout/i)).toBeVisible();

  const operator = await (await browser.newContext()).newPage();
  await signIn(operator, OPERATOR);
  await operator.goto("/operator");
  await operator.getByRole("link", { name: "Open order" }).last().click(); // the queue is oldest-first, so the newest is last
  await expect(operator.getByRole("button", { name: "Accept" })).toBeDisabled(); // not paid yet

  await student.getByRole("button", { name: "Pay now" }).click();
  await expect(student.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();

  await operator.reload();
  await expect(operator.getByRole("button", { name: "Accept" })).toBeEnabled();
  await operator.getByRole("button", { name: "Accept" }).click();
  await operator.getByRole("button", { name: "Start printing" }).click();
  await operator.getByRole("button", { name: "Mark ready for pickup" }).click();

  await student.getByRole("link", { name: "Go to my order" }).click();
  const code = (await student.getByLabel("Pickup code").textContent())?.trim() ?? "";
  await operator.getByLabel("Customer's pickup code").fill(code);
  await operator.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(operator.getByText("This order is closed.")).toBeVisible();
});

test("a student cannot open the operator screens or another shop's data", async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto("/operator");
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
});
