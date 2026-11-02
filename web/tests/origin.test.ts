import { test } from "node:test";
import assert from "node:assert/strict";
import { sameOrigin } from "../lib/origin";

test("accepts the browser Host when Next.js normalizes its internal URL to localhost", () => {
  assert.equal(
    sameOrigin("http://127.0.0.1:43121", "127.0.0.1:43121", "http:"),
    true,
  );
  assert.equal(
    sameOrigin("https://attacker.example", "127.0.0.1:43121", "http:"),
    false,
  );
});
test("a configured public origin takes precedence over proxy Host", () => {
  assert.equal(
    sameOrigin(
      "https://research.example",
      "internal:8000",
      "http:",
      "https://research.example",
    ),
    true,
  );
  assert.equal(
    sameOrigin(
      "http://internal:8000",
      "internal:8000",
      "http:",
      "https://research.example",
    ),
    false,
  );
});
test("an empty optional deployment origin uses the browser Host", () => {
  assert.equal(
    sameOrigin("http://127.0.0.1:43121", "127.0.0.1:43121", "http:", ""),
    true,
  );
});
