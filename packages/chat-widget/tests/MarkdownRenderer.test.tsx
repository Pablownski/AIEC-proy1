import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownRenderer } from "../src/components/MarkdownRenderer";

describe("MarkdownRenderer", () => {
  it("renders headings", () => {
    render(<MarkdownRenderer content="## AGIChat" />);
    expect(screen.getByRole("heading", { level: 2, name: "AGIChat" })).toBeInTheDocument();
  });

  it("renders bold and italic text", () => {
    render(<MarkdownRenderer content="**fuerte** y *cursiva*" />);
    expect(screen.getByText("fuerte").tagName).toBe("STRONG");
    expect(screen.getByText("cursiva").tagName).toBe("EM");
  });

  it("renders unordered lists", () => {
    render(<MarkdownRenderer content={"- uno\n- dos"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders links with href", () => {
    render(<MarkdownRenderer content="[AGIChat](https://example.com)" />);
    const link = screen.getByRole("link", { name: "AGIChat" });
    expect(link).toHaveAttribute("href", "https://example.com");
  });

  it("renders inline code", () => {
    render(<MarkdownRenderer content="usa `npm install`" />);
    expect(screen.getByText("npm install").tagName).toBe("CODE");
  });

  it("renders fenced code blocks", () => {
    render(<MarkdownRenderer content={"```\nconst a = 1;\n```"} />);
    expect(screen.getByText("const a = 1;")).toBeInTheDocument();
  });

  it("strips script tags instead of executing them", () => {
    render(<MarkdownRenderer content={'<script>window.__pwned = true</script>\n\nHola'} />);
    expect(screen.getByText("Hola")).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("never renders an onerror handler from raw HTML input", () => {
    const { container } = render(
      <MarkdownRenderer content={'<img src="x" onerror="window.__pwned=true">Hola'} />,
    );
    expect(container.querySelector("[onerror]")).not.toBeInTheDocument();
  });
});
