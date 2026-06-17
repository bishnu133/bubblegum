// Drop a `package.json` "type" marker into each build dir so Node interprets the
// emitted files correctly regardless of the root package's "type": dist/esm is
// ES modules, dist/cjs is CommonJS. Without the cjs marker, the root
// "type": "module" would make Node treat dist/cjs/*.js as ESM and `require()`
// would throw ERR_REQUIRE_ESM.
import { mkdirSync, writeFileSync } from "node:fs";

for (const [dir, type] of [["dist/esm", "module"], ["dist/cjs", "commonjs"]]) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(`${dir}/package.json`, JSON.stringify({ type }, null, 2) + "\n");
}
console.log("postbuild: wrote dist/esm and dist/cjs package.json type markers");
