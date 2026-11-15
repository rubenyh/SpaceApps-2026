// Self-check for lib/board.ts. Run: node src/lib/board.check.ts
import { cascadeFrames } from "./board.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

// Cascade: changed positions only, ends on target, bounded length.
eq(cascadeFrames("71", "71"), [], "no change");
const f = cascadeFrames(" 71", "112");
eq(f[f.length - 1], "112", "ends on target");
eq(f.length, 4, "frames = changed + 1");
for (const s of f) eq(s.length, 3, "fixed width");
eq(cascadeFrames("120", "125").every((s) => s.startsWith("12")), true, "unchanged chars stay");
eq(cascadeFrames("A", "ABCDEFGHIJKLMNOP").length, 8, "capped frames");
eq(cascadeFrames("ALERT", "NO ALERTS").slice(-1)[0], "NO ALERTS", "text target");

console.log("board.check: ok");
