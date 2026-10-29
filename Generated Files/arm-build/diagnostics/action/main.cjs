"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

if (!process.env.DIAG_ROOT || !process.env.INPUT_OUTPUT) {
  throw new Error("DIAG_ROOT and the output input are required");
}
const root = path.resolve(process.env.DIAG_ROOT);
const output = path.resolve(process.env.INPUT_OUTPUT);
const relative = path.relative(root, output);
if (
  !relative ||
  path.isAbsolute(relative) ||
  relative === ".." ||
  relative.startsWith(`..${path.sep}`)
) {
  throw new Error("The runtime receipt must be a new file inside DIAG_ROOT");
}

const environment = {};
for (const name of [
  "GITHUB_RUN_ID",
  "GITHUB_RUN_ATTEMPT",
  "GITHUB_JOB",
  "RUNNER_OS",
  "RUNNER_ARCH",
  "RUNNER_ENVIRONMENT",
  "ImageOS",
  "ImageVersion",
]) {
  environment[name] = process.env[name] ?? null;
}
const receipt = {
  schema: "arm-analysis-action-runtime-v1",
  purpose: "analysis-only",
  performance_eligible: false,
  execution_context:
    process.env.GITHUB_ACTIONS === "true" ? "github-action" : "local-validation",
  node: {
    architecture: process.arch,
    version: process.version,
    versions: process.versions,
    executable: process.execPath,
    sha256: crypto
      .createHash("sha256")
      .update(fs.readFileSync(process.execPath))
      .digest("hex"),
  },
  host: {
    platform: process.platform,
    machine: os.machine(),
    release: os.release(),
    logical_cpus: os.cpus().length,
    cpu_models: [...new Set(os.cpus().map((cpu) => cpu.model))],
    memory_bytes: os.totalmem(),
  },
  environment,
  scope: "Actual Node process executing this action, not PATH-selected node",
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(receipt, null, 2)}\n`, { flag: "wx" });
console.log(`Analysis action runtime: Node ${process.version}, ${process.arch}`);
console.log(`Receipt: ${output}`);
