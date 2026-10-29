"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

test("runtime receipt is scoped, immutable, and excludes unapproved environment", () => {
  const parent = path.resolve(__dirname, "..", ".local");
  fs.mkdirSync(parent, { recursive: true });
  const root = fs.mkdtempSync(path.join(parent, "action-"));
  const output = path.join(root, "runtime.json");
  const outside = path.join(parent, `${path.basename(root)}-outside.json`);
  const environment = {
    ...process.env,
    DIAG_ROOT: root,
    INPUT_OUTPUT: output,
    GITHUB_ACTIONS: "false",
    UNAPPROVED_SECRET: "not-for-export",
  };
  const run = (env) =>
    spawnSync(process.execPath, [path.join(__dirname, "main.cjs")], {
      env,
      encoding: "utf8",
    });
  try {
    const first = run(environment);
    assert.equal(first.status, 0, first.stderr);
    const bytes = fs.readFileSync(output);
    const receipt = JSON.parse(bytes);
    assert.equal(receipt.performance_eligible, false);
    assert.equal(receipt.execution_context, "local-validation");
    assert.equal(receipt.node.architecture, process.arch);
    assert.match(receipt.node.sha256, /^[0-9a-f]{64}$/);
    assert.equal(receipt.scope.includes("not PATH-selected"), true);
    assert.equal(bytes.includes(Buffer.from("not-for-export")), false);
    assert.equal(Object.hasOwn(receipt.environment, "PATH"), false);
    assert.notEqual(run(environment).status, 0);
    assert.deepEqual(fs.readFileSync(output), bytes);
    assert.notEqual(run({ ...environment, INPUT_OUTPUT: outside }).status, 0);
    assert.equal(fs.existsSync(outside), false);
  } finally {
    if (fs.existsSync(output)) fs.unlinkSync(output);
    fs.rmdirSync(root);
  }
});
