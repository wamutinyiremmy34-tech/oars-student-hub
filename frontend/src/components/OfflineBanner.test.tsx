import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OfflineBanner } from "@/components/OfflineBanner";

afterEach(() => vi.restoreAllMocks());

describe("OfflineBanner", () => {
  it("renders nothing while online", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    const { container } = render(<OfflineBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("announces when offline", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<OfflineBanner />);
    expect(screen.getByRole("status")).toHaveTextContent(/offline/i);
  });
});
