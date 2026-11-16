import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { INSTITUTIONS } from "@/test/fixtures";
import { mockApi, ok, okPage, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

const FACULTY = { id: "f-1", institution_id: "i-1", name: "College of Computing", kind: "COLLEGE", code: null };
const PROGRAM = { id: "p-1", institution_id: "i-1", faculty_id: "f-1", name: "BSc Computer Science", level: "BACHELORS", code: null };
const COURSE = { id: "co-1", institution_id: "i-1", faculty_id: "f-1", code: "CSC1201", title: "Data Structures" };

const routes = () => ({
  ...signedOutApi(),
  "GET /institutions": () => ok(INSTITUTIONS),
  "GET /faculties": () => ok([FACULTY]),
  "GET /programs": () => ok([PROGRAM]),
  "GET /courses": () => okPage([COURSE], { page_size: 20 }),
});

describe("CatalogPage", () => {
  it("asks for a university before loading anything else", async () => {
    const api = mockApi(routes());
    renderApp("/catalog");
    expect(await screen.findByText("Choose a university to see its courses.")).toBeInTheDocument();
    expect(api.callsTo("GET /courses")).toHaveLength(0);
    expect(api.callsTo("GET /faculties")).toHaveLength(0);
  });

  it("walks university → faculty → program → courses and links to resources", async () => {
    const api = mockApi(routes());
    renderApp("/catalog");
    const user = userEvent.setup();
    const uniSelect = await screen.findByLabelText("University");
    await screen.findByText("Makerere University"); // wait for options to load
    await user.selectOptions(uniSelect, "i-1");

    expect(await screen.findByText("CSC1201")).toBeInTheDocument();
    expect(api.callsTo("GET /faculties")[0]?.search.get("institution_id")).toBe("i-1");
    // the label uses the institution's own terminology (here: a college)
    expect(await screen.findByLabelText(/faculty \/ school \(college\)/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/faculty \/ school/i), "f-1");
    await user.selectOptions(screen.getByLabelText("Program"), "p-1");
    await waitFor(() => {
      const last = api.callsTo("GET /courses").at(-1)!.search;
      expect(last.get("faculty_id")).toBe("f-1");
      expect(last.get("program_id")).toBe("p-1");
    });
    expect(screen.getByRole("link", { name: "Find resources" })).toHaveAttribute("href", "/resources?course_id=co-1&institution_id=i-1");
  });
});
