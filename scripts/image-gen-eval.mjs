#!/usr/bin/env node

import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { performance } from 'node:perf_hooks';

const DEFAULT_CASES_DIR = 'eval/image-gen-cases';
const DEFAULT_OUTPUT_DIR = 'eval/results/image-gen';
const OPENAI_IMAGE_GENERATIONS_URL = 'https://api.openai.com/v1/images/generations';
const OPENAI_IMAGE_EDITS_URL = 'https://api.openai.com/v1/images/edits';
const DEFAULT_MODEL = 'gpt-image-1';
const MOCK_PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';

main().catch((error) => {
  console.error(formatError(error));
  process.exitCode = 1;
});

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  const cwd = process.cwd();
  const env = await loadEnv(path.join(cwd, '.env'));
  const apiKey = env.OPENAI_API_KEY || env.CODEX_API_KEY || process.env.OPENAI_API_KEY || process.env.CODEX_API_KEY || '';
  const outputDir = path.resolve(cwd, options.outputDir || DEFAULT_OUTPUT_DIR);

  if (!options.casePath && !options.casePaths && !options.allCases) {
    throw new Error('Missing required --case <path>, --cases <csv>, or --all-cases option.');
  }

  const caseFilePaths = await resolveCaseFilePaths(cwd, options);
  const cases = [];
  for (const caseFilePath of caseFilePaths) {
    cases.push(await prepareCase(caseFilePath));
  }
  const preparedCases = expandModelMatrix(cases, options.models);

  if (options.dryRun) {
    for (const preparedCase of preparedCases) {
      printDryRun({ preparedCase, outputDir, apiKey, mock: options.mock });
    }
    return;
  }

  if (!options.mock && !apiKey) {
    throw new Error('Missing OpenAI API key. Set OPENAI_API_KEY or CODEX_API_KEY in .env.');
  }

  await mkdir(outputDir, { recursive: true });
  const reports = [];
  for (const preparedCase of preparedCases) {
    reports.push(await runCase({ cwd, preparedCase, outputDir, apiKey, mock: options.mock }));
  }

  const indexPath = path.join(outputDir, 'index.md');
  await writeFile(indexPath, renderIndex(reports));
  console.log(`Wrote image generation index: ${path.relative(cwd, indexPath)}`);
  const htmlPath = path.join(outputDir, 'index.html');
  await writeFile(htmlPath, renderHtmlIndex(reports, outputDir));
  console.log(`Wrote image generation HTML index: ${path.relative(cwd, htmlPath)}`);
}

function parseArgs(args) {
  const options = {
    casePath: '',
    casePaths: null,
    allCases: false,
    outputDir: '',
    models: null,
    dryRun: false,
    mock: false,
    help: false,
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = () => {
      index += 1;
      if (index >= args.length) {
        throw new Error(`Missing value for ${arg}.`);
      }
      return args[index];
    };

    if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--case') {
      options.casePath = next();
    } else if (arg === '--cases') {
      options.casePaths = splitCsv(next());
    } else if (arg === '--all-cases') {
      options.allCases = true;
    } else if (arg === '--output-dir') {
      options.outputDir = next();
    } else if (arg === '--models') {
      options.models = splitCsv(next());
    } else if (arg === '--dry-run') {
      options.dryRun = true;
    } else if (arg === '--mock') {
      options.mock = true;
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }

  return options;
}

function printHelp() {
  console.log(`Image generation evaluation harness

Usage:
  node scripts/image-gen-eval.mjs --case eval/image-gen-cases/buddy-simple-generate.json --dry-run
  node scripts/image-gen-eval.mjs --all-cases --mock
  node scripts/image-gen-eval.mjs --all-cases

Options:
  --case <path>        Run one image generation case JSON file.
  --cases <csv>        Run multiple case JSON files.
  --all-cases          Run every JSON case in eval/image-gen-cases.
  --output-dir <path>  Defaults to ${DEFAULT_OUTPUT_DIR}.
  --models <csv>       Override case model and run a model matrix.
  --dry-run            Validate config and print planned requests.
  --mock               Generate local mock artifacts without API calls.
`);
}

async function resolveCaseFilePaths(cwd, options) {
  if (options.casePath) {
    return [path.resolve(cwd, options.casePath)];
  }
  if (options.casePaths) {
    return options.casePaths.map((casePath) => path.resolve(cwd, casePath));
  }

  const casesDir = path.resolve(cwd, DEFAULT_CASES_DIR);
  const entries = await readdir(casesDir);
  return entries
    .filter((entry) => entry.endsWith('.json'))
    .sort()
    .map((entry) => path.join(casesDir, entry));
}

