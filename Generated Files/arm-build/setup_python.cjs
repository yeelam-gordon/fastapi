// Provision the same native Python distribution family without Windows MSI setup.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = __dirname;
const output = path.join(root, "results", "bootstrap");
fs.mkdirSync(output, { recursive: true });
const os = process.platform === "win32" ? "windows" : "macos";
if (!["win32", "darwin"].includes(process.platform)) {
  throw new Error(`Unsupported experiment platform: ${process.platform}`);
}
const request = `cpython-3.13.15-${os}-aarch64-none`;
const report = { status: "running", request, phases: [] };

function run(command, args, phase) {
  const started = performance.now();
  const result = spawnSync(command, args, { encoding: "utf8" });
  fs.writeFileSync(
    path.join(output, `${phase}.log`),
    (result.stdout || "") + (result.stderr || ""),
  );
  report.phases.push({
    command: [command, ...args],
    phase,
    seconds: (performance.now() - started) / 1000,
    exit_code: result.status,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`${phase}: ${result.error || result.stderr}`);
  }
  return result.stdout.trim();
}

try {
  run("uv", ["python", "install", request, "--no-config"], "install-python");
  const interpreter = run(
    "uv", ["python", "find", "--managed-python", request, "--no-config"],
    "find-python",
  );
  const environment = path.join(root, ".venv");
  run(
    "uv", ["venv", "--python", interpreter, "--no-python-downloads", environment],
    "create-build-environment",
  );
  const python = path.join(
    environment,
    process.platform === "win32" ? "Scripts" : "bin",
    process.platform === "win32" ? "python.exe" : "python",
  );
  report.python = JSON.parse(run(
    python,
    ["-c", "import json,sys,sysconfig,platform; print(json.dumps({'version':sys.version,'platform':sysconfig.get_platform(),'machine':platform.machine(),'executable':sys.executable}))"],
    "probe-python",
  ));
  if (!process.env.GITHUB_PATH) {
    throw new Error("GITHUB_PATH is required to select the CI interpreter");
  }
  fs.appendFileSync(process.env.GITHUB_PATH, path.dirname(python) + "\n");
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.error = String(error);
  throw error;
} finally {
  fs.writeFileSync(
    path.join(output, "python-setup.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
}
