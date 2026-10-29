'use strict';
// Bounded experiment: regular files only, one JSON request, binary gzip stdout.
const fs = require('node:fs/promises');
const path = require('node:path');
const { gzipSync } = require('node:zlib');

function safeName(name) {
  if (typeof name !== 'string' || !name || /[\\:\0\r\n]/u.test(name) ||
      name.split('/').some(p => !p || p === '.' || p === '..') ||
      Buffer.from(name).toString('utf8') !== name) {
    throw new Error('Unsafe archive path');
  }
}
function octal(header, value, offset, length) {
  if (!Number.isSafeInteger(value) || value < 0) throw new Error('Invalid numeric field');
  const text = value.toString(8);
  if (text.length >= length) throw new Error('USTAR numeric overflow');
  header.write(text.padStart(length - 1, '0') + '\0', offset, length, 'ascii');
}
function header(name, size, mode, type = '0') {
  if (!/^[\x20-\x7e]+$/.test(name) || Buffer.byteLength(name) > 100)
    throw new Error('Invalid USTAR header name');
  const b = Buffer.alloc(512);
  b.write(name, 0, 100, 'ascii');
  octal(b, mode, 100, 8);
  octal(b, 0, 108, 8);
  octal(b, 0, 116, 8);
  octal(b, size, 124, 12);
  octal(b, 0, 136, 12);
  b.fill(32, 148, 156);
  b.write(type, 156, 1, 'ascii');
  b.write('ustar\0', 257, 6, 'ascii');
  b.write('00', 263, 2, 'ascii');
  const sum = b.reduce((a, v) => a + v, 0);
  b.write(sum.toString(8).padStart(6, '0') + '\0 ', 148, 8, 'ascii');
  return b;
}
function paxPath(name) {
  const body = ` path=${name}\n`;
  let length = Buffer.byteLength(body) + 1;
  while (length !== Buffer.byteLength(body) + String(length).length)
    length = Buffer.byteLength(body) + String(length).length;
  return Buffer.from(String(length) + body);
}
function padded(parts, data) {
  parts.push(data);
  const remainder = data.length % 512;
  if (remainder) parts.push(Buffer.alloc(512 - remainder));
}
async function archive(request, stages) {
  let start = stages ? performance.now() : 0;
  const mark = name => {
    if (stages) {
      const end = performance.now();
      stages[name] = (end - start) / 1000;
      start = end;
    }
  };
  if (!request || ![4, 8].includes(request.workers) || !Array.isArray(request.files) ||
      typeof request.root !== 'string' || !path.isAbsolute(request.root))
    throw new Error('Unsupported request');
  const root = path.resolve(request.root);
  const seen = new Set();
  for (const row of request.files) {
    safeName(row.name);
    if (seen.has(row.name) || ![0o644, 0o755].includes(row.mode) ||
        typeof row.source !== 'string' || !path.isAbsolute(row.source))
      throw new Error('Invalid or duplicate member');
    seen.add(row.name);
    const relative = path.relative(root, row.source);
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative))
      throw new Error('Source outside root');
  }
  mark('validate_request');
  const payloads = new Array(request.files.length);
  let next = 0;
  await Promise.all(Array.from({ length: request.workers }, async () => {
    while (next < request.files.length) {
      const i = next++;
      const row = request.files[i];
      const info = await fs.lstat(row.source);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error('Unsupported source member');
      payloads[i] = await fs.readFile(row.source);
    }
  }));
  mark('bounded_lstat_and_read');
  const parts = [];
  request.files.forEach((row, i) => {
    let name = row.name;
    if (!/^[\x20-\x7e]+$/.test(name) || Buffer.byteLength(name) > 100) {
      const pax = paxPath(name);
      parts.push(header(`PaxHeaders/${i}`, pax.length, 0o644, 'x'));
      padded(parts, pax);
      name = `PaxFiles/${i}`;
    }
    parts.push(header(name, payloads[i].length, row.mode));
    padded(parts, payloads[i]);
  });
  parts.push(Buffer.alloc(1024));
  const tar = Buffer.concat(parts);
  mark('ustar_pax_serialization');
  const output = gzipSync(tar, { level: 9 });
  mark('gzip_level_9');
  return output;
}
async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const stages = request.diagnostic === true ? {} : null;
  const output = await archive(request, stages);
  if (stages) process.stderr.write(JSON.stringify(stages) + '\n');
  process.stdout.write(output);
}
if (require.main === module) main().catch(error => {
  process.stderr.write(error.message + '\n');
  process.exitCode = 1;
});