async function prepareCase(caseFilePath) {
  const raw = await readFile(caseFilePath, 'utf8');
  const testCase = JSON.parse(raw);
  validateCase(testCase);

  let inputImage = null;
  if (testCase.imagePath) {
    const imagePath = path.resolve(path.dirname(caseFilePath), testCase.imagePath);
    if (!existsSync(imagePath)) {
      throw new Error(`Input image file not found: ${imagePath}`);
    }
    const buffer = await readFile(imagePath);
    inputImage = {
      path: imagePath,
      bytes: buffer.byteLength,
      mediaType: mediaTypeForPath(imagePath),
      buffer,
    };
  }

  return { caseFilePath, testCase, inputImage };
}

function expandModelMatrix(preparedCases, models) {
  if (!models || models.length === 0) {
    return preparedCases;
  }

  return preparedCases.flatMap((preparedCase) => models.map((model) => {
    const testCase = JSON.parse(JSON.stringify(preparedCase.testCase));
    const originalId = testCase.id;
    testCase.generation.model = model;
    testCase.id = `${originalId}-${sanitizeFileName(model)}`;
    return {
      ...preparedCase,
      testCase,
      matrix: {
        originalId,
        model,
      },
    };
  }));
}

function validateCase(testCase) {
  const validActions = new Set(['generate', 'translate-text', 'edit-image']);
  if (!testCase.id || typeof testCase.id !== 'string') {
    throw new Error('Case must include string field: id');
  }
  if (!validActions.has(testCase.action)) {
    throw new Error(`Invalid action: ${testCase.action}. Expected generate, translate-text, or edit-image.`);
  }
  if (!testCase.prompt || typeof testCase.prompt !== 'string') {
    throw new Error('Case must include string field: prompt');
  }
  if (testCase.action !== 'generate' && (!testCase.imagePath || typeof testCase.imagePath !== 'string')) {
    throw new Error(`${testCase.action} case must include string field: imagePath`);
  }
  if (!testCase.generation || typeof testCase.generation !== 'object') {
    testCase.generation = {};
  }
  testCase.generation.provider = testCase.generation.provider || 'openai';
  testCase.generation.model = testCase.generation.model || DEFAULT_MODEL;
  testCase.generation.n = testCase.generation.n || 1;
  if (testCase.generation.provider !== 'openai') {
    throw new Error('Image generation currently supports provider=openai only.');
  }
}

function printDryRun({ preparedCase, outputDir, apiKey, mock }) {
  const { testCase, caseFilePath, inputImage } = preparedCase;
  console.log('Dry run OK');
  console.log(`Case: ${testCase.id} (${testCase.action})`);
  console.log(`Case path: ${caseFilePath}`);
  console.log(`Model: ${testCase.generation.model}`);
  console.log(`Size: ${testCase.generation.size || 'provider default'}`);
  console.log(`Quality: ${testCase.generation.quality || 'provider default'}`);
  console.log(`Output format: ${testCase.generation.outputFormat || 'provider default'}`);
  console.log(`Background: ${testCase.generation.background || 'provider default'}`);
  console.log(`Input image: ${inputImage ? `${inputImage.path} (${inputImage.mediaType}, ${inputImage.bytes} bytes)` : '-'}`);
  console.log(`OpenAI key: ${apiKey ? 'present' : 'missing'}`);
  console.log(`Mock mode: ${mock ? 'on' : 'off'}`);
  console.log(`Output dir: ${outputDir}`);
}

