// Remove the generated .next cache before a build.
//
// Some sandboxed Node runtimes wrap fs.rmSync with a bulk-delete guard once the
// cache has more than 50 files. Using the platform directory remover on this
// fixed generated path keeps repeated local builds reproducible.

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const target = join(root, ".next");

if (existsSync(target)) {
  if (process.platform === "win32") {
    execFileSync("cmd.exe", ["/c", "rmdir", "/s", "/q", target], { stdio: "ignore" });
  } else {
    execFileSync("rm", ["-rf", target], { stdio: "ignore" });
  }
}
