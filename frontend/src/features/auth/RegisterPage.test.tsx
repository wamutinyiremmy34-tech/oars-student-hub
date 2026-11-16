import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, jsonResponse, mockApi, ok, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

const INSTITUTIONS = [
  { id: "i-1", name: "Makerere University", code: "MAK", slug: "makerere-university" },
  { id: "i-2", name: "Kyambogo University", code: "KYU", slug: "kyambogo-university" },
];
const REGISTERED = {
  user: {
    id: "u-9", email: "amina@example.com", full_name: "Amina Nakato", phone: null,
    status: "ACTIVE", email_verified: false, created_at: "2026-10-03T08:00:00Z",
  },
};

const routes = () => ({
  ...signedOutApi(),
  "GET /institutions": () => ok(INSTITUTIONS),
});

async function fillValid(user = userEvent.setup()) {
  await user.type(await screen.findByLabelText("Full name"), "Amina Nakato");
  await user.type(screen.getByLabelText("Email"), "amina@example.com");
  await user.selectOptions(await screen.findByLabelText("University"), "i-1");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
  await user.type(screen.getByLabelText("Repeat password"), "correct-horse-battery");
  return user;
}

describe("RegisterPage", () => {
  it("loads universities from the API into the form", async () => {
    mockApi(routes());
    renderApp("/register");
    expect(await screen.findByRole("option", { name: "Makerere University" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Kyambogo University" })).toBeInTheDocument();
  });

  it("validates fields locally and never sends invalid data", async () => {
    const api = mockApi(routes());
    renderApp("/register");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Password"), "short");
    await user.type(screen.getByLabelText("Repeat password"), "different");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Use at least 10 characters")).toBeInTheDocument();
    expect(screen.getByText("Enter your full name")).toBeInTheDocument();
    expect(screen.getByText("Choose your university")).toBeInTheDocument();
    expect(api.callsTo("POST /auth/register")).toHaveLength(0);
  });

  it("flags mismatched passwords", async () => {
    mockApi(routes());
    renderApp("/register");
    const user = await fillValid();
    await user.clear(screen.getByLabelText("Repeat password"));
    await user.type(screen.getByLabelText("Repeat password"), "something-else-entirely");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
  });

  it("submits the right payload (no confirm field, empty optionals omitted) and confirms", async () => {
    const api = mockApi({ ...routes(), "POST /auth/register": () => ok(REGISTERED, 201) });
    renderApp("/register");
    const user = await fillValid();
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("heading", { name: "Account created" })).toBeInTheDocument();
    expect(api.callsTo("POST /auth/register")[0]?.body).toEqual({
      email: "amina@example.com",
      password: "correct-horse-battery",
      full_name: "Amina Nakato",
      institution_id: "i-1",
    });
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");
  });

  it("shows a duplicate-email error on the email field", async () => {
    mockApi({ ...routes(), "POST /auth/register": () => apiError(409, "email_taken") });
    renderApp("/register");
    const user = await fillValid();
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("An account with this email already exists.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("maps server-side validation errors onto fields", async () => {
    mockApi({
      ...routes(),
      "POST /auth/register": () =>
        jsonResponse(
          {
            error: {
              code: "validation_error",
              message: "bad",
              details: [{ field: "body.phone", message: "Server says no" }],
              request_id: "r",
            },
          },
          422,
        ),
    });
    renderApp("/register");
    const user = await fillValid();
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Server says no")).toBeInTheDocument();
  });

  it("offers a retry when universities fail to load", async () => {
    mockApi({ ...signedOutApi(), "GET /institutions": () => apiError(503, "service_unavailable") });
    renderApp("/register");
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