async function runCase({ cwd, preparedCase, outputDir, apiKey, mock }) {
  const { testCase } = preparedCase;
  const startedAt = new Date();
  const started = performance.now();
  const generated = mock
    ? await createMockImage({ testCase, outputDir })
    : await callOpenAIImage({ preparedCase, outputDir, apiKey });
  const latencyTotalMs = Math.round(performance.now() - started);
  const finishedAt = new Date();

  const report = {
    case: testCase,
    metadata: {
      caseFilePath: preparedCase.caseFilePath,
      originalCaseId: preparedCase.matrix?.originalId || testCase.id,
      inputImage: describeInputImage(preparedCase.inputImage),
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      mock,
    },
    run: {
      provider: 'openai',
      model: testCase.generation.model,
      action: testCase.action,
      status: 'success',
      latencyTotalMs,
      request: buildRequestSummary(testCase),
      output: generated.output,
      usage: generated.usage,
      estimatedCostUsd: null,
      raw: generated.raw,
    },
    manualReview: {
      qualityNotes: '',
      winner: '',
      checklist: buildReviewChecklist(testCase),
    },
  };

  const safeId = sanitizeFileName(testCase.id);
  const timestamp = toTimestamp(finishedAt);
  const jsonPath = path.join(outputDir, `${safeId}-${timestamp}.json`);
  const mdPath = path.join(outputDir, `${safeId}-${timestamp}.md`);
  await writeFile(jsonPath, `${JSON.stringify(report, null, 2)}\n`);
  await writeFile(mdPath, renderMarkdownReport(report));

  report.artifacts = {
    jsonPath,
    mdPath,
    jsonRelativePath: path.relative(outputDir, jsonPath),
    mdRelativePath: path.relative(outputDir, mdPath),
  };

  console.log(`Wrote image result: ${path.relative(cwd, generated.output.path)}`);
  console.log(`Wrote JSON result: ${path.relative(cwd, jsonPath)}`);
  console.log(`Wrote Markdown report: ${path.relative(cwd, mdPath)}`);
  return report;
}

async function createMockImage({ testCase, outputDir }) {
  const output = await writeImageOutput({
    outputDir,
    caseId: testCase.id,
    index: 0,
    outputFormat: testCase.generation.outputFormat || 'png',
    base64: MOCK_PNG_BASE64,
  });

  return {
    output,
    usage: { imageCount: 1 },
    raw: { mock: true },
  };
}

async function callOpenAIImage({ preparedCase, outputDir, apiKey }) {
  const { testCase, inputImage } = preparedCase;
  const response = testCase.action === 'generate'
    ? await callOpenAIImageGeneration({ testCase, apiKey })
    : await callOpenAIImageEdit({ testCase, inputImage, apiKey });

  const firstImage = response.data?.[0];
  if (!firstImage) {
    throw new Error('OpenAI image response did not include data[0].');
  }

  const outputFormat = testCase.generation.outputFormat || 'png';
  const output = firstImage.b64_json
    ? await writeImageOutput({
      outputDir,
      caseId: testCase.id,
      index: 0,
      outputFormat,
      base64: firstImage.b64_json,
    })
    : await downloadImageOutput({
      outputDir,
      caseId: testCase.id,
      index: 0,
      outputFormat,
      url: firstImage.url,
    });

  return {
    output,
    usage: response.usage || { imageCount: response.data.length },
    raw: response,
  };
}

async function callOpenAIImageGeneration({ testCase, apiKey }) {
  return fetchJson(OPENAI_IMAGE_GENERATIONS_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(compactObject({
      model: testCase.generation.model,
      prompt: testCase.prompt,
      size: testCase.generation.size,
      quality: testCase.generation.quality,
      n: testCase.generation.n,
      output_format: testCase.generation.outputFormat,
      output_compression: testCase.generation.outputCompression,
      background: testCase.generation.background,
      moderation: testCase.generation.moderation,
    })),
  });
}

async function callOpenAIImageEdit({ testCase, inputImage, apiKey }) {
  if (!inputImage) {
    throw new Error(`${testCase.action} requires an input image.`);
  }

  const form = new FormData();
  form.set('model', testCase.generation.model);
  form.set('prompt', testCase.prompt);
  appendOptionalFormField(form, 'size', testCase.generation.size);
  appendOptionalFormField(form, 'quality', testCase.generation.quality);
  appendOptionalFormField(form, 'n', testCase.generation.n);
  appendOptionalFormField(form, 'output_format', testCase.generation.outputFormat);
  appendOptionalFormField(form, 'output_compression', testCase.generation.outputCompression);
  appendOptionalFormField(form, 'background', testCase.generation.background);
  const blob = new Blob([inputImage.buffer], { type: inputImage.mediaType });
  form.set('image', blob, path.basename(inputImage.path));

  return fetchJson(OPENAI_IMAGE_EDITS_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: form,
  });
}

function appendOptionalFormField(form, name, value) {
  if (value !== undefined && value !== null && value !== '') {
    form.set(name, String(value));
  }
}

