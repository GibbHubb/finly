import { describe, expect, it } from "vitest";
import { apiErrorMessage } from "@/utils/errors";

// F36 — this is called from every catch block in the app; a throw inside it
// would mask the original failure, which is exactly what it exists to prevent.
describe("apiErrorMessage", () => {
  it("prefers FastAPI's response.data.detail", () => {
    const err = { response: { data: { detail: "Budget already exists" } }, message: "Request failed" };
    expect(apiErrorMessage(err, "fallback")).toBe("Budget already exists");
  });

  it("falls back to Error.message when there is no detail", () => {
    expect(apiErrorMessage(new Error("Network Error"), "fallback")).toBe("Network Error");
  });

  it("falls back when detail is present but blank", () => {
    const err = { response: { data: { detail: "   " } }, message: "Request failed" };
    expect(apiErrorMessage(err, "fallback")).toBe("Request failed");
  });

  it("ignores a non-string detail (FastAPI validation arrays)", () => {
    const err = { response: { data: { detail: [{ msg: "field required" }] } } };
    expect(apiErrorMessage(err, "fallback")).toBe("fallback");
  });

  it("returns the fallback for null, undefined and primitives", () => {
    expect(apiErrorMessage(null, "fallback")).toBe("fallback");
    expect(apiErrorMessage(undefined, "fallback")).toBe("fallback");
    expect(apiErrorMessage("a string throw", "fallback")).toBe("fallback");
    expect(apiErrorMessage(42, "fallback")).toBe("fallback");
  });

  it("returns the fallback for an object with nothing usable", () => {
    expect(apiErrorMessage({}, "fallback")).toBe("fallback");
  });
});
