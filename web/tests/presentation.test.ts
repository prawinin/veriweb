import assert from "node:assert/strict";
import test from "node:test";
import { introProgress } from "../lib/presentation";

test("intro transition follows scroll and stays bounded during overscroll", () => {
  assert.equal(introProgress(-100, 900), 0);
  assert.equal(introProgress(0, 900), 0);
  assert.equal(introProgress(315, 900), 0.5);
  assert.equal(introProgress(630, 900), 1);
  assert.equal(introProgress(1800, 900), 1);
  assert.equal(introProgress(20, 0), 0);
});
