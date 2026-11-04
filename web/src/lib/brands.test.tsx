import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandMark, brandOf, KindMark } from "@/lib/brands";

describe("vendor marks", () => {
  it("knows the brands the API sends, whatever their spelling", () => {
    expect(brandOf("homeassistant")).toBe("home-assistant");
    expect(brandOf("pollen-robotics")).toBe("reachy");
    expect(brandOf("openai")).toBe("openai");
    expect(brandOf("mistral")).toBe("mistral");
    expect(brandOf("openai-compatible-embeddings")).toBe("openai-compatible");
    expect(brandOf("telegram:42")).toBe("telegram");
    expect(brandOf("someone-else")).toBeNull();
  });

  it("draws each vendor's own mark under its name", () => {
    render(
      <>
        <BrandMark brand="openrouter" />
        <BrandMark brand="llama-cpp" />
        <BrandMark brand="kokoro" />
        <BrandMark brand="elevenlabs" label={false} />
      </>,
    );
    for (const name of ["OpenRouter", "llama.cpp", "Kokoro"]) {
      expect(screen.getByRole("img", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("img", { name: "ElevenLabs" })).toBeNull();
  });

  it("shows a neutral plug, named by its kind, for an unknown plugin", () => {
    render(<KindMark kind="acme-weather" />);
    expect(screen.getByLabelText("acme-weather")).toBeInTheDocument();
  });
});