async function writeImageOutput({ outputDir, caseId, index, outputFormat, base64 }) {
  const buffer = Buffer.from(base64, 'base64');
  const ext = extensionForOutputFormat(outputFormat);
  const imageDir = path.join(outputDir, 'assets');
  await mkdir(imageDir, { recursive: true });
  const outputPath = path.join(imageDir, `${sanitizeFileName(caseId)}-${index}.${ext}`);
  await writeFile(outputPath, buffer);
  return describeOutputImage(outputPath, buffer, outputFormat);
}

async function downloadImageOutput({ outputDir, caseId, index, outputFormat, url }) {
  if (!url) {
    throw new Error('OpenAI image response included neither b64_json nor url.');
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download generated image: HTTP ${response.status}`);
  }
  const arrayBuffer = await response.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  const ext = extensionForOutputFormat(outputFormat);
  const imageDir = path.join(outputDir, 'assets');
  await mkdir(imageDir, { recursive: true });
  const outputPath = path.join(imageDir, `${sanitizeFileName(caseId)}-${index}.${ext}`);
  await writeFile(outputPath, buffer);
  return describeOutputImage(outputPath, buffer, outputFormat);
}

function describeOutputImage(outputPath, buffer, outputFormat) {
  const dimensions = readImageDimensions(buffer, outputFormat);
  return {
    path: outputPath,
    bytes: buffer.byteLength,
    format: outputFormat,
    width: dimensions.width,
    height: dimensions.height,
  };
}

function readImageDimensions(buffer, outputFormat) {
  if (outputFormat === 'png' && buffer.length >= 24 && buffer.toString('ascii', 1, 4) === 'PNG') {
    return {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }
  return { width: null, height: null };
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { rawText: text };
  }

  if (!response.ok) {
    const message = body?.error?.message || body?.message || text || `HTTP ${response.status}`;
    throw new Error(message);
  }

  return body;
}

function buildRequestSummary(testCase) {
  return {
    endpoint: testCase.action === 'generate' ? '/v1/images/generations' : '/v1/images/edits',
    prompt: testCase.prompt,
    generation: testCase.generation,
    expectedCriteria: testCase.expectedCriteria || {},
  };
}

function buildReviewChecklist(testCase) {
  if (testCase.action === 'translate-text') {
    return [
      'Visible text is translated according to the prompt',
      'Original layout, color, and hierarchy are preserved',
      'Translated text is legible',
      'No important UI content is lost',
    ];
  }
  if (testCase.action === 'edit-image') {
    return [
      'Requested visual edit is present',
      'Important source-image content remains readable',
      'New element does not occlude key text',
      'Style feels appropriate for Buddy',
    ];
  }
  return [
    'Generated image follows the prompt',
    'No unintended visible text appears',
    'Image is usable in Buddy UI',
    'Composition and style are polished',
  ];
}

function renderMarkdownReport(report) {
  const output = report.run.output;
  const checklist = report.manualReview.checklist.map((item) => `- [ ] ${item}`).join('\n');

  return `# Image Gen Eval Report: ${report.case.id}

## Case

- action: ${report.case.action}
- startedAt: ${report.metadata.startedAt}
- finishedAt: ${report.metadata.finishedAt}
- mock: ${report.metadata.mock}
- inputImage: ${report.metadata.inputImage?.path || '-'}

## Request

\`\`\`json
${JSON.stringify(report.run.request, null, 2)}
\`\`\`

## Summary

| Provider | Model | Status | Total ms | Output format | Width | Height | Bytes |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| ${report.run.provider} | ${report.run.model} | ${report.run.status} | ${report.run.latencyTotalMs} | ${output.format} | ${output.width ?? '-'} | ${output.height ?? '-'} | ${output.bytes} |

## Output

- image: ${output.path}

## Manual Review

${checklist}

- qualityNotes:
- winner:
`;
}

function renderIndex(reports) {
  const rows = reports.map((report) => (
    `| ${report.metadata.originalCaseId || report.case.id} | ${report.case.action} | ${report.run.model} | ${report.run.latencyTotalMs} | ${report.run.output.format} | ${report.run.output.width ?? '-'}x${report.run.output.height ?? '-'} | ${report.run.output.bytes} | ${report.artifacts?.mdRelativePath || '-'} |`
  )).join('\n');

  return `# Image Generation Eval Index

| Case | Action | Model | Total ms | Format | Size | Bytes | Report |
| --- | --- | --- | ---: | --- | --- | ---: | --- |
${rows}
`;
}

function renderHtmlIndex(reports, outputDir) {
  const cards = reports.map((report) => {
    const imagePath = path.relative(outputDir, report.run.output.path);
    const reportPath = report.artifacts?.mdRelativePath || '';
    return `<article>
  <img src="${escapeHtml(imagePath)}" alt="${escapeHtml(report.case.id)}">
  <div class="card-body">
    <h2>${escapeHtml(report.metadata.originalCaseId || report.case.id)}</h2>
    <dl>
      <div><dt>Model</dt><dd>${escapeHtml(report.run.model)}</dd></div>
      <div><dt>Action</dt><dd>${escapeHtml(report.case.action)}</dd></div>
      <div><dt>Latency</dt><dd>${formatMs(report.run.latencyTotalMs)}</dd></div>
      <div><dt>Size</dt><dd>${report.run.output.width ?? '-'}x${report.run.output.height ?? '-'}</dd></div>
      <div><dt>Bytes</dt><dd>${report.run.output.bytes.toLocaleString('en-US')}</dd></div>
    </dl>
    <a href="${escapeHtml(reportPath)}">Markdown report</a>
  </div>
</article>`;
  }).join('\n');

  const rows = reports.map((report) => (
    `<tr>
  <td>${escapeHtml(report.metadata.originalCaseId || report.case.id)}</td>
  <td>${escapeHtml(report.case.action)}</td>
  <td>${escapeHtml(report.run.model)}</td>
  <td>${formatMs(report.run.latencyTotalMs)}</td>
  <td>${report.run.output.width ?? '-'}x${report.run.output.height ?? '-'}</td>
  <td>${report.run.output.bytes.toLocaleString('en-US')}</td>
  <td><a href="${escapeHtml(report.artifacts?.mdRelativePath || '')}">Markdown</a></td>
</tr>`
  )).join('\n');

  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Buddy Image Generation Eval</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7f9; color: #202124; }
    main { max-width: 1280px; margin: 0 auto; padding: 32px 24px 56px; }
    h1 { margin: 0 0 8px; font-size: 28px; line-height: 1.25; }
    .note { margin: 0 0 24px; color: #5f6368; line-height: 1.55; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0 28px; background: #fff; border: 1px solid #dfe3e8; }
    th, td { padding: 10px 12px; border-bottom: 1px solid #e9edf2; text-align: left; font-size: 14px; vertical-align: top; }
    th { background: #eef2f7; font-weight: 700; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
    article { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; overflow: hidden; }
    article img { width: 100%; display: block; background: #fff; }
    .card-body { padding: 16px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    dl { display: grid; gap: 6px; margin: 0 0 12px; }
    dl div { display: flex; justify-content: space-between; gap: 12px; }
    dt { color: #5f6368; }
    dd { margin: 0; font-weight: 600; text-align: right; }
    a { color: #0b57d0; }
  </style>
</head>
<body>
  <main>
    <h1>Buddy Image Generation Eval</h1>
    <p class="note">Generated image/edit outputs with model, latency, dimensions, and file-size comparisons.</p>
    <table>
      <thead>
        <tr><th>Case</th><th>Action</th><th>Model</th><th>Latency</th><th>Size</th><th>Bytes</th><th>Report</th></tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
    <section class="grid">
      ${cards}
    </section>
  </main>
</body>
</html>
`;
}

function formatMs(ms) {
  return `${(ms / 1000).toFixed(3)}s`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function describeInputImage(inputImage) {
  if (!inputImage) {
    return null;
  }
  return {
    path: inputImage.path,
    bytes: inputImage.bytes,
    mediaType: inputImage.mediaType,
  };
}

async function loadEnv(envPath) {
  if (!existsSync(envPath)) {
    return {};
  }
  const env = {};
  const content = await readFile(envPath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
      continue;
    }
    const index = trimmed.indexOf('=');
    const key = trimmed.slice(0, index).trim();
    const value = trimmed.slice(index + 1).trim().replace(/^["']|["']$/g, '');
    env[key] = value;
  }
  return env;
}

function compactObject(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ''));
}

function splitCsv(value) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function sanitizeFileName(value) {
  return String(value).replace(/[^a-z0-9._-]+/gi, '-').toLowerCase();
}

function toTimestamp(date) {
  return date.toISOString().replace(/[:.]/g, '-');
}

function mediaTypeForPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  throw new Error(`Unsupported image extension: ${ext}`);
}

function extensionForOutputFormat(outputFormat) {
  if (outputFormat === 'jpeg') return 'jpg';
  if (outputFormat === 'webp') return 'webp';
  return 'png';
}

function formatError(error) {
  return error?.stack || error?.message || String(error);
}
