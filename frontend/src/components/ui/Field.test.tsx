import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Alert } from "@/components/ui/Alert";
import { SelectField, TextField } from "@/components/ui/Field";

describe("TextField", () => {
  it("associates the label with the input", () => {
    render(<TextField label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("exposes errors to assistive technology", () => {
    render(<TextField label="Email" error="Enter a valid email" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter a valid email");
  });

  it("shows the hint only while there is no error", () => {
    const { rerender } = render(<TextField label="Password" hint="At least 10 characters." />);
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("At least 10 characters.");
    rerender(<TextField label="Password" hint="At least 10 characters." error="Too short" />);
    expect(screen.queryByText("At least 10 characters.")).not.toBeInTheDocument();
  });
});

describe("SelectField", () => {
  it("renders options under an accessible label", () => {
    render(
      <SelectField label="University" defaultValue="">
        <option value="">Choose</option>
        <option value="a">A</option>
      </SelectField>,
    );
    expect(screen.getByLabelText("University")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "A" })).toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("uses role=alert for errors and role=status otherwise", () => {
    const { rerender } = render(<Alert variant="error">Bad</Alert>);
    expect(screen.getByRole("alert")).toHaveTextContent("Bad");
    rerender(<Alert variant="success">Good</Alert>);
    expect(screen.getByRole("status")).toHaveTextContent("Good");
  });
});
