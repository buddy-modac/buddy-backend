#!/usr/bin/env node

import { copyFile, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { performance } from 'node:perf_hooks';

const DEFAULT_OPENAI_MODEL = 'gpt-5.4-mini';
const DEFAULT_CLAUDE_MODEL = 'claude-sonnet-4-6';
const DEFAULT_CASES_DIR = 'eval/cases';
const DEFAULT_OUTPUT_DIR = 'eval/results';
const DEFAULT_STRATEGIES = ['single', 'parallel', 'mixed-provider'];
const DEFAULT_MAX_OUTPUT_TOKENS = 900;
const DEFAULT_JUDGE_PROVIDER = 'openai';
const DEFAULT_JUDGE_MODEL = 'gpt-5.4';
const DEFAULT_JUDGE_MAX_OUTPUT_TOKENS = 900;

const OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses';
const CLAUDE_MESSAGES_URL = 'https://api.anthropic.com/v1/messages';
const CLAUDE_API_VERSION = '2023-06-01';

const MODEL_PRICES_PER_MTOK = {
  'gpt-5.5': { input: 5, output: 30 },
  'gpt-5.4': { input: 2.5, output: 15 },
  'gpt-5.4-mini': { input: 0.75, output: 4.5 },
  'claude-fable-5': { input: 10, output: 50 },
  'claude-opus-4-8': { input: 5, output: 25 },
  'claude-sonnet-4-6': { input: 3, output: 15 },
  'claude-haiku-4-5': { input: 1, output: 5 },
  'claude-haiku-4-5-20251001': { input: 1, output: 5 },
};

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
  const apiKeys = {
    openai: env.OPENAI_API_KEY || env.CODEX_API_KEY || process.env.OPENAI_API_KEY || process.env.CODEX_API_KEY || '',
    claude: env.CLAUDE_API_KEY || process.env.CLAUDE_API_KEY || '',
  };

  if (options.resultPaths) {
    const config = {
      outputDir: path.resolve(cwd, options.outputDir || DEFAULT_OUTPUT_DIR),
      pagesDir: options.pagesDir ? path.resolve(cwd, options.pagesDir) : '',
      judgeProvider: options.judgeProvider || DEFAULT_JUDGE_PROVIDER,
      judgeModel: options.judgeModel || DEFAULT_JUDGE_MODEL,
      judgeMaxOutputTokens: options.judgeMaxOutputTokens || DEFAULT_JUDGE_MAX_OUTPUT_TOKENS,
    };
    await mkdir(config.outputDir, { recursive: true });
    const reports = await loadResultReports(cwd, options.resultPaths, config.outputDir);
    if (options.judge) {
      validateJudgeConfig(config, apiKeys);
      await judgeReports({ reports, apiKeys, config });
    }
    const comparisonPath = path.join(config.outputDir, 'index.html');
    await writeFile(comparisonPath, renderComparisonPage(reports));
    console.log(`Wrote comparison page: ${path.relative(cwd, comparisonPath)}`);
    if (config.pagesDir) {
      await exportPagesReport({ cwd, reports, pagesDir: config.pagesDir });
    }
    return;
  }

  if (!options.casePath && !options.casePaths && !options.allCases) {
    throw new Error('Missing required --case <path>, --cases <csv>, --all-cases, or --results <csv> option.');
  }

  const strategies = options.strategies || DEFAULT_STRATEGIES;
  validateStrategies(strategies);
  validateStrategyKeys(strategies, apiKeys);

  const providers = resolveProviders(options.providers, apiKeys, strategies);
  const models = {
    openai: options.openaiModels || (options.openaiModel ? [options.openaiModel] : [DEFAULT_OPENAI_MODEL]),
    claude: options.claudeModels || (options.claudeModel ? [options.claudeModel] : [DEFAULT_CLAUDE_MODEL]),
  };

  const config = {
    models,
    maxOutputTokens: options.maxOutputTokens || DEFAULT_MAX_OUTPUT_TOKENS,
    outputDir: path.resolve(cwd, options.outputDir || DEFAULT_OUTPUT_DIR),
    pagesDir: options.pagesDir ? path.resolve(cwd, options.pagesDir) : '',
    mock: options.mock,
    judgeProvider: options.judgeProvider || DEFAULT_JUDGE_PROVIDER,
    judgeModel: options.judgeModel || DEFAULT_JUDGE_MODEL,
    judgeMaxOutputTokens: options.judgeMaxOutputTokens || DEFAULT_JUDGE_MAX_OUTPUT_TOKENS,
  };

  const caseFilePaths = await resolveCaseFilePaths(cwd, options);
  const preparedCases = [];
  for (const caseFilePath of caseFilePaths) {
    preparedCases.push(await prepareCase(caseFilePath));
  }

  if (options.dryRun) {
    for (const preparedCase of preparedCases) {
      printDryRun({ ...preparedCase, strategies, providers, config, apiKeys });
    }
    return;
  }

  await mkdir(config.outputDir, { recursive: true });

  const reports = [];
  for (const preparedCase of preparedCases) {
    reports.push(await runCase({ cwd, preparedCase, strategies, providers, apiKeys, config }));
  }
  if (options.judge) {
    validateJudgeConfig(config, apiKeys);
    await judgeReports({ reports, apiKeys, config });
  }

  const comparisonPath = path.join(config.outputDir, 'index.html');
  await writeFile(comparisonPath, renderComparisonPage(reports));
  console.log(`Wrote comparison page: ${path.relative(cwd, comparisonPath)}`);
  if (config.pagesDir) {
    await exportPagesReport({ cwd, reports, pagesDir: config.pagesDir });
  }
}

function parseArgs(args) {
  const options = {
    casePath: '',
    casePaths: null,
    resultPaths: null,
    allCases: false,
    strategies: null,
    providers: null,
    openaiModel: '',
    claudeModel: '',
    openaiModels: null,
    claudeModels: null,
    outputDir: '',
    pagesDir: '',
    maxOutputTokens: 0,
    judge: false,
    judgeProvider: '',
    judgeModel: '',
    judgeMaxOutputTokens: 0,
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
    } else if (arg === '--results') {
      options.resultPaths = splitCsv(next());
    } else if (arg === '--all-cases') {
      options.allCases = true;
    } else if (arg === '--strategies') {
      options.strategies = splitCsv(next());
    } else if (arg === '--providers') {
      options.providers = splitCsv(next());
    } else if (arg === '--openai-model') {
      options.openaiModel = next();
    } else if (arg === '--claude-model') {
      options.claudeModel = next();
    } else if (arg === '--openai-models') {
      options.openaiModels = splitCsv(next());
    } else if (arg === '--claude-models') {
      options.claudeModels = splitCsv(next());
    } else if (arg === '--output-dir') {
      options.outputDir = next();
    } else if (arg === '--pages-dir') {
      options.pagesDir = next();
    } else if (arg === '--max-output-tokens') {
      options.maxOutputTokens = Number(next());
      if (!Number.isFinite(options.maxOutputTokens) || options.maxOutputTokens <= 0) {
        throw new Error('--max-output-tokens must be a positive number.');
      }
    } else if (arg === '--judge') {
      options.judge = true;
    } else if (arg === '--judge-provider') {
      options.judgeProvider = next();
    } else if (arg === '--judge-model') {
      options.judgeModel = next();
    } else if (arg === '--judge-max-output-tokens') {
      options.judgeMaxOutputTokens = Number(next());
      if (!Number.isFinite(options.judgeMaxOutputTokens) || options.judgeMaxOutputTokens <= 0) {
        throw new Error('--judge-max-output-tokens must be a positive number.');
      }
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
  console.log(`AI action evaluation harness

Usage:
  node scripts/ai-eval.mjs --case eval/cases/sample-ask.json
  node scripts/ai-eval.mjs --all-cases
  node scripts/ai-eval.mjs --cases eval/cases/sample-ask.json,eval/cases/sample-describe.json
  node scripts/ai-eval.mjs --results eval/results/sample-ask.json,eval/results/sample-describe.json
  node scripts/ai-eval.mjs --case eval/cases/sample-ask.json --strategies single,parallel,mixed-provider
  node scripts/ai-eval.mjs --case eval/cases/sample-ask.json --openai-models gpt-5.4,gpt-5.4-mini --claude-models claude-sonnet-4-6,claude-haiku-4-5
  node scripts/ai-eval.mjs --case eval/cases/sample-ask.json --dry-run

Options:
  --case <path>                 Run one case JSON file.
  --cases <csv>                 Run multiple case JSON files.
  --results <csv>               Build only the comparison HTML from existing result JSON files.
  --all-cases                   Run every JSON case in eval/cases.
  --strategies <csv>            single, parallel, mixed-provider. Defaults to all.
  --providers <csv>             openai, claude. Defaults to providers with API keys.
  --openai-model <model>        Single OpenAI model. Defaults to ${DEFAULT_OPENAI_MODEL}.
  --claude-model <model>        Single Claude model. Defaults to ${DEFAULT_CLAUDE_MODEL}.
  --openai-models <csv>         Multiple OpenAI models to compare.
  --claude-models <csv>         Multiple Claude models to compare.
  --max-output-tokens <number>  Defaults to ${DEFAULT_MAX_OUTPUT_TOKENS}.
  --judge                       Evaluate each run with a judge model and update reports.
  --judge-provider <provider>   openai or claude. Defaults to ${DEFAULT_JUDGE_PROVIDER}.
  --judge-model <model>         Defaults to ${DEFAULT_JUDGE_MODEL}.
  --judge-max-output-tokens <number>
                                  Defaults to ${DEFAULT_JUDGE_MAX_OUTPUT_TOKENS}.
  --output-dir <path>           Defaults to ${DEFAULT_OUTPUT_DIR}.
  --pages-dir <path>            Also export a GitHub Pages static bundle.
  --dry-run                     Validate config and print the run matrix without API calls.
  --mock                        Generate report artifacts with mock model responses.
`);
}

async function loadResultReports(cwd, resultPaths, outputDir) {
  const reports = [];
  for (const resultPath of resultPaths) {
    const absolutePath = path.resolve(cwd, resultPath);
    const report = JSON.parse(await readFile(absolutePath, 'utf8'));
    report.artifacts = {
      jsonPath: absolutePath,
      mdPath: absolutePath.replace(/\.json$/, '.md'),
      jsonRelativePath: path.relative(outputDir, absolutePath),
      mdRelativePath: path.relative(outputDir, absolutePath.replace(/\.json$/, '.md')),
    };
    reports.push(report);
  }
  return reports;
}

async function exportPagesReport({ cwd, reports, pagesDir }) {
  const assetsDir = path.join(pagesDir, 'assets');
  await mkdir(assetsDir, { recursive: true });
  const imagePaths = collectReportImagePaths(reports);
  const replacements = new Map();

  for (const imagePath of imagePaths) {
    if (!existsSync(imagePath)) {
      continue;
    }
    const assetName = sanitizeAssetName(imagePath);
    const assetPath = path.join(assetsDir, assetName);
    await copyFile(imagePath, assetPath);
    replacements.set(imagePathToFileUrl(imagePath), `assets/${assetName}`);
  }

  let html = renderComparisonPage(reports);
  for (const [from, to] of replacements) {
    html = html.replaceAll(from, to);
  }

  const pagePath = path.join(pagesDir, 'index.html');
  await writeFile(pagePath, html);
  console.log(`Wrote GitHub Pages report: ${path.relative(cwd, pagePath)}`);
}

function collectReportImagePaths(reports) {
  const paths = new Set();
  for (const report of reports) {
    if (report.metadata?.imagePath) {
      paths.add(report.metadata.imagePath);
    }
    for (const image of Object.values(report.metadata?.providerImages || {})) {
      if (image?.path) {
        paths.add(image.path);
      }
    }
  }
  return [...paths];
}

function sanitizeAssetName(imagePath) {
  return path.basename(imagePath).replace(/[^a-z0-9._-]+/gi, '-').toLowerCase();
}

async function resolveCaseFilePaths(cwd, options) {
  if (options.allCases) {
    const casesDir = path.join(cwd, DEFAULT_CASES_DIR);
    const names = await readdir(casesDir);
    return names
      .filter((name) => name.endsWith('.json'))
      .sort()
      .map((name) => path.join(casesDir, name));
  }

  if (options.casePaths) {
    return options.casePaths.map((casePath) => path.resolve(cwd, casePath));
  }

  return [path.resolve(cwd, options.casePath)];
}

async function prepareCase(caseFilePath) {
  const testCase = await loadCase(caseFilePath);
  const images = await loadCaseImages(caseFilePath, testCase);
  const image = images.default;
  validateCase(testCase);
  return { caseFilePath, testCase, image, images };
}

async function loadEnv(envPath) {
  const env = {};
  if (!existsSync(envPath)) {
    return env;
  }

  const raw = await readFile(envPath, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const separatorIndex = trimmed.indexOf('=');
    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    let value = trimmed.slice(separatorIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

async function loadCase(caseFilePath) {
  if (!existsSync(caseFilePath)) {
    throw new Error(`Case file not found: ${caseFilePath}`);
  }

  try {
    return JSON.parse(await readFile(caseFilePath, 'utf8'));
  } catch (error) {
    throw new Error(`Failed to parse case JSON: ${caseFilePath}\n${error.message}`);
  }
}

async function loadImage(caseFilePath, imagePath) {
  if (!imagePath || typeof imagePath !== 'string') {
    throw new Error('Case must include imagePath.');
  }

  const absolutePath = path.resolve(path.dirname(caseFilePath), imagePath);
  if (!existsSync(absolutePath)) {
    throw new Error(`Image file not found: ${absolutePath}`);
  }

  const mediaType = mediaTypeForPath(absolutePath);
  const buffer = await readFile(absolutePath);
  const base64 = buffer.toString('base64');
  return {
    path: absolutePath,
    mediaType,
    base64,
    bytes: buffer.byteLength,
    dataUrl: `data:${mediaType};base64,${base64}`,
  };
}

async function loadCaseImages(caseFilePath, testCase) {
  const images = {
    default: await loadImage(caseFilePath, testCase.imagePath),
  };
  for (const provider of ['openai', 'claude']) {
    const overridePath = testCase.providerImageOverrides?.[provider];
    if (overridePath) {
      images[provider] = await loadImage(caseFilePath, overridePath);
    }
  }
  return images;
}

function validateCase(testCase) {
  const validActions = new Set(['translate', 'describe', 'ask']);
  const validInputModes = new Set(['ocr-image', 'ocr-only', 'image-only']);
  const requiredFields = ['id', 'action', 'ocrText', 'imagePath'];

  for (const field of requiredFields) {
    if (!testCase[field] || typeof testCase[field] !== 'string') {
      throw new Error(`Case must include string field: ${field}`);
    }
  }

  if (!validActions.has(testCase.action)) {
    throw new Error(`Invalid action: ${testCase.action}. Expected translate, describe, or ask.`);
  }

  if (testCase.action === 'ask' && (!testCase.question || typeof testCase.question !== 'string')) {
    throw new Error('ask case must include string field: question');
  }

  if (testCase.action === 'translate' && !testCase.targetLanguage) {
    testCase.targetLanguage = 'ko';
  }

  if (!testCase.inputMode) {
    testCase.inputMode = 'ocr-image';
  }

  if (!validInputModes.has(testCase.inputMode)) {
    throw new Error(`Invalid inputMode: ${testCase.inputMode}. Expected ocr-image, ocr-only, or image-only.`);
  }
}

function resolveProviders(requestedProviders, apiKeys, strategies) {
  const needsMixed = strategies.includes('mixed-provider');
  const providers = requestedProviders || ['openai', 'claude'].filter((provider) => Boolean(apiKeys[provider]));
  if (needsMixed) {
    for (const provider of ['openai', 'claude']) {
      if (!providers.includes(provider)) {
        providers.push(provider);
      }
    }
  }

  if (providers.length === 0) {
    throw new Error('No providers available. Set OPENAI_API_KEY, CODEX_API_KEY, or CLAUDE_API_KEY in .env.');
  }

  for (const provider of providers) {
    if (!['openai', 'claude'].includes(provider)) {
      throw new Error(`Invalid provider: ${provider}. Expected openai or claude.`);
    }
    if (!apiKeys[provider]) {
      throw new Error(`Missing API key for provider: ${provider}`);
    }
  }
  return providers;
}

function validateStrategies(strategies) {
  const validStrategies = new Set(DEFAULT_STRATEGIES);
  for (const strategy of strategies) {
    if (!validStrategies.has(strategy)) {
      throw new Error(`Invalid strategy: ${strategy}. Expected ${DEFAULT_STRATEGIES.join(', ')}.`);
    }
  }
}

function validateStrategyKeys(strategies, apiKeys) {
  if (strategies.includes('mixed-provider') && (!apiKeys.openai || !apiKeys.claude)) {
    throw new Error('mixed-provider requires both OpenAI and Claude API keys.');
  }
}

function printDryRun({ testCase, caseFilePath, image, images, strategies, providers, config, apiKeys }) {
  console.log('Dry run OK');
  console.log(`Case: ${testCase.id} (${testCase.action})`);
  console.log(`Case path: ${caseFilePath}`);
  console.log(`Image: ${image.path} (${image.mediaType}, ${image.bytes} bytes)`);
  if (images?.openai) {
    console.log(`OpenAI image override: ${images.openai.path} (${images.openai.mediaType}, ${images.openai.bytes} bytes)`);
  }
  if (images?.claude) {
    console.log(`Claude image override: ${images.claude.path} (${images.claude.mediaType}, ${images.claude.bytes} bytes)`);
  }
  console.log(`Input mode: ${testCase.inputMode || 'ocr-image'}`);
  console.log(`OpenAI image detail: ${testCase.openaiImageDetail || 'auto'}`);
  console.log(`Expected findings: ${Array.isArray(testCase.expectedFindings) ? testCase.expectedFindings.length : 0}`);
  console.log(`OpenAI key: ${apiKeys.openai ? 'present' : 'missing'}`);
  console.log(`Claude key: ${apiKeys.claude ? 'present' : 'missing'}`);
  console.log(`OpenAI models: ${config.models.openai.join(', ')}`);
  console.log(`Claude models: ${config.models.claude.join(', ')}`);
  console.log(`Runs: ${buildRunMatrix({ strategies, providers, models: config.models }).map((run) => run.label).join(', ')}`);
}

async function runCase({ cwd, preparedCase, strategies, providers, apiKeys, config }) {
  const { caseFilePath, testCase, image, images } = preparedCase;
  const startedAt = new Date();
  const runMatrix = buildRunMatrix({ strategies, providers, models: config.models });
  const runs = [];

  for (const runConfig of runMatrix) {
    const context = { testCase, image, images, apiKeys, config, runConfig };
    if (runConfig.strategy === 'single') {
      runs.push(await runSingle(context));
    } else if (runConfig.strategy === 'parallel') {
      runs.push(await runParallel(context));
    } else {
      runs.push(await runMixedProvider(context));
    }
  }

  const scoredRuns = runs.map((run) => decorateRunQuality(testCase, run));
  const finishedAt = new Date();
  const report = {
    case: testCase,
    metadata: {
      caseFilePath,
      imagePath: image.path,
      imageMediaType: image.mediaType,
      imageBytes: image.bytes,
      providerImages: describeProviderImages(images),
      inputMode: testCase.inputMode || 'ocr-image',
      openaiImageDetail: testCase.openaiImageDetail || 'auto',
      imageFidelity: testCase.imageFidelity || '',
      imageTextPolicy: testCase.imageTextPolicy || '',
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      strategies,
      providers,
      models: config.models,
      requestStructure: describeRequestStructure(testCase),
    },
    runs: scoredRuns,
    analysis: analyzeRuns(scoredRuns),
    qualityNotes: '',
    winner: '',
  };

  const safeId = sanitizeFileName(testCase.id);
  const timestamp = toTimestamp(finishedAt);
  const jsonPath = path.join(config.outputDir, `${safeId}-${timestamp}.json`);
  const mdPath = path.join(config.outputDir, `${safeId}-${timestamp}.md`);

  await writeFile(jsonPath, `${JSON.stringify(report, null, 2)}\n`);
  await writeFile(mdPath, renderMarkdownReport(report));

  report.artifacts = {
    jsonPath,
    mdPath,
    jsonRelativePath: path.relative(config.outputDir, jsonPath),
    mdRelativePath: path.relative(config.outputDir, mdPath),
  };

  console.log(`Wrote JSON result: ${path.relative(cwd, jsonPath)}`);
  console.log(`Wrote Markdown report: ${path.relative(cwd, mdPath)}`);
  return report;
}

function buildRunMatrix({ strategies, providers, models }) {
  const runs = [];
  for (const strategy of strategies) {
    if (strategy === 'mixed-provider') {
      for (const openaiModel of models.openai) {
        for (const claudeModel of models.claude) {
          runs.push({
            label: `mixed-provider:openai=${openaiModel}:claude=${claudeModel}`,
            strategy,
            provider: 'mixed',
            openaiModel,
            claudeModel,
          });
        }
      }
      continue;
    }

    if (providers.includes('openai')) {
      for (const model of models.openai) {
        runs.push({
          label: `${strategy}:openai:${model}`,
          strategy,
          provider: 'openai',
          openaiModel: model,
          claudeModel: null,
        });
      }
    }

    if (providers.includes('claude')) {
      for (const model of models.claude) {
        runs.push({
          label: `${strategy}:claude:${model}`,
          strategy,
          provider: 'claude',
          openaiModel: null,
          claudeModel: model,
        });
      }
    }
  }
  return runs;
}

async function runSingle(context) {
  return runTimed(context.runConfig, async () => {
    const call = await callModel(context.runConfig.provider, {
      name: 'single_action',
      prompt: buildSinglePrompt(context.testCase),
      includeImage: true,
    }, context);

    return {
      status: 'success',
      output: call.text,
      calls: [call],
    };
  });
}

async function runParallel(context) {
  return runParallelWithMerge({
    context,
    tasks: buildParallelTasks(context.testCase),
    mergeProvider: context.runConfig.provider,
  });
}

async function runMixedProvider(context) {
  return runParallelWithMerge({
    context,
    tasks: buildMixedProviderTasks(context.testCase),
    mergeProvider: 'claude',
  });
}

async function runParallelWithMerge({ context, tasks, mergeProvider }) {
  const started = performance.now();
  let firstResultMs = null;
  const timedTasks = tasks.map((taskConfig) => (
    callModel(taskConfig.provider || context.runConfig.provider, taskConfig, context)
      .then((call) => {
        firstResultMs ??= Math.round(performance.now() - started);
        return { status: 'fulfilled', call };
      })
      .catch((error) => {
        firstResultMs ??= Math.round(performance.now() - started);
        return {
          status: 'rejected',
          error: {
            name: taskConfig.name,
            provider: taskConfig.provider || context.runConfig.provider,
            message: formatError(error),
          },
        };
      })
  ));

  const settled = await Promise.all(timedTasks);
  const successfulCalls = settled.filter((item) => item.status === 'fulfilled').map((item) => item.call);
  const failedCalls = settled.filter((item) => item.status === 'rejected').map((item) => item.error);

  if (successfulCalls.length === 0) {
    return decorateRunResult(context.runConfig, {
      status: 'failed',
      latencyTotalMs: Math.round(performance.now() - started),
      latencyFirstResultMs: firstResultMs,
      output: '',
      calls: [],
      failedCalls,
    });
  }

  let mergeCall;
  try {
    mergeCall = await callModel(mergeProvider, {
      name: 'merge',
      prompt: buildMergePrompt(context.testCase, successfulCalls, failedCalls),
      includeImage: false,
    }, context);
  } catch (error) {
    return decorateRunResult(context.runConfig, {
      status: 'partial_success',
      latencyTotalMs: Math.round(performance.now() - started),
      latencyFirstResultMs: firstResultMs,
      output: successfulCalls.map((call) => `## ${call.taskName}\n${call.text}`).join('\n\n'),
      calls: successfulCalls,
      failedCalls: [...failedCalls, { name: 'merge', provider: mergeProvider, message: formatError(error) }],
    });
  }

  return decorateRunResult(context.runConfig, {
    status: failedCalls.length > 0 ? 'partial_success' : 'success',
    latencyTotalMs: Math.round(performance.now() - started),
    latencyFirstResultMs: firstResultMs,
    output: mergeCall.text,
    calls: [...successfulCalls, mergeCall],
    failedCalls,
  });
}

async function runTimed(runConfig, execute) {
  const started = performance.now();
  try {
    const result = await execute();
    const latencyTotalMs = Math.round(performance.now() - started);
    return decorateRunResult(runConfig, {
      ...result,
      latencyTotalMs,
      latencyFirstResultMs: latencyTotalMs,
      failedCalls: [],
    });
  } catch (error) {
    const latencyTotalMs = Math.round(performance.now() - started);
    return decorateRunResult(runConfig, {
      status: 'failed',
      latencyTotalMs,
      latencyFirstResultMs: latencyTotalMs,
      output: '',
      calls: [],
      failedCalls: [{ name: 'single_action', provider: runConfig.provider, message: formatError(error) }],
    });
  }
}

function decorateRunResult(runConfig, result) {
  const calls = result.calls || [];
  const usage = summarizeUsage(calls);
  return {
    label: runConfig.label,
    strategy: runConfig.strategy,
    provider: runConfig.provider,
    openaiModel: runConfig.openaiModel,
    claudeModel: runConfig.claudeModel,
    status: result.status,
    latencyTotalMs: result.latencyTotalMs,
    latencyFirstResultMs: result.latencyFirstResultMs,
    output: result.output || '',
    calls,
    failedCalls: result.failedCalls || [],
    usage,
    estimatedCostUsd: estimateCallsCost(calls),
  };
}

function decorateRunQuality(testCase, run) {
  return {
    ...run,
    quality: scoreExpectedFindings(testCase.expectedFindings, run.output),
  };
}

function scoreExpectedFindings(expectedFindings, output) {
  if (!Array.isArray(expectedFindings) || expectedFindings.length === 0) {
    return {
      expectedCount: 0,
      matchedCount: 0,
      score: null,
      matched: [],
      missing: [],
    };
  }

  const normalizedOutput = normalizeForFindingMatch(output || '');
  const findings = expectedFindings.map((finding) => {
    const label = typeof finding === 'string' ? finding : finding.label || finding.value || '';
    const candidates = typeof finding === 'string'
      ? [finding]
      : finding.anyOf || [finding.value || finding.label || ''];
    const matched = candidates.some((candidate) => (
      normalizeForFindingMatch(candidate) && normalizedOutput.includes(normalizeForFindingMatch(candidate))
    ));
    return { label, matched, candidates };
  });

  const matched = findings.filter((finding) => finding.matched).map((finding) => finding.label);
  const missing = findings.filter((finding) => !finding.matched).map((finding) => finding.label);
  return {
    expectedCount: findings.length,
    matchedCount: matched.length,
    score: Number((matched.length / findings.length).toFixed(3)),
    matched,
    missing,
  };
}

function normalizeForFindingMatch(value) {
  return String(value)
    .toLowerCase()
    .normalize('NFKC')
    .replace(/[,\s원()]/g, '');
}

async function callModel(provider, taskConfig, context) {
  if (context.config.mock) {
    return callMockModel(provider, taskConfig, context);
  }

  if (provider === 'openai') {
    return callOpenAI(taskConfig, context);
  }
  if (provider === 'claude') {
    return callClaude(taskConfig, context);
  }
  throw new Error(`Unknown provider: ${provider}`);
}

async function callMockModel(provider, taskConfig, context) {
  const started = performance.now();
  const model = provider === 'openai' ? context.runConfig.openaiModel : context.runConfig.claudeModel;
  await new Promise((resolve) => setTimeout(resolve, provider === 'openai' ? 35 : 55));
  const inputTokens = Math.max(80, Math.ceil(taskConfig.prompt.length / 4));
  const outputTokens = provider === 'openai' ? 120 : 150;

  return {
    taskName: taskConfig.name,
    provider,
    model,
    latencyMs: Math.round(performance.now() - started),
    text: [
      `bubbleText: ${context.testCase.action} 액션의 ${taskConfig.name} mock 결과입니다.`,
      `detail: ${context.testCase.id} 케이스를 ${provider}/${model}로 처리한 것으로 가정했습니다.`,
      `evidence: inputMode=${context.testCase.inputMode || 'ocr-image'} 설정을 사용했습니다.`,
      'confidence: medium',
    ].join('\n'),
    usage: { inputTokens, outputTokens },
    raw: { mock: true },
  };
}

async function callOpenAI(taskConfig, context) {
  const started = performance.now();
  const model = context.runConfig.openaiModel;
  const content = [{ type: 'input_text', text: taskConfig.prompt }];
  if (taskConfig.includeImage !== false && shouldIncludeImage(context.testCase)) {
    const image = imageForProvider(context, 'openai');
    content.push({
      type: 'input_image',
      image_url: image.dataUrl,
      detail: context.testCase.openaiImageDetail || 'auto',
    });
  }

  const response = await fetchJson(OPENAI_RESPONSES_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${context.apiKeys.openai}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      input: [{ role: 'user', content }],
      max_output_tokens: context.config.maxOutputTokens,
    }),
  });

  return {
    taskName: taskConfig.name,
    provider: 'openai',
    model,
    latencyMs: Math.round(performance.now() - started),
    text: extractOpenAIText(response),
    usage: normalizeOpenAIUsage(response.usage),
    raw: response,
  };
}

async function callClaude(taskConfig, context) {
  const started = performance.now();
  const model = context.runConfig.claudeModel;
  const content = [];
  if (taskConfig.includeImage !== false && shouldIncludeImage(context.testCase)) {
    const image = imageForProvider(context, 'claude');
    content.push({
      type: 'image',
      source: {
        type: 'base64',
        media_type: image.mediaType,
        data: image.base64,
      },
    });
  }
  content.push({ type: 'text', text: taskConfig.prompt });

  const response = await fetchJson(CLAUDE_MESSAGES_URL, {
    method: 'POST',
    headers: {
      'x-api-key': context.apiKeys.claude,
      'anthropic-version': CLAUDE_API_VERSION,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: context.config.maxOutputTokens,
      messages: [{ role: 'user', content }],
    }),
  });

  return {
    taskName: taskConfig.name,
    provider: 'claude',
    model,
    latencyMs: Math.round(performance.now() - started),
    text: extractClaudeText(response),
    usage: normalizeClaudeUsage(response.usage),
    raw: response,
  };
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

function buildSinglePrompt(testCase) {
  return [
    commonPromptHeader(testCase),
    '선택된 액션 하나를 한 번의 응답으로 처리해줘.',
    actionInstruction(testCase),
    outputInstruction(),
  ].join('\n\n');
}

function buildParallelTasks(testCase) {
  if (testCase.action === 'translate') {
    return [
      task('text_translation', 'OCR 텍스트를 목표 언어로 번역해줘. 원문에 없는 내용은 추가하지 마.'),
      task('visual_context', '이미지를 보고 번역에 영향을 줄 화면 맥락, UI 유형, 고유명사, 주의할 표현을 정리해줘.'),
      task('text_structure', 'OCR 텍스트를 제목, 본문, 버튼, 메뉴, 표, 에러 메시지 등으로 구조화해줘.'),
    ].map((item) => withCasePrompt(item, testCase));
  }

  if (testCase.action === 'describe') {
    return [
      task('visual_summary', '이미지의 시각 정보만 중심으로 객체, UI 구성, 레이아웃, 상태를 설명해줘.'),
      task('ocr_summary', 'OCR 텍스트에서 중요한 제목, 경고, 숫자, 버튼, 핵심 문장을 요약해줘.'),
      task('screen_intent', '이 화면의 목적이나 종류를 추정하고 근거를 설명해줘.'),
      task('focus', '사용자가 주목해야 할 오류, 경고, 중요한 버튼, 입력 영역을 찾아줘.'),
    ].map((item) => withCasePrompt(item, testCase));
  }

  return [
    task('question_intent', '사용자 질문이 무엇을 묻는지 의도를 분류하고 답변 기준을 정리해줘.'),
    task('text_evidence', 'OCR 텍스트에서 사용자 질문과 관련 있는 근거 문장, 숫자, 에러 메시지를 찾아줘.'),
    task('visual_evidence', '이미지에서 사용자 질문과 관련 있는 시각 근거를 찾아줘.'),
    task('quick_answer', '이미지, OCR 텍스트, 사용자 질문을 보고 빠른 답변 초안을 작성해줘. 확신도와 추정 여부를 포함해줘.'),
  ].map((item) => withCasePrompt(item, testCase));
}

function buildMixedProviderTasks(testCase) {
  return buildParallelTasks(testCase).map((item) => {
    if (['visual_context', 'visual_summary', 'focus', 'visual_evidence'].includes(item.name)) {
      return { ...item, provider: 'claude' };
    }
    return { ...item, provider: 'openai' };
  });
}

function buildMergePrompt(testCase, successfulCalls, failedCalls) {
  const taskOutputs = successfulCalls.map((call) => (
    `### ${call.taskName} (${call.provider}/${call.model})\n${call.text}`
  )).join('\n\n');
  const failures = failedCalls.length > 0
    ? failedCalls.map((call) => `- ${call.name} (${call.provider || 'unknown'}): ${call.message}`).join('\n')
    : '- 없음';

  return [
    commonPromptHeader(testCase),
    '아래 병렬 작업 결과를 종합해 최종 사용자 응답을 만들어줘.',
    actionInstruction(testCase),
    `병렬 작업 결과:\n\n${taskOutputs}`,
    `실패한 작업:\n${failures}`,
    '실패한 작업이 있으면 가능한 결과만 사용하고, 확실하지 않은 부분은 명시해줘.',
    outputInstruction(),
  ].join('\n\n');
}

function commonPromptHeader(testCase) {
  return [
    '너는 Buddy 데스크톱 AI 도우미의 스크린샷 분석 엔진이야.',
    `액션: ${testCase.action}`,
    `입력 모드: ${testCase.inputMode || 'ocr-image'}`,
    shouldIncludeImage(testCase) ? '이미지 입력: 포함됨' : '이미지 입력: 제외됨',
    shouldIncludeOcrText(testCase) ? 'OCR 텍스트: 포함됨' : 'OCR 텍스트: 제외됨',
    testCase.imageTextPolicy ? `OCR/이미지 텍스트 정책: ${testCase.imageTextPolicy}` : '',
    testCase.targetLanguage ? `목표 언어: ${testCase.targetLanguage}` : '',
    testCase.question ? `사용자 질문: ${testCase.question}` : '',
    shouldIncludeOcrText(testCase) ? `OCR 텍스트:\n${testCase.ocrText}` : '',
  ].filter(Boolean).join('\n');
}

function actionInstruction(testCase) {
  if (testCase.action === 'translate') {
    return [
      `OCR 텍스트를 ${testCase.targetLanguage || 'ko'}로 번역해줘.`,
      '이미지는 문맥 참고용으로 사용하고, UI 버튼은 짧고 자연스럽게, 에러 메시지는 기술적으로 정확하게 번역해줘.',
    ].join('\n');
  }

  if (testCase.action === 'describe') {
    return [
      '스크린샷에 무엇이 보이는지 설명해줘.',
      '시각 정보와 OCR 텍스트를 함께 사용해 화면 종류, 상황, 주목할 포인트를 정리해줘.',
    ].join('\n');
  }

  return [
    '사용자 질문에 답해줘.',
    '이미지와 OCR 텍스트를 근거로 삼고, 화면에서 확인되지 않는 내용은 추측이라고 표시해줘.',
  ].join('\n');
}

function outputInstruction() {
  return [
    '응답은 한국어로 작성해.',
    '아래 형식을 지켜줘.',
    '- bubbleText: Buddy 말풍선에 넣을 짧은 한 문장',
    '- detail: 사용자가 볼 상세 결과',
    '- evidence: 사용한 근거',
    '- confidence: high | medium | low',
  ].join('\n');
}

function task(name, instruction) {
  return { name, instruction, includeImage: true };
}

function withCasePrompt(item, testCase) {
  return {
    ...item,
    prompt: [
      commonPromptHeader(testCase),
      item.instruction,
      '이 작업의 결과만 간결하게 작성해줘.',
    ].join('\n\n'),
  };
}

function describeRequestStructure(testCase) {
  const parallelTasks = buildParallelTasks(testCase).map((item) => item.name);
  const mixedTasks = buildMixedProviderTasks(testCase).map((item) => ({
    task: item.name,
    provider: item.provider || 'openai',
  }));
  const input = [
    shouldIncludeImage(testCase) ? 'image' : '',
    shouldIncludeOcrText(testCase) ? 'ocrText' : '',
    ...(testCase.question ? ['question'] : []),
    ...(testCase.targetLanguage ? ['targetLanguage'] : []),
  ].filter(Boolean);

  return {
    action: testCase.action,
    inputMode: testCase.inputMode || 'ocr-image',
    input,
    image: {
      sentToModel: shouldIncludeImage(testCase),
      openaiDetail: testCase.openaiImageDetail || 'auto',
      fidelity: testCase.imageFidelity || '',
    },
    textPolicy: testCase.imageTextPolicy || '',
    expectedFindings: Array.isArray(testCase.expectedFindings) ? testCase.expectedFindings.length : 0,
    single: ['single_action'],
    parallel: [...parallelTasks, 'merge'],
    mixedProvider: [...mixedTasks, { task: 'merge', provider: 'claude' }],
  };
}

function shouldIncludeImage(testCase) {
  return (testCase.inputMode || 'ocr-image') !== 'ocr-only';
}

function shouldIncludeOcrText(testCase) {
  return (testCase.inputMode || 'ocr-image') !== 'image-only';
}

function imageForProvider(context, provider) {
  return context.images?.[provider] || context.images?.default || context.image;
}

function describeProviderImages(images = {}) {
  const result = {};
  for (const provider of ['default', 'openai', 'claude']) {
    if (!images[provider]) {
      continue;
    }
    result[provider] = {
      path: images[provider].path,
      mediaType: images[provider].mediaType,
      bytes: images[provider].bytes,
    };
  }
  return result;
}

function analyzeRuns(runs) {
  const successful = runs.filter((run) => ['success', 'partial_success'].includes(run.status));
  const fastest = minBy(successful, (run) => run.latencyTotalMs);
  const fastestFirst = minBy(successful, (run) => run.latencyFirstResultMs ?? Number.POSITIVE_INFINITY);
  const cheapest = minBy(successful, (run) => run.estimatedCostUsd);
  const highestQuality = maxBy(
    successful.filter((run) => run.quality?.score !== null && run.quality?.score !== undefined),
    (run) => run.quality.score,
  );
  const failed = runs.filter((run) => run.status === 'failed');
  const baseline = successful.find((run) => run.strategy === 'single');

  return {
    fastestRun: fastest?.label || '',
    fastestFirstResultRun: fastestFirst?.label || '',
    cheapestRun: cheapest?.label || '',
    highestQualityRun: highestQuality?.label || '',
    failedRuns: failed.map((run) => run.label),
    notes: buildAnalysisNotes({ fastest, fastestFirst, cheapest, highestQuality, failed, baseline }),
  };
}

function buildAnalysisNotes({ fastest, fastestFirst, cheapest, highestQuality, failed, baseline }) {
  const notes = [];
  if (fastest) {
    notes.push(`최종 응답 기준 가장 빠른 실행은 ${fastest.label} (${fastest.latencyTotalMs}ms)입니다.`);
  }
  if (fastestFirst) {
    notes.push(`첫 결과 기준 가장 빠른 실행은 ${fastestFirst.label} (${fastestFirst.latencyFirstResultMs}ms)입니다.`);
  }
  if (cheapest) {
    notes.push(`추정 비용 기준 가장 저렴한 실행은 ${cheapest.label} ($${cheapest.estimatedCostUsd})입니다.`);
  }
  if (highestQuality) {
    notes.push(`expected findings 기준 가장 많이 맞춘 실행은 ${highestQuality.label} (${highestQuality.quality.matchedCount}/${highestQuality.quality.expectedCount})입니다.`);
  }
  if (baseline && fastest && fastest.label !== baseline.label) {
    const diff = baseline.latencyTotalMs - fastest.latencyTotalMs;
    notes.push(`단일 요청 기준선 ${baseline.label} 대비 ${fastest.label}은 ${diff}ms 차이가 납니다.`);
  }
  if (failed.length > 0) {
    notes.push(`실패한 실행이 ${failed.length}개 있습니다. 모델명, 권한, provider payload를 확인해야 합니다.`);
  }
  if (notes.length === 0) {
    notes.push('성공한 실행 결과가 없어 비교 분석을 만들 수 없습니다.');
  }
  return notes;
}

function extractOpenAIText(response) {
  if (typeof response.output_text === 'string' && response.output_text) {
    return response.output_text;
  }

  const parts = [];
  for (const output of response.output || []) {
    for (const content of output.content || []) {
      if (typeof content.text === 'string') {
        parts.push(content.text);
      }
    }
  }
  return parts.join('\n').trim();
}

function extractClaudeText(response) {
  return (response.content || [])
    .filter((item) => item.type === 'text' && typeof item.text === 'string')
    .map((item) => item.text)
    .join('\n')
    .trim();
}

function normalizeOpenAIUsage(usage = {}) {
  return {
    inputTokens: usage.input_tokens ?? usage.prompt_tokens ?? 0,
    outputTokens: usage.output_tokens ?? usage.completion_tokens ?? 0,
  };
}

function normalizeClaudeUsage(usage = {}) {
  return {
    inputTokens: usage.input_tokens ?? 0,
    outputTokens: usage.output_tokens ?? 0,
  };
}

function summarizeUsage(calls) {
  return calls.reduce((summary, call) => ({
    inputTokens: summary.inputTokens + (call.usage?.inputTokens || 0),
    outputTokens: summary.outputTokens + (call.usage?.outputTokens || 0),
  }), { inputTokens: 0, outputTokens: 0 });
}

function estimateCallsCost(calls) {
  const total = calls.reduce((sum, call) => {
    const price = MODEL_PRICES_PER_MTOK[call.model];
    if (!price) {
      return sum;
    }
    return sum
      + ((call.usage?.inputTokens || 0) / 1_000_000) * price.input
      + ((call.usage?.outputTokens || 0) / 1_000_000) * price.output;
  }, 0);

  return Number(total.toFixed(6));
}

function validateJudgeConfig(config, apiKeys) {
  if (!['openai', 'claude'].includes(config.judgeProvider)) {
    throw new Error(`Invalid judge provider: ${config.judgeProvider}. Expected openai or claude.`);
  }
  if (!apiKeys[config.judgeProvider]) {
    throw new Error(`Missing API key for judge provider: ${config.judgeProvider}`);
  }
}

async function judgeReports({ reports, apiKeys, config }) {
  for (const report of reports) {
    const judge = await judgeReport({ report, apiKeys, config });
    report.judge = judge;
    applyJudgeEvaluations(report, judge);
    if (report.artifacts?.jsonPath) {
      await writeFile(report.artifacts.jsonPath, `${JSON.stringify(report, null, 2)}\n`);
    }
    if (report.artifacts?.mdPath) {
      await writeFile(report.artifacts.mdPath, renderMarkdownReport(report));
    }
    console.log(`Judged report: ${report.case.id} with ${judge.provider}/${judge.model}`);
  }
}

async function judgeReport({ report, apiKeys, config }) {
  const started = performance.now();
  const prompt = buildJudgePrompt(report);
  const image = await loadJudgeImage(report);
  const response = config.judgeProvider === 'openai'
    ? await callOpenAIJudge({ prompt, image, apiKeys, config })
    : await callClaudeJudge({ prompt, image, apiKeys, config });
  const parsed = parseJudgeResponse(response.text);
  const usage = response.usage || { inputTokens: 0, outputTokens: 0 };
  const model = config.judgeModel;
  return {
    provider: config.judgeProvider,
    model,
    latencyMs: Math.round(performance.now() - started),
    usage,
    estimatedCostUsd: estimateCallsCost([{ model, usage }]),
    criteria: parsed.criteria || defaultJudgeCriteria(),
    evaluations: Array.isArray(parsed.evaluations) ? parsed.evaluations : [],
    winner: parsed.winner || '',
    summary: parsed.summary || '',
    rawText: response.text,
  };
}

async function loadJudgeImage(report) {
  const imagePath = report.metadata?.imagePath;
  if (!imagePath || !existsSync(imagePath)) {
    return null;
  }
  const buffer = await readFile(imagePath);
  const mediaType = report.metadata?.imageMediaType || mediaTypeForPath(imagePath);
  return {
    path: imagePath,
    mediaType,
    base64: buffer.toString('base64'),
    dataUrl: `data:${mediaType};base64,${buffer.toString('base64')}`,
  };
}

async function callOpenAIJudge({ prompt, image, apiKeys, config }) {
  const content = [{ type: 'input_text', text: prompt }];
  if (image) {
    content.push({ type: 'input_image', image_url: image.dataUrl, detail: 'high' });
  }
  const response = await fetchJson(OPENAI_RESPONSES_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKeys.openai}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: config.judgeModel,
      input: [{ role: 'user', content }],
      max_output_tokens: config.judgeMaxOutputTokens,
    }),
  });

  return {
    text: extractOpenAIText(response),
    usage: normalizeOpenAIUsage(response.usage),
  };
}

async function callClaudeJudge({ prompt, image, apiKeys, config }) {
  const content = [];
  if (image) {
    content.push({
      type: 'image',
      source: {
        type: 'base64',
        media_type: image.mediaType,
        data: image.base64,
      },
    });
  }
  content.push({ type: 'text', text: prompt });
  const response = await fetchJson(CLAUDE_MESSAGES_URL, {
    method: 'POST',
    headers: {
      'x-api-key': apiKeys.claude,
      'anthropic-version': CLAUDE_API_VERSION,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: config.judgeModel,
      max_tokens: config.judgeMaxOutputTokens,
      messages: [{ role: 'user', content }],
    }),
  });

  return {
    text: extractClaudeText(response),
    usage: normalizeClaudeUsage(response.usage),
  };
}

function buildJudgePrompt(report) {
  const expectedFindings = Array.isArray(report.case.expectedFindings)
    ? report.case.expectedFindings.map((finding) => (
      typeof finding === 'string' ? finding : `${finding.label}: ${(finding.anyOf || [finding.value || '']).join(' | ')}`
    )).join('\n')
    : '없음';
  const runOutputs = report.runs.map((run) => [
    `### ${run.label}`,
    `provider/model: ${run.provider}/${run.openaiModel || run.claudeModel || 'mixed'}`,
    `findingScore: ${formatQualityScore(run.quality)}`,
    `latencyTotalMs: ${run.latencyTotalMs}`,
    `estimatedCostUsd: ${run.estimatedCostUsd}`,
    'output:',
    run.output || 'No output',
  ].join('\n')).join('\n\n');

  return [
    '너는 Buddy 스크린샷 AI 응답 품질을 평가하는 엄격한 judge야.',
    '같은 케이스에 대한 여러 모델 응답을 같은 기준으로 비교해.',
    '원본 이미지가 함께 제공되면 이미지의 실제 내용도 기준으로 삼아라.',
    '응답은 반드시 JSON 객체만 출력해. Markdown 코드펜스는 쓰지 마.',
    '',
    '평가 기준은 각 0~5점이다.',
    '- accuracy: 이미지/OCR/질문 기준 사실 정확도',
    '- completeness: 질문 또는 액션에 필요한 핵심 정보 포함도',
    '- grounding: 근거가 이미지/OCR에 잘 연결되는 정도',
    '- hallucinationSafety: 화면에 없는 내용을 단정하지 않는 정도',
    '- usefulness: 사용자가 이해하거나 다음 행동을 하기 쉬운 정도',
    '- conciseness: Buddy UI에 넣기 적절한 길이와 밀도',
    '- formatCompliance: bubbleText/detail/evidence/confidence 형식 준수',
    '',
    'overallScore는 위 7개 점수를 종합한 0~100 정수로 줘.',
    '각 run의 strengths, weaknesses는 짧은 한국어 배열로 줘.',
    'winner는 가장 제품 적용에 적합한 run label로 골라.',
    '',
    `caseId: ${report.case.id}`,
    `action: ${report.case.action}`,
    report.case.question ? `question: ${report.case.question}` : '',
    report.case.targetLanguage ? `targetLanguage: ${report.case.targetLanguage}` : '',
    `ocrText:\n${report.case.ocrText}`,
    `expectedFindings:\n${expectedFindings}`,
    '',
    'modelOutputs:',
    runOutputs,
    '',
    'JSON schema:',
    JSON.stringify({
      criteria: defaultJudgeCriteria(),
      evaluations: [{
        runLabel: 'string',
        scores: {
          accuracy: 0,
          completeness: 0,
          grounding: 0,
          hallucinationSafety: 0,
          usefulness: 0,
          conciseness: 0,
          formatCompliance: 0,
        },
        overallScore: 0,
        strengths: ['string'],
        weaknesses: ['string'],
        notes: 'string',
      }],
      winner: 'string',
      summary: 'string',
    }, null, 2),
  ].filter(Boolean).join('\n');
}

function parseJudgeResponse(text) {
  const trimmed = String(text || '').trim();
  const jsonText = trimmed.startsWith('{')
    ? trimmed
    : trimmed.slice(trimmed.indexOf('{'), trimmed.lastIndexOf('}') + 1);
  try {
    if (!jsonText || !jsonText.startsWith('{')) {
      throw new Error('No JSON object found.');
    }
    return JSON.parse(jsonText);
  } catch {
    return {
      criteria: defaultJudgeCriteria(),
      evaluations: [],
      winner: '',
      summary: 'Judge response JSON 파싱에 실패했습니다.',
      rawText: text,
    };
  }
}

function applyJudgeEvaluations(report, judge) {
  const evaluations = new Map((judge.evaluations || []).map((evaluation) => [evaluation.runLabel, evaluation]));
  report.runs = report.runs.map((run) => ({
    ...run,
    judge: evaluations.get(run.label) || null,
  }));
}

function defaultJudgeCriteria() {
  return {
    accuracy: '이미지/OCR/질문 기준 사실 정확도',
    completeness: '필요한 핵심 정보 포함도',
    grounding: '근거가 이미지/OCR에 연결되는 정도',
    hallucinationSafety: '화면에 없는 내용을 단정하지 않는 정도',
    usefulness: '사용자가 이해하거나 다음 행동을 하기 쉬운 정도',
    conciseness: 'Buddy UI에 적절한 길이와 밀도',
    formatCompliance: 'bubbleText/detail/evidence/confidence 형식 준수',
  };
}

function renderMarkdownReport(report) {
  const rows = report.runs.map((run) => (
    `| ${run.label} | ${run.status} | ${run.latencyTotalMs} | ${run.latencyFirstResultMs ?? '-'} | ${run.usage.inputTokens} | ${run.usage.outputTokens} | ${run.estimatedCostUsd} | ${formatQualityScore(run.quality)} | ${formatJudgeScore(run.judge)} |`
  )).join('\n');
  const notes = report.analysis.notes.map((note) => `- ${note}`).join('\n');
  const sections = report.runs.map(renderRunSection).join('\n');
  const judgeSection = report.judge ? renderMarkdownJudgeSection(report) : '';

  return `# AI Eval Report: ${report.case.id}

## Case

- action: ${report.case.action}
- startedAt: ${report.metadata.startedAt}
- finishedAt: ${report.metadata.finishedAt}
- image: ${report.metadata.imagePath}
- imageBytes: ${report.metadata.imageBytes}
- inputMode: ${report.metadata.inputMode}
- openaiImageDetail: ${report.metadata.openaiImageDetail}
- imageFidelity: ${report.metadata.imageFidelity || '-'}
- imageTextPolicy: ${report.metadata.imageTextPolicy || '-'}

## Request Structure

\`\`\`json
${JSON.stringify(report.metadata.requestStructure, null, 2)}
\`\`\`

## Summary

| Run | Status | Total ms | First result ms | Input tokens | Output tokens | Estimated cost USD | Finding score | Judge score |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
${rows}

## Analysis

${notes}

${judgeSection}

## Manual Review

- qualityNotes:
- winner:

## Quality Rubric

각 run의 결과 품질은 아래 기준으로 수동 평가합니다.

| Criterion | What to check |
| --- | --- |
| Accuracy | OCR 텍스트와 이미지에 있는 정보만으로 맞는 답을 했는가 |
| Grounding | 답변 근거를 텍스트/시각 정보로 명확히 설명했는가 |
| Concision | Buddy 말풍선/상세 패널에 넣기 적절한 길이인가 |
| Usefulness | 사용자가 다음 행동을 바로 이해할 수 있는가 |
| Overclaiming | 화면에 없는 내용을 단정하지 않았는가 |

${sections}
`;
}

function renderRunSection(run) {
  const calls = (run.calls || []).map((call) => (
    `- ${call.taskName}: ${call.provider}/${call.model}, ${call.latencyMs}ms, input ${call.usage?.inputTokens || 0}, output ${call.usage?.outputTokens || 0}`
  )).join('\n') || '- 없음';
  const failures = (run.failedCalls || []).map((call) => (
    `- ${call.name}: ${call.message}`
  )).join('\n') || '- 없음';

  return `## ${run.label}

- status: ${run.status}
- total latency: ${run.latencyTotalMs}ms
- first result latency: ${run.latencyFirstResultMs ?? '-'}ms
- estimated cost: $${run.estimatedCostUsd}
- finding score: ${formatQualityScore(run.quality)}
- judge score: ${formatJudgeScore(run.judge)}
- matched findings: ${run.quality?.matched?.join(', ') || '-'}
- missing findings: ${run.quality?.missing?.join(', ') || '-'}

### Calls
${calls}

### Failures
${failures}

### Output
${run.output || '_No output_'}
`;
}

function renderMarkdownJudgeSection(report) {
  const rows = (report.judge.evaluations || []).map((evaluation) => (
    `| ${evaluation.runLabel} | ${evaluation.overallScore ?? '-'} | ${evaluation.scores?.accuracy ?? '-'} | ${evaluation.scores?.completeness ?? '-'} | ${evaluation.scores?.grounding ?? '-'} | ${evaluation.scores?.hallucinationSafety ?? '-'} | ${evaluation.scores?.usefulness ?? '-'} | ${evaluation.scores?.conciseness ?? '-'} | ${evaluation.scores?.formatCompliance ?? '-'} | ${evaluation.notes || ''} |`
  )).join('\n');

  return `## Judge Review

- judge: ${report.judge.provider}/${report.judge.model}
- latency: ${report.judge.latencyMs}ms
- estimatedCostUsd: ${report.judge.estimatedCostUsd}
- winner: ${report.judge.winner || '-'}
- summary: ${report.judge.summary || '-'}

| Run | Overall | Accuracy | Completeness | Grounding | Hallucination safety | Usefulness | Conciseness | Format | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
${rows}
`;
}

function renderComparisonPage(reports) {
  const generatedAt = new Date().toISOString();
  const aggregate = aggregateReports(reports);
  const allRuns = reports.flatMap((report) => report.runs.map((run) => ({ report, run })));
  const fastest = minBy(allRuns.filter(({ run }) => run.status !== 'failed'), ({ run }) => run.latencyTotalMs);
  const fastestFirst = minBy(allRuns.filter(({ run }) => run.status !== 'failed'), ({ run }) => run.latencyFirstResultMs ?? Number.POSITIVE_INFINITY);
  const cheapest = minBy(allRuns.filter(({ run }) => run.status !== 'failed'), ({ run }) => run.estimatedCostUsd);
  const bestQuality = maxBy(
    allRuns.filter(({ run }) => run.status !== 'failed' && run.quality?.score !== null && run.quality?.score !== undefined),
    ({ run }) => run.quality.score,
  );
  const bestJudge = maxBy(
    allRuns.filter(({ run }) => run.status !== 'failed' && Number.isFinite(run.judge?.overallScore)),
    ({ run }) => run.judge.overallScore,
  );
  const totalCost = allRuns.reduce((sum, { run }) => sum + (run.estimatedCostUsd || 0), 0);
  const totalInput = allRuns.reduce((sum, { run }) => sum + (run.usage?.inputTokens || 0), 0);
  const totalOutput = allRuns.reduce((sum, { run }) => sum + (run.usage?.outputTokens || 0), 0);
  const nav = reports.map((report) => (
    `<a href="#case-${escapeAttribute(sanitizeFileName(report.case.id))}">${escapeHtml(report.case.id)}</a>`
  )).join('');
  const cards = reports.map((report) => {
    const fastest = readableRunLabel(report.analysis.fastestRun) || '-';
    const first = readableRunLabel(report.analysis.fastestFirstResultRun) || '-';
    const cheapest = readableRunLabel(report.analysis.cheapestRun) || '-';
    const quality = readableRunLabel(report.analysis.highestQualityRun) || '-';
    const notes = report.analysis.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('');
    return `<section class="case-card">
      <div class="case-head">
        <h2>${escapeHtml(caseTitle(report.case))}</h2>
        ${renderActionTag(report.case.action)}
      </div>
      <p class="section-note">${escapeHtml(casePurpose(report.case))}</p>
      <dl>
        <div><dt>Fastest</dt><dd>${escapeHtml(fastest)}</dd></div>
        <div><dt>First result</dt><dd>${escapeHtml(first)}</dd></div>
        <div><dt>Cheapest</dt><dd>${escapeHtml(cheapest)}</dd></div>
        <div><dt>Best quality</dt><dd>${escapeHtml(quality)}</dd></div>
        <div><dt>Report</dt><dd><a href="${escapeAttribute(report.artifacts?.mdRelativePath || '#')}">Markdown</a></dd></div>
      </dl>
      <ul>${notes}</ul>
    </section>`;
  }).join('\n');

  const rows = reports.flatMap((report) => report.runs.map((run) => (
    `<tr>
      <td>${escapeHtml(caseTitle(report.case))}</td>
      <td>${escapeHtml(report.case.action)}</td>
      <td>${escapeHtml(readableRunLabel(run.label))}</td>
      <td>${escapeHtml(run.status)}</td>
      <td class="num">${run.latencyTotalMs}</td>
      <td class="num">${run.latencyFirstResultMs ?? ''}</td>
      <td class="num">${run.usage.inputTokens}</td>
      <td class="num">${run.usage.outputTokens}</td>
      <td class="num">${run.estimatedCostUsd}</td>
      <td class="num">${escapeHtml(formatQualityScore(run.quality))}</td>
      <td class="num">${escapeHtml(formatJudgeScore(run.judge))}</td>
    </tr>`
  ))).join('\n');
  const aggregateRows = aggregate.map((row) => (
    `<tr>
      <td>${escapeHtml(row.group)}</td>
      <td class="num">${row.count}</td>
      <td class="num">${row.successCount}</td>
      <td class="num">${row.avgTotalMs}</td>
      <td class="num">${row.avgFirstMs}</td>
      <td class="num">${row.totalCostUsd}</td>
      <td class="num">${row.totalInputTokens}</td>
      <td class="num">${row.totalOutputTokens}</td>
      <td class="num">${escapeHtml(row.avgQualityScore === null ? '-' : `${Math.round(row.avgQualityScore * 100)}%`)}</td>
    </tr>`
  )).join('\n');
  const detailSections = reports.map(renderHtmlCaseDetail).join('\n');
  const strategyGuide = renderStrategyGuide();
  const insightsSection = renderExperimentInsights(reports);
  const scoreSection = renderScoreboard(buildScoreboard(reports));

  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Buddy AI Eval Comparison</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #fff;
      --panel-2: #f9fafc;
      --text: #172033;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #1f6feb;
      --good: #067647;
      --warn: #b54708;
      --bad: #b42318;
      --code: #111827;
      --single: #175cd3;
      --parallel: #027a48;
      --mixed: #9e77ed;
      --openai: #0f766e;
      --claude: #7f56d9;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); line-height: 1.48; }
    header { padding: 28px 32px 16px; border-bottom: 1px solid var(--line); background: rgba(255,255,255,.86); position: sticky; top: 0; z-index: 10; backdrop-filter: blur(12px); }
    h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }
    h2 { margin: 28px 0 12px; font-size: 21px; letter-spacing: 0; }
    h3 { margin: 20px 0 10px; font-size: 17px; letter-spacing: 0; }
    p { color: var(--muted); margin: 0; }
    main { padding: 0 32px 48px; max-width: 1480px; margin: 0 auto; }
    .nav { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
    .nav a { display: inline-flex; padding: 7px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); text-decoration: none; font-size: 13px; }
    .hero-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 20px 0 8px; }
    .metric { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    .metric span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .metric strong { display: block; overflow-wrap: anywhere; font-size: 18px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin: 18px 0 24px; }
    .case-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }
    .case-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
    .case-head h2 { margin: 0; font-size: 18px; }
    .case-head span { color: var(--accent); font-weight: 700; }
    .section-note { color: var(--muted); margin: -4px 0 14px; max-width: 960px; }
    .explain-box { background: #f8fbff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 14px; margin: 12px 0 18px; }
    .explain-box strong { display: block; margin-bottom: 6px; }
    .explain-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
    .explain-list li { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; color: var(--text); }
    .explain-list span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    .filter-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; margin: 18px 0 20px; }
    .filter-grid { display: grid; grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(140px, 1fr)); gap: 10px; align-items: end; }
    .filter-field label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }
    .filter-field input, .filter-field select { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--text); padding: 9px 10px; font: inherit; font-size: 13px; }
    .filter-actions { display: flex; gap: 8px; align-items: center; }
    .filter-actions button { border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--text); padding: 9px 10px; font: inherit; font-size: 13px; cursor: pointer; }
    .filter-count { color: var(--muted); font-size: 12px; margin-top: 8px; }
    .guide-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 18px 0 24px; }
    .guide-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    .guide-card h3 { margin: 0 0 8px; font-size: 16px; }
    .guide-card p { margin: 0 0 10px; }
    .tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; font-size: 12px; font-weight: 700; border: 1px solid transparent; }
    .tag-single { color: var(--single); background: #eff6ff; border-color: #bfdbfe; }
    .tag-parallel { color: var(--parallel); background: #ecfdf3; border-color: #abefc6; }
    .tag-mixed { color: var(--mixed); background: #f4f3ff; border-color: #d9d6fe; }
    .tag-openai { color: var(--openai); background: #f0fdfa; border-color: #99f6e4; }
    .tag-claude { color: var(--claude); background: #f4f3ff; border-color: #d9d6fe; }
    dl { display: grid; gap: 8px; margin: 0 0 12px; }
    dl div { display: grid; grid-template-columns: 92px 1fr; gap: 8px; }
    dt { color: var(--muted); }
    dd { margin: 0; overflow-wrap: anywhere; }
    ul { margin: 0; padding-left: 18px; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { background: #eef2f7; color: #344054; font-size: 13px; }
    td { font-size: 13px; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .score-strong { font-weight: 800; color: var(--accent); }
    .table-wrap { overflow-x: auto; border-radius: 8px; }
    .case-detail { margin-top: 28px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
    .case-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 14px 0; }
    .case-meta div { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    .case-meta span { display: block; color: var(--muted); font-size: 12px; }
    .case-meta strong { display: block; overflow-wrap: anywhere; }
    .request-preview { display: grid; grid-template-columns: minmax(260px, 420px) 1fr; gap: 16px; margin: 14px 0 20px; align-items: start; }
    .image-preview { border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); padding: 10px; }
    .image-preview img { display: block; width: 100%; height: auto; border-radius: 6px; border: 1px solid var(--line); background: #fff; }
    .image-preview figcaption { margin-top: 8px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .provider-images { display: grid; gap: 6px; margin-top: 8px; }
    .provider-images a { display: block; font-size: 12px; overflow-wrap: anywhere; }
    .input-preview { display: grid; gap: 10px; }
    .input-card { border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); padding: 10px; }
    .input-card h4 { margin: 0 0 6px; font-size: 14px; }
    .input-card pre { background: #fff; color: var(--text); border: 1px solid var(--line); }
    .structure { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 12px 0 18px; }
    .structure-card { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .structure-card h4 { margin: 0 0 8px; font-size: 14px; }
    .pill-list { display: flex; flex-wrap: wrap; gap: 6px; padding: 0; list-style: none; }
    .pill-list li { border: 1px solid var(--line); background: var(--panel); border-radius: 999px; padding: 5px 8px; font-size: 12px; color: var(--text); }
    .finding-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; padding: 0; margin: 12px 0 18px; list-style: none; }
    .finding-list li { border: 1px solid var(--line); background: var(--panel-2); border-radius: 8px; padding: 10px; color: var(--text); }
    .finding-list strong { display: block; margin-bottom: 4px; }
    .finding-list span { display: block; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .run-grid { display: grid; gap: 14px; }
    .comparison-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 12px 0 18px; }
    .comparison-card { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .comparison-card h4 { margin: 0 0 8px; font-size: 14px; }
    .comparison-card p { margin: 0 0 10px; }
    .delta-good { color: var(--good); font-weight: 700; }
    .delta-bad { color: var(--bad); font-weight: 700; }
    .run-card { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--panel); }
    .run-head { display: flex; gap: 12px; justify-content: space-between; align-items: flex-start; padding: 12px 14px; background: #eef2f7; }
    .run-head strong { overflow-wrap: anywhere; }
    .status { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; font-size: 12px; font-weight: 700; }
    .status-success { color: var(--good); background: #ecfdf3; }
    .status-partial_success { color: var(--warn); background: #fffaeb; }
    .status-failed { color: var(--bad); background: #fef3f2; }
    .run-body { padding: 14px; display: grid; gap: 12px; }
    .mini-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
    .mini-metrics div { border: 1px solid var(--line); border-radius: 8px; padding: 9px; background: var(--panel-2); }
    .mini-metrics span { display: block; color: var(--muted); font-size: 12px; }
    .mini-metrics strong { font-variant-numeric: tabular-nums; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--code); color: #f9fafb; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.5; }
    details { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: var(--panel-2); }
    summary { cursor: pointer; font-weight: 700; }
    .rubric { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin-top: 10px; }
    .rubric div { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    .rubric strong { display: block; margin-bottom: 4px; }
    a { color: var(--accent); }
    @media (max-width: 720px) {
      header { position: static; padding: 20px 18px 12px; }
      main { padding: 0 18px 32px; }
      .run-head { display: grid; }
      .request-preview { grid-template-columns: 1fr; }
      .filter-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Buddy AI Eval Comparison</h1>
    <p>Generated at ${escapeHtml(generatedAt)}. 케이스별 단일 요청, 병렬 요청, 모델/provider 조합 비교 리포트입니다.</p>
    <nav class="nav">${nav}<a href="#insights">Insights</a><a href="#aggregate">Aggregate</a><a href="#run-details">Run Details</a><a href="#scoreboard">Scoreboard</a></nav>
  </header>
  <main>
    <section class="explain-box">
      <strong>이 페이지에서 확인하려는 것</strong>
      <ul class="explain-list">
        <li><span>1. 호출 방식</span>단일 요청, 병렬 요청, OpenAI/Claude 분업 요청이 각각 어떻게 실행됐는지 봅니다.</li>
        <li><span>2. 속도</span>최종 응답 시간과 첫 결과 시간을 분리해서 봅니다.</li>
        <li><span>3. 비용</span>토큰 사용량과 추정 비용을 비교합니다.</li>
        <li><span>4. 품질</span>응답 전문을 보고 정확도, 근거성, 과장 여부를 사람이 판단합니다.</li>
      </ul>
    </section>
    ${renderTableFilters()}
    <section class="hero-metrics" aria-label="Overall metrics">
      <div class="metric"><span>Fastest final response</span><strong>${escapeHtml(fastest ? `${fastest.report.case.id} / ${fastest.run.label} (${fastest.run.latencyTotalMs}ms)` : '-')}</strong></div>
      <div class="metric"><span>Fastest first result</span><strong>${escapeHtml(fastestFirst ? `${fastestFirst.report.case.id} / ${fastestFirst.run.label} (${fastestFirst.run.latencyFirstResultMs}ms)` : '-')}</strong></div>
      <div class="metric"><span>Lowest cost run</span><strong>${escapeHtml(cheapest ? `${cheapest.report.case.id} / ${cheapest.run.label} ($${formatUsd(cheapest.run.estimatedCostUsd)})` : '-')}</strong></div>
      <div class="metric"><span>Best finding score</span><strong>${escapeHtml(bestQuality ? `${bestQuality.report.case.id} / ${bestQuality.run.label} (${formatQualityScore(bestQuality.run.quality)})` : '-')}</strong></div>
      <div class="metric"><span>Best judge score</span><strong>${escapeHtml(bestJudge ? `${bestJudge.report.case.id} / ${bestJudge.run.label} (${formatJudgeScore(bestJudge.run.judge)})` : '-')}</strong></div>
      <div class="metric"><span>Total measured usage</span><strong>$${formatUsd(totalCost)} · ${totalInput}/${totalOutput} tokens</strong></div>
    </section>
    ${strategyGuide}
    ${insightsSection}
    <h2>Case Summary: 액션별 결론</h2>
    <p class="section-note">각 카드 하나가 하나의 사용자 액션입니다. 같은 입력을 여러 호출 방식으로 실행한 뒤, 어느 방식이 빠르고 저렴했는지 요약합니다.</p>
    <div class="grid">${cards}</div>
    <h2 id="aggregate">Aggregate Metrics: 전략/모델 묶음 비교</h2>
    <p class="section-note">여기는 개별 답변 내용이 아니라 전체 실행을 전략, provider, 모델 단위로 묶어 평균을 보는 영역입니다. 병렬 전략은 첫 결과가 빠를 수 있지만 merge 호출 때문에 최종 응답은 늦어질 수 있습니다.</p>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Group</th>
          <th>Runs</th>
          <th>Success</th>
          <th>Avg total ms</th>
          <th>Avg first ms</th>
          <th>Total cost USD</th>
          <th>Input tokens</th>
          <th>Output tokens</th>
          <th>Avg quality</th>
        </tr>
      </thead>
      <tbody>${aggregateRows}</tbody>
    </table></div>
    <h2 id="run-details">Run Details: 모든 실행 조합의 숫자</h2>
    <p class="section-note">각 행은 하나의 실행 결과입니다. 여기서는 답변 내용보다 status, 최종 지연시간, 첫 결과 시간, 토큰, 비용을 빠르게 비교합니다.</p>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Case</th>
          <th>Action</th>
          <th>Run</th>
          <th>Status</th>
          <th>Total ms</th>
          <th>First ms</th>
          <th>Input</th>
          <th>Output</th>
          <th>Cost</th>
          <th>Quality</th>
          <th>Judge</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table></div>
    <h2>Case Deep Dive: 케이스별 호출 구조와 응답 전문</h2>
    <p class="section-note">여기부터는 각 액션을 실제로 어떻게 쪼개 호출했는지, 그리고 각 호출 방식이 어떤 답변을 냈는지 확인하는 상세 영역입니다.</p>
    ${detailSections}
    ${scoreSection}
  </main>
  ${renderTableFilterScript()}
</body>
</html>
`;
}

function renderStrategyGuide() {
  return `<section>
    <h2>Call Strategy Guide: 호출 방식 설명</h2>
    <p class="section-note">아래 세 카드가 이 실험의 핵심 비교군입니다. 같은 액션을 처리하지만 AI에게 일을 맡기는 방식이 다릅니다.</p>
    <div class="guide-grid">
      <div class="guide-card">
        <h3><span class="tag tag-single">Single</span> 단일 요청</h3>
        <p>선택된 액션을 모델 1회 호출로 처리합니다. 전체 완료 시간과 비용의 기준선입니다.</p>
        <div class="tag-row"><span class="tag tag-openai">OpenAI</span><span class="tag tag-claude">Claude</span></div>
      </div>
      <div class="guide-card">
        <h3><span class="tag tag-parallel">Parallel</span> 병렬 요청</h3>
        <p>액션 내부 작업을 여러 subtask로 동시에 호출하고 마지막에 merge합니다. 첫 결과는 빠를 수 있지만 총 호출 수와 비용이 늘어납니다.</p>
        <div class="tag-row"><span class="tag">subtasks</span><span class="tag">merge</span><span class="tag">first result</span></div>
      </div>
      <div class="guide-card">
        <h3><span class="tag tag-mixed">Mixed</span> 모델 분업</h3>
        <p>텍스트/구조화는 OpenAI, 시각 맥락과 merge는 Claude에 맡기는 전략입니다. 품질 보강 가능성과 지연시간 비용을 함께 봅니다.</p>
        <div class="tag-row"><span class="tag tag-openai">OpenAI text</span><span class="tag tag-claude">Claude vision/merge</span></div>
      </div>
    </div>
  </section>`;
}

function renderTableFilters() {
  return `<section class="filter-panel" aria-label="Table filters">
    <h2>Table Filters</h2>
    <p class="section-note">아래 필터는 이 페이지의 모든 표에 적용됩니다. 모델명, 케이스명, 포맷, 점수, 비용 등을 바로 좁혀 볼 수 있습니다.</p>
    <div class="filter-grid">
      <div class="filter-field">
        <label for="table-search">Search</label>
        <input id="table-search" type="search" placeholder="예: webp, low-fidelity, gpt-5.4-mini, 99/100" />
      </div>
      <div class="filter-field">
        <label for="provider-filter">Provider</label>
        <select id="provider-filter">
          <option value="">All</option>
          <option value="openai">OpenAI</option>
          <option value="claude">Claude</option>
        </select>
      </div>
      <div class="filter-field">
        <label for="action-filter">Action</label>
        <select id="action-filter">
          <option value="">All</option>
          <option value="ask">ask</option>
          <option value="describe">describe</option>
          <option value="translate">translate</option>
        </select>
      </div>
      <div class="filter-field">
        <label for="status-filter">Status</label>
        <select id="status-filter">
          <option value="">All</option>
          <option value="success">success</option>
          <option value="partial_success">partial_success</option>
          <option value="failed">failed</option>
        </select>
      </div>
      <div class="filter-actions">
        <button type="button" id="reset-filters">Reset</button>
      </div>
    </div>
    <div class="filter-count" id="filter-count">Filters are ready.</div>
  </section>`;
}

function renderTableFilterScript() {
  return `<script>
(() => {
  const search = document.getElementById('table-search');
  const provider = document.getElementById('provider-filter');
  const action = document.getElementById('action-filter');
  const status = document.getElementById('status-filter');
  const reset = document.getElementById('reset-filters');
  const count = document.getElementById('filter-count');
  const rows = Array.from(document.querySelectorAll('table tbody tr'));

  function normalize(value) {
    return String(value || '').toLowerCase();
  }

  function matches(row, needle) {
    return !needle || normalize(row.textContent).includes(needle);
  }

  function applyFilters() {
    const text = normalize(search.value).trim();
    const providerValue = normalize(provider.value);
    const actionValue = normalize(action.value);
    const statusValue = normalize(status.value);
    let visible = 0;

    for (const row of rows) {
      const rowText = normalize(row.textContent);
      const show = matches(row, text)
        && (!providerValue || rowText.includes(providerValue))
        && (!actionValue || rowText.includes(actionValue))
        && (!statusValue || rowText.includes(statusValue));
      row.hidden = !show;
      if (show) visible += 1;
    }

    if (count) {
      count.textContent = visible + ' / ' + rows.length + ' table rows visible';
    }
  }

  for (const element of [search, provider, action, status]) {
    element?.addEventListener('input', applyFilters);
    element?.addEventListener('change', applyFilters);
  }
  reset?.addEventListener('click', () => {
    search.value = '';
    provider.value = '';
    action.value = '';
    status.value = '';
    applyFilters();
  });
  applyFilters();
})();
</script>`;
}

function renderExperimentInsights(reports) {
  const lowFidelity = renderLowFidelityInsight(reports);
  const format = renderFormatInsight(reports);
  if (!lowFidelity && !format) {
    return '';
  }

  return `<section id="insights">
    <h2>Experiment Insights: 결과 해석 요약</h2>
    <p class="section-note">아래 표는 상세 run을 다시 읽지 않아도 실험 결론을 바로 볼 수 있도록, 결과 JSON의 latency/cost/finding/judge 데이터를 묶어 요약한 영역입니다.</p>
    ${lowFidelity}
    ${format}
  </section>`;
}

function renderLowFidelityInsight(reports) {
  const byId = new Map(reports.map((report) => [report.case.id, report]));
  const actions = ['ask', 'describe', 'translate'];
  const rows = [];

  for (const action of actions) {
    const high = byId.get(`kbs-wealth-${action}`);
    const low = byId.get(`kbs-wealth-${action}-low-fidelity`);
    if (!high || !low) {
      continue;
    }
    for (const highRun of high.runs) {
      const lowRun = low.runs.find((run) => run.label === highRun.label);
      if (!lowRun) {
        continue;
      }
      rows.push({ action, highRun, lowRun });
    }
  }

  if (rows.length === 0) {
    return '';
  }

  const htmlRows = rows.map(({ action, highRun, lowRun }) => {
    const judgeDelta = deltaNumber(lowRun.judge?.overallScore, highRun.judge?.overallScore);
    const findingDelta = deltaNumber(lowRun.quality?.matchedCount, highRun.quality?.matchedCount);
    const latencyDelta = deltaNumber(lowRun.latencyTotalMs, highRun.latencyTotalMs);
    const costDelta = deltaNumber(lowRun.estimatedCostUsd, highRun.estimatedCostUsd);
    return `<tr>
      <td>${escapeHtml(action)}</td>
      <td>${escapeHtml(providerModelLabel(highRun.provider, highRun.openaiModel || highRun.claudeModel || 'mixed'))}</td>
      <td class="num">${escapeHtml(formatJudgeScore(highRun.judge))} → ${escapeHtml(formatJudgeScore(lowRun.judge))}</td>
      <td class="num ${deltaClass(judgeDelta, false)}">${formatSigned(judgeDelta)}</td>
      <td class="num">${escapeHtml(formatQualityScore(highRun.quality))} → ${escapeHtml(formatQualityScore(lowRun.quality))}</td>
      <td class="num ${deltaClass(findingDelta, false)}">${formatSigned(findingDelta)}</td>
      <td class="num">${highRun.latencyTotalMs} → ${lowRun.latencyTotalMs}</td>
      <td class="num ${deltaClass(latencyDelta, true)}">${formatSigned(latencyDelta)}ms</td>
      <td class="num">$${formatUsd(highRun.estimatedCostUsd)} → $${formatUsd(lowRun.estimatedCostUsd)}</td>
      <td class="num ${deltaClass(costDelta, true)}">${formatSigned(costDelta, 6)}</td>
    </tr>`;
  }).join('');

  return `<h3>Low Fidelity Impact: OpenAI low detail / Claude compressed image</h3>
    <p class="section-note">High fidelity 결과와 low fidelity 결과를 같은 action/model끼리 비교합니다. OpenAI는 detail=low, Claude는 193×512 JPEG 저화질 이미지를 사용했습니다.</p>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Action</th>
          <th>Model</th>
          <th>Judge</th>
          <th>Judge Δ</th>
          <th>Findings</th>
          <th>Findings Δ</th>
          <th>Latency ms</th>
          <th>Latency Δ</th>
          <th>Cost</th>
          <th>Cost Δ</th>
        </tr>
      </thead>
      <tbody>${htmlRows}</tbody>
    </table></div>`;
}

function renderFormatInsight(reports) {
  const formatReports = reports
    .filter((report) => report.case.id.startsWith('kbs-wealth-format-'))
    .sort((a, b) => a.metadata.imageBytes - b.metadata.imageBytes);
  if (formatReports.length === 0) {
    return '';
  }

  const rows = [];
  for (const report of formatReports) {
    for (const run of report.runs) {
      rows.push({ report, run });
    }
  }

  const htmlRows = rows.map(({ report, run }) => (
    `<tr>
      <td>${escapeHtml(formatName(report))}</td>
      <td>${escapeHtml(report.metadata.imageMediaType || '')}</td>
      <td class="num">${report.metadata.imageBytes}</td>
      <td>${escapeHtml(providerModelLabel(run.provider, run.openaiModel || run.claudeModel || 'mixed'))}</td>
      <td class="num">${escapeHtml(formatJudgeScore(run.judge))}</td>
      <td class="num">${escapeHtml(formatQualityScore(run.quality))}</td>
      <td class="num">${run.latencyTotalMs}</td>
      <td class="num">$${formatUsd(run.estimatedCostUsd)}</td>
      <td class="num">${run.usage?.inputTokens || 0} / ${run.usage?.outputTokens || 0}</td>
    </tr>`
  )).join('');

  const smallest = formatReports[0];
  const largest = maxBy(formatReports, (report) => report.metadata.imageBytes);
  const savingPercent = largest && smallest
    ? Math.round((1 - smallest.metadata.imageBytes / largest.metadata.imageBytes) * 100)
    : 0;

  return `<h3>Image Format Impact: PNG vs JPEG vs WebP</h3>
    <p class="section-note">같은 해상도의 이미지 포맷만 바꿔 전송량, latency, judge 품질을 비교합니다. 가장 작은 파일은 ${escapeHtml(formatName(smallest))}이고, 가장 큰 파일 대비 약 ${savingPercent}% 작습니다.</p>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Format</th>
          <th>Media type</th>
          <th>Bytes</th>
          <th>Model</th>
          <th>Judge</th>
          <th>Findings</th>
          <th>Latency ms</th>
          <th>Cost</th>
          <th>Tokens</th>
        </tr>
      </thead>
      <tbody>${htmlRows}</tbody>
    </table></div>`;
}

function formatName(report) {
  return report.case.id
    .replace('kbs-wealth-format-', '')
    .replace('jpeg-q70', 'JPEG q70')
    .replace('webp-q70', 'WebP q70')
    .replace('png', 'PNG');
}

function buildScoreboard(reports) {
  const runs = reports.flatMap((report) => report.runs.map((run) => {
    const model = run.openaiModel || run.claudeModel || 'mixed';
    const totalTokens = (run.usage?.inputTokens || 0) + (run.usage?.outputTokens || 0);
    return {
      caseId: report.case.id,
      action: report.case.action,
      runLabel: run.label,
      strategy: run.strategy,
      provider: run.provider,
      model,
      status: run.status,
      latencyTotalMs: run.latencyTotalMs || 0,
      latencyFirstResultMs: run.latencyFirstResultMs || run.latencyTotalMs || 0,
      estimatedCostUsd: run.estimatedCostUsd || 0,
      totalTokens,
      findingRaw: run.quality?.score ?? null,
      findingLabel: formatQualityScore(run.quality),
      judgeScore: Number.isFinite(run.judge?.overallScore) ? run.judge.overallScore : null,
      qualityRaw: Number.isFinite(run.judge?.overallScore) ? run.judge.overallScore / 100 : run.quality?.score ?? null,
      qualityLabel: Number.isFinite(run.judge?.overallScore) ? formatJudgeScore(run.judge) : formatQualityScore(run.quality),
    };
  }));
  const successful = runs.filter((run) => run.status !== 'failed');
  const minTotalMs = minPositive(successful.map((run) => run.latencyTotalMs));
  const minFirstMs = minPositive(successful.map((run) => run.latencyFirstResultMs));
  const minCost = minPositive(successful.map((run) => run.estimatedCostUsd));
  const minTokens = minPositive(successful.map((run) => run.totalTokens));

  const runRows = runs.map((run) => {
    const qualityScore = run.qualityRaw === null ? 0 : Math.round(run.qualityRaw * 100);
    const latencyScore = scoreLowerIsBetter(run.latencyTotalMs, minTotalMs);
    const firstScore = scoreLowerIsBetter(run.latencyFirstResultMs, minFirstMs);
    const costScore = scoreLowerIsBetter(run.estimatedCostUsd, minCost);
    const tokenScore = scoreLowerIsBetter(run.totalTokens, minTokens);
    const totalScore = Math.round(
      qualityScore * 0.4
      + latencyScore * 0.25
      + firstScore * 0.1
      + costScore * 0.2
      + tokenScore * 0.05,
    );

    return {
      ...run,
      qualityScore,
      latencyScore,
      firstScore,
      costScore,
      tokenScore,
      totalScore,
    };
  }).sort((a, b) => b.totalScore - a.totalScore);

  const modelGroups = new Map();
  for (const row of runRows) {
    const key = `${row.provider}:${row.model}`;
    const group = modelGroups.get(key) || {
      provider: row.provider,
      model: row.model,
      count: 0,
      qualityScore: 0,
      latencyScore: 0,
      firstScore: 0,
      costScore: 0,
      tokenScore: 0,
      totalScore: 0,
      avgLatencyTotalMs: 0,
      avgCostUsd: 0,
    };
    group.count += 1;
    group.qualityScore += row.qualityScore;
    group.latencyScore += row.latencyScore;
    group.firstScore += row.firstScore;
    group.costScore += row.costScore;
    group.tokenScore += row.tokenScore;
    group.totalScore += row.totalScore;
    group.avgLatencyTotalMs += row.latencyTotalMs;
    group.avgCostUsd += row.estimatedCostUsd;
    modelGroups.set(key, group);
  }

  const modelRows = [...modelGroups.values()].map((group) => ({
    ...group,
    qualityScore: Math.round(group.qualityScore / group.count),
    latencyScore: Math.round(group.latencyScore / group.count),
    firstScore: Math.round(group.firstScore / group.count),
    costScore: Math.round(group.costScore / group.count),
    tokenScore: Math.round(group.tokenScore / group.count),
    totalScore: Math.round(group.totalScore / group.count),
    avgLatencyTotalMs: Math.round(group.avgLatencyTotalMs / group.count),
    avgCostUsd: Number((group.avgCostUsd / group.count).toFixed(6)),
  })).sort((a, b) => b.totalScore - a.totalScore);

  return { modelRows, runRows };
}

function renderScoreboard(scoreboard) {
  const modelRows = scoreboard.modelRows.map((row, index) => (
    `<tr>
      <td class="num">${index + 1}</td>
      <td>${escapeHtml(providerModelLabel(row.provider, row.model))}</td>
      <td class="num">${row.count}</td>
      <td class="num score-strong">${row.totalScore}</td>
      <td class="num">${row.qualityScore}</td>
      <td class="num">${row.latencyScore}</td>
      <td class="num">${row.firstScore}</td>
      <td class="num">${row.costScore}</td>
      <td class="num">${row.tokenScore}</td>
      <td class="num">${row.avgLatencyTotalMs}</td>
      <td class="num">${formatUsd(row.avgCostUsd)}</td>
    </tr>`
  )).join('');

  const runRows = scoreboard.runRows.map((row, index) => (
    `<tr>
      <td class="num">${index + 1}</td>
      <td>${escapeHtml(row.caseId)}</td>
      <td>${escapeHtml(row.action)}</td>
      <td>${escapeHtml(providerModelLabel(row.provider, row.model))}</td>
      <td>${escapeHtml(row.strategy)}</td>
      <td class="num score-strong">${row.totalScore}</td>
      <td class="num">${row.qualityScore}</td>
      <td class="num">${row.latencyScore}</td>
      <td class="num">${row.firstScore}</td>
      <td class="num">${row.costScore}</td>
      <td class="num">${row.tokenScore}</td>
      <td class="num">${row.latencyTotalMs}</td>
      <td class="num">${formatUsd(row.estimatedCostUsd)}</td>
      <td class="num">${escapeHtml(row.qualityLabel)}</td>
      <td class="num">${escapeHtml(row.findingLabel)}</td>
    </tr>`
  )).join('');

  return `<section id="scoreboard">
    <h2>Overall Scoreboard: 항목별 점수 비교</h2>
    <p class="section-note">아래 점수는 현재 리포트에 포함된 run끼리 상대 비교한 0~100점입니다. Quality는 judge 결과가 있으면 gpt-5.4 judge score를 우선 사용하고, 없으면 finding score를 사용합니다. 종합점수는 Quality 40%, Final latency 25%, First result 10%, Cost 20%, Tokens 5% 가중치로 계산했습니다.</p>
    <h3>Model Average Score: 모델별 평균</h3>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Model</th>
          <th>Runs</th>
          <th>Total</th>
          <th>Quality</th>
          <th>Final latency</th>
          <th>First result</th>
          <th>Cost</th>
          <th>Tokens</th>
          <th>Avg ms</th>
          <th>Avg cost</th>
        </tr>
      </thead>
      <tbody>${modelRows}</tbody>
    </table></div>
    <h3>Run Score: 케이스별 실행 점수</h3>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Case</th>
          <th>Action</th>
          <th>Model</th>
          <th>Strategy</th>
          <th>Total</th>
          <th>Quality</th>
          <th>Final latency</th>
          <th>First result</th>
          <th>Cost</th>
          <th>Tokens</th>
          <th>Raw ms</th>
          <th>Raw cost</th>
          <th>Quality source</th>
          <th>Findings</th>
        </tr>
      </thead>
      <tbody>${runRows}</tbody>
    </table></div>
  </section>`;
}

function renderHtmlCaseDetail(report) {
  const id = `case-${sanitizeFileName(report.case.id)}`;
  const notes = report.analysis.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('');
  const runs = [...report.runs]
    .sort((a, b) => strategySortOrder(a.strategy) - strategySortOrder(b.strategy))
    .map(renderHtmlRunCard)
    .join('\n');
  return `<section class="case-detail" id="${escapeAttribute(id)}">
    <h2>${escapeHtml(caseTitle(report.case))} ${renderActionTag(report.case.action)}</h2>
    <p class="section-note">${escapeHtml(casePurpose(report.case))}</p>
    <div class="case-meta">
      <div><span>Started</span><strong>${escapeHtml(report.metadata.startedAt)}</strong></div>
      <div><span>Finished</span><strong>${escapeHtml(report.metadata.finishedAt)}</strong></div>
      <div><span>Image bytes</span><strong>${escapeHtml(report.metadata.imageBytes)}</strong></div>
      <div><span>Input mode</span><strong>${escapeHtml(report.metadata.inputMode || 'ocr-image')}</strong></div>
      <div><span>OpenAI image detail</span><strong>${escapeHtml(report.metadata.openaiImageDetail || 'auto')}</strong></div>
      <div><span>Image text policy</span><strong>${escapeHtml(report.metadata.imageTextPolicy || '-')}</strong></div>
      <div><span>Markdown</span><strong><a href="${escapeAttribute(report.artifacts?.mdRelativePath || '#')}">open case report</a></strong></div>
    </div>
    <h3>Requested Image & Inputs: 이 케이스에 실제로 보낸 내용</h3>
    <p class="section-note">아래 이미지와 OCR 텍스트가 AI 요청에 함께 들어갔습니다. ask 케이스는 사용자 질문도 같이 포함됩니다.</p>
    ${renderRequestPreview(report)}
    <h3>Request Structure: 이 액션을 AI 작업으로 쪼갠 방식</h3>
    <p class="section-note">Single은 한 번에 처리하고, Parallel/Mixed는 아래 subtask 단위로 나눠 호출한 뒤 merge합니다.</p>
    ${renderRequestStructure(report.metadata.requestStructure)}
    <h3>Expected Findings: 이미지 리딩 자동 체크 포인트</h3>
    <p class="section-note">아래 항목은 모델이 이미지나 OCR에서 반드시 읽어내면 좋은 핵심 정보입니다. Run별 finding score는 이 항목이 응답에 포함됐는지로 계산합니다.</p>
    ${renderExpectedFindings(report.case.expectedFindings)}
    <h3>Single vs Parallel Comparison: 단일 호출과 병렬 호출의 실제 차이</h3>
    <p class="section-note">병렬이 최종 응답을 더 빠르게 만드는지, 아니면 첫 결과만 빨라지는지 확인하는 영역입니다.</p>
    ${renderStrategyComparison(report)}
    <h3>Analysis: 이 케이스의 자동 해석</h3>
    <ul>${notes}</ul>
    ${renderJudgeCaseSummary(report)}
    <h3>Quality Rubric: 답변 품질을 볼 때의 기준</h3>
    <div class="rubric">
      <div><strong>Accuracy</strong><span>OCR 텍스트와 이미지 정보만으로 맞는 답을 했는가</span></div>
      <div><strong>Grounding</strong><span>근거를 텍스트/시각 정보로 명확히 설명했는가</span></div>
      <div><strong>Concision</strong><span>Buddy 말풍선/상세 패널에 넣기 적절한 길이인가</span></div>
      <div><strong>Usefulness</strong><span>사용자가 다음 행동을 바로 이해할 수 있는가</span></div>
      <div><strong>Overclaiming</strong><span>화면에 없는 내용을 단정하지 않았는가</span></div>
    </div>
    <h3>Run Outputs: 호출 방식별 실제 응답 전문</h3>
    <p class="section-note">여기서는 숫자가 아니라 결과 품질을 봅니다. 같은 질문에 대해 어떤 방식이 더 정확하고 사용하기 좋은 답을 냈는지 비교합니다.</p>
    <div class="run-grid">${runs}</div>
  </section>`;
}

function renderRequestPreview(report) {
  const imageSrc = imagePathToFileUrl(report.metadata.imagePath);
  const providerImages = renderProviderImagePreview(report.metadata.providerImages);
  const requestPolicy = `<div class="input-card"><h4>Request Policy</h4><pre>${escapeHtml([
    `inputMode: ${report.metadata.inputMode || 'ocr-image'}`,
    `imageSentToModel: ${report.metadata.requestStructure?.image?.sentToModel !== false}`,
    `openaiImageDetail: ${report.metadata.openaiImageDetail || 'auto'}`,
    `imageFidelity: ${report.metadata.imageFidelity || '-'}`,
    `imageTextPolicy: ${report.metadata.imageTextPolicy || '-'}`,
    `providerImageOverrides: ${Object.keys(report.metadata.providerImages || {}).filter((key) => key !== 'default').join(', ') || '-'}`,
  ].join('\n'))}</pre></div>`;
  const question = report.case.question
    ? `<div class="input-card"><h4>User Question</h4><pre>${escapeHtml(report.case.question)}</pre></div>`
    : '';
  const targetLanguage = report.case.targetLanguage
    ? `<div class="input-card"><h4>Target Language</h4><pre>${escapeHtml(report.case.targetLanguage)}</pre></div>`
    : '';

  return `<div class="request-preview">
    <figure class="image-preview">
      <img src="${escapeAttribute(imageSrc)}" alt="${escapeAttribute(report.case.id)} requested screenshot" />
      <figcaption>${escapeHtml(report.metadata.imagePath)} · ${escapeHtml(report.metadata.imageMediaType || '')} · ${escapeHtml(report.metadata.imageBytes)} bytes</figcaption>
      ${providerImages}
    </figure>
    <div class="input-preview">
      ${requestPolicy}
      ${question}
      ${targetLanguage}
      <div class="input-card"><h4>OCR Text</h4><pre>${escapeHtml(report.case.ocrText)}</pre></div>
    </div>
  </div>`;
}

function renderProviderImagePreview(providerImages = {}) {
  const overrides = Object.entries(providerImages).filter(([provider]) => provider !== 'default');
  if (overrides.length === 0) {
    return '';
  }
  return `<div class="provider-images">${overrides.map(([provider, image]) => (
    `<a href="${escapeAttribute(imagePathToFileUrl(image.path))}">${escapeHtml(provider)} override · ${escapeHtml(image.mediaType)} · ${escapeHtml(image.bytes)} bytes</a>`
  )).join('')}</div>`;
}

function renderExpectedFindings(expectedFindings) {
  if (!Array.isArray(expectedFindings) || expectedFindings.length === 0) {
    return '<p class="section-note">이 케이스에는 자동 체크 포인트가 없습니다. 응답 전문을 보고 수동 평가합니다.</p>';
  }

  const items = expectedFindings.map((finding) => {
    const label = typeof finding === 'string' ? finding : finding.label || finding.value || '';
    const candidates = typeof finding === 'string'
      ? [finding]
      : finding.anyOf || [finding.value || finding.label || ''];
    return `<li><strong>${escapeHtml(label)}</strong><span>${escapeHtml(candidates.join(' | '))}</span></li>`;
  }).join('');

  return `<ul class="finding-list">${items}</ul>`;
}

function renderRequestStructure(structure) {
  const input = (structure.input || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const single = (structure.single || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const parallel = (structure.parallel || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const mixed = (structure.mixedProvider || []).map((item) => (
    typeof item === 'string'
      ? `<li>${escapeHtml(item)}</li>`
      : `<li>${escapeHtml(item.task)} · ${escapeHtml(item.provider)}</li>`
  )).join('');
  const imagePolicy = [
    `mode: ${structure.inputMode || 'ocr-image'}`,
    `image sent: ${structure.image?.sentToModel !== false}`,
    `OpenAI detail: ${structure.image?.openaiDetail || 'auto'}`,
    structure.image?.fidelity ? `fidelity: ${structure.image.fidelity}` : '',
    structure.textPolicy ? `text policy: ${structure.textPolicy}` : '',
    `expected findings: ${structure.expectedFindings || 0}`,
  ].filter(Boolean).map((item) => `<li>${escapeHtml(item)}</li>`).join('');

  return `<div class="structure">
    <div class="structure-card"><h4>Input</h4><p>클라이언트가 서버로 보내는 공통 입력입니다.</p><ul class="pill-list">${input}</ul></div>
    <div class="structure-card"><h4>Image/OCR Policy</h4><p>모델 요청에 이미지와 OCR을 어떤 방식으로 넣었는지입니다.</p><ul class="pill-list">${imagePolicy}</ul></div>
    <div class="structure-card"><h4><span class="tag tag-single">Single</span></h4><p>모델 1회 호출로 전체 액션을 해결합니다.</p><ul class="pill-list">${single}</ul></div>
    <div class="structure-card"><h4><span class="tag tag-parallel">Parallel</span></h4><p>subtask를 동시에 호출하고 merge로 합칩니다.</p><ul class="pill-list">${parallel}</ul></div>
    <div class="structure-card"><h4><span class="tag tag-mixed">Mixed Provider</span></h4><p>작업 성격에 따라 OpenAI와 Claude를 나눠 호출합니다.</p><ul class="pill-list">${mixed}</ul></div>
  </div>`;
}

function renderHtmlRunCard(run) {
  const calls = (run.calls || []).map((call) => (
    `<li>${escapeHtml(call.taskName)} · ${escapeHtml(call.provider)}/${escapeHtml(call.model)} · ${call.latencyMs}ms · in ${call.usage?.inputTokens || 0} / out ${call.usage?.outputTokens || 0}</li>`
  )).join('') || '<li>없음</li>';
  const failures = (run.failedCalls || []).map((call) => (
    `<li>${escapeHtml(call.name)} · ${escapeHtml(call.message)}</li>`
  )).join('') || '<li>없음</li>';

  return `<article class="run-card">
    <div class="run-head">
      <div>
        <div class="tag-row">${renderStrategyTag(run.strategy)}${renderProviderTags(run)}</div>
        <strong>${escapeHtml(readableRunLabel(run.label))}</strong>
        <p class="section-note">${escapeHtml(run.label)}</p>
      </div>
      <span class="status status-${escapeAttribute(run.status)}">${escapeHtml(run.status)}</span>
    </div>
    <div class="run-body">
      <p class="section-note">${escapeHtml(strategyDescription(run))}</p>
      <div class="mini-metrics">
        <div><span>Total latency</span><strong>${run.latencyTotalMs}ms</strong></div>
        <div><span>First result</span><strong>${run.latencyFirstResultMs ?? '-'}ms</strong></div>
        <div><span>Tokens</span><strong>${run.usage.inputTokens} / ${run.usage.outputTokens}</strong></div>
        <div><span>Cost</span><strong>$${formatUsd(run.estimatedCostUsd)}</strong></div>
        <div><span>Finding score</span><strong>${escapeHtml(formatQualityScore(run.quality))}</strong></div>
        <div><span>Judge score</span><strong>${escapeHtml(formatJudgeScore(run.judge))}</strong></div>
      </div>
      ${renderRunQuality(run.quality)}
      ${renderRunJudge(run.judge)}
      <details>
        <summary>Calls</summary>
        <ul>${calls}</ul>
      </details>
      <details>
        <summary>Failures</summary>
        <ul>${failures}</ul>
      </details>
      <div>
        <h4>Output</h4>
        <pre>${escapeHtml(run.output || 'No output')}</pre>
      </div>
    </div>
  </article>`;
}

function renderRunQuality(quality) {
  if (!quality || quality.score === null || quality.score === undefined) {
    return '<p class="section-note">이 run에는 자동 finding score가 없습니다.</p>';
  }

  const matched = quality.matched.map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>없음</li>';
  const missing = quality.missing.map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>없음</li>';
  return `<details>
    <summary>Finding score details (${escapeHtml(formatQualityScore(quality))})</summary>
    <div class="comparison-grid">
      <div class="comparison-card"><h4>Matched</h4><ul>${matched}</ul></div>
      <div class="comparison-card"><h4>Missing</h4><ul>${missing}</ul></div>
    </div>
  </details>`;
}

function renderJudgeCaseSummary(report) {
  if (!report.judge) {
    return '';
  }

  const rows = (report.judge.evaluations || []).map((evaluation) => (
    `<tr>
      <td>${escapeHtml(readableRunLabel(evaluation.runLabel))}</td>
      <td class="num score-strong">${escapeHtml(formatJudgeScore(evaluation))}</td>
      <td class="num">${escapeHtml(evaluation.scores?.accuracy ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.completeness ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.grounding ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.hallucinationSafety ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.usefulness ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.conciseness ?? '-')}</td>
      <td class="num">${escapeHtml(evaluation.scores?.formatCompliance ?? '-')}</td>
    </tr>`
  )).join('');

  return `<h3>Judge Review: gpt-5.4 기반 품질 재검증</h3>
    <p class="section-note">${escapeHtml(report.judge.summary || 'Judge summary 없음')}</p>
    <div class="case-meta">
      <div><span>Judge</span><strong>${escapeHtml(report.judge.provider)}/${escapeHtml(report.judge.model)}</strong></div>
      <div><span>Winner</span><strong>${escapeHtml(readableRunLabel(report.judge.winner) || '-')}</strong></div>
      <div><span>Judge latency</span><strong>${escapeHtml(report.judge.latencyMs)}ms</strong></div>
      <div><span>Judge cost</span><strong>$${formatUsd(report.judge.estimatedCostUsd)}</strong></div>
    </div>
    <div class="table-wrap"><table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Overall</th>
          <th>Accuracy</th>
          <th>Completeness</th>
          <th>Grounding</th>
          <th>Safety</th>
          <th>Usefulness</th>
          <th>Concise</th>
          <th>Format</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function renderRunJudge(judge) {
  if (!judge) {
    return '<p class="section-note">이 run에는 judge 평가가 없습니다.</p>';
  }

  const strengths = (judge.strengths || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>없음</li>';
  const weaknesses = (judge.weaknesses || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>없음</li>';
  const scores = judge.scores || {};
  return `<details>
    <summary>Judge score details (${escapeHtml(formatJudgeScore(judge))})</summary>
    <div class="mini-metrics">
      <div><span>Accuracy</span><strong>${escapeHtml(scores.accuracy ?? '-')}</strong></div>
      <div><span>Completeness</span><strong>${escapeHtml(scores.completeness ?? '-')}</strong></div>
      <div><span>Grounding</span><strong>${escapeHtml(scores.grounding ?? '-')}</strong></div>
      <div><span>Hallucination safety</span><strong>${escapeHtml(scores.hallucinationSafety ?? '-')}</strong></div>
      <div><span>Usefulness</span><strong>${escapeHtml(scores.usefulness ?? '-')}</strong></div>
      <div><span>Conciseness</span><strong>${escapeHtml(scores.conciseness ?? '-')}</strong></div>
      <div><span>Format</span><strong>${escapeHtml(scores.formatCompliance ?? '-')}</strong></div>
    </div>
    <div class="comparison-grid">
      <div class="comparison-card"><h4>Strengths</h4><ul>${strengths}</ul></div>
      <div class="comparison-card"><h4>Weaknesses</h4><ul>${weaknesses}</ul></div>
    </div>
    <p class="section-note">${escapeHtml(judge.notes || '')}</p>
  </details>`;
}

function renderStrategyComparison(report) {
  const singleOpenAI = report.runs.find((run) => run.strategy === 'single' && run.provider === 'openai');
  const parallelOpenAI = report.runs.find((run) => run.strategy === 'parallel' && run.provider === 'openai');
  const singleClaude = report.runs.find((run) => run.strategy === 'single' && run.provider === 'claude');
  const parallelClaude = report.runs.find((run) => run.strategy === 'parallel' && run.provider === 'claude');
  const mixed = report.runs.find((run) => run.strategy === 'mixed-provider');

  return `<div class="comparison-grid">
    ${renderPairComparison('OpenAI 단일 vs 병렬', singleOpenAI, parallelOpenAI)}
    ${renderPairComparison('Claude 단일 vs 병렬', singleClaude, parallelClaude)}
    ${renderMixedComparison(singleOpenAI, mixed)}
  </div>`;
}

function renderPairComparison(title, singleRun, parallelRun) {
  if (!singleRun || !parallelRun) {
    return `<div class="comparison-card"><h4>${escapeHtml(title)}</h4><p>비교할 실행 데이터가 부족합니다.</p></div>`;
  }

  const totalDelta = parallelRun.latencyTotalMs - singleRun.latencyTotalMs;
  const firstDelta = parallelRun.latencyFirstResultMs - singleRun.latencyFirstResultMs;
  const costDelta = parallelRun.estimatedCostUsd - singleRun.estimatedCostUsd;
  return `<div class="comparison-card">
    <h4>${escapeHtml(title)}</h4>
    <p><strong>결론:</strong> ${escapeHtml(comparisonConclusion(singleRun, parallelRun, '병렬'))}</p>
    <p>병렬은 ${renderDelta(totalDelta, 'ms', true)} 최종 응답 차이, ${renderDelta(firstDelta, 'ms', true)} 첫 결과 차이를 보였습니다.</p>
    <p>비용 차이: ${renderDelta(costDelta, ' USD', true)}</p>
    <div class="tag-row">${renderStrategyTag('single')}${renderStrategyTag('parallel')}</div>
  </div>`;
}

function renderMixedComparison(singleRun, mixedRun) {
  if (!singleRun || !mixedRun) {
    return `<div class="comparison-card"><h4>OpenAI 단일 vs Mixed</h4><p>비교할 실행 데이터가 부족합니다.</p></div>`;
  }

  const totalDelta = mixedRun.latencyTotalMs - singleRun.latencyTotalMs;
  const firstDelta = mixedRun.latencyFirstResultMs - singleRun.latencyFirstResultMs;
  const costDelta = mixedRun.estimatedCostUsd - singleRun.estimatedCostUsd;
  return `<div class="comparison-card">
    <h4>OpenAI 단일 vs Mixed Provider</h4>
    <p><strong>결론:</strong> ${escapeHtml(comparisonConclusion(singleRun, mixedRun, 'Mixed'))}</p>
    <p>Mixed는 ${renderDelta(totalDelta, 'ms', true)} 최종 응답 차이, ${renderDelta(firstDelta, 'ms', true)} 첫 결과 차이를 보였습니다.</p>
    <p>비용 차이: ${renderDelta(costDelta, ' USD', true)}</p>
    <div class="tag-row">${renderStrategyTag('single')}${renderStrategyTag('mixed-provider')}</div>
  </div>`;
}

function comparisonConclusion(baselineRun, targetRun, targetName) {
  const totalBetter = targetRun.latencyTotalMs < baselineRun.latencyTotalMs;
  const firstBetter = (targetRun.latencyFirstResultMs ?? Infinity) < (baselineRun.latencyFirstResultMs ?? Infinity);
  const costBetter = targetRun.estimatedCostUsd < baselineRun.estimatedCostUsd;

  if (totalBetter && costBetter) {
    return `${targetName}이 최종 응답과 비용 모두 더 좋았습니다.`;
  }
  if (totalBetter) {
    return `${targetName}이 최종 응답은 더 빠르지만 비용은 확인이 필요합니다.`;
  }
  if (firstBetter) {
    return `${targetName}은 첫 결과를 더 빨리 보여주지만, 최종 응답/비용은 단일 요청이 유리합니다.`;
  }
  return `이 케이스에서는 단일 요청이 최종 응답과 비용 측면에서 유리합니다.`;
}

function renderDelta(value, unit, lowerIsBetter) {
  const rounded = unit.trim() === 'USD' ? formatUsd(Math.abs(value)) : Math.abs(Math.round(value));
  const isBetter = lowerIsBetter ? value < 0 : value > 0;
  const className = isBetter ? 'delta-good' : 'delta-bad';
  const direction = value < 0 ? '빠름/저렴' : value > 0 ? '느림/비쌈' : '동일';
  return `<span class="${className}">${value < 0 ? '-' : '+'}${rounded}${escapeHtml(unit)} (${direction})</span>`;
}

function renderActionTag(action) {
  return `<span class="tag">${escapeHtml(action)}</span>`;
}

function renderStrategyTag(strategy) {
  if (strategy === 'single') return '<span class="tag tag-single">Single</span>';
  if (strategy === 'parallel') return '<span class="tag tag-parallel">Parallel</span>';
  return '<span class="tag tag-mixed">Mixed</span>';
}

function renderProviderTags(run) {
  if (run.strategy === 'mixed-provider') {
    return '<span class="tag tag-openai">OpenAI subtasks</span><span class="tag tag-claude">Claude visual/merge</span>';
  }
  if (run.provider === 'openai') {
    return `<span class="tag tag-openai">OpenAI</span><span class="tag">${escapeHtml(run.openaiModel || '')}</span>`;
  }
  return `<span class="tag tag-claude">Claude</span><span class="tag">${escapeHtml(run.claudeModel || '')}</span>`;
}

function strategyDescription(run) {
  if (run.strategy === 'single') {
    return '모든 판단을 한 번의 모델 호출로 처리한 기준선입니다. 최종 완료 시간과 비용 비교의 기준으로 봅니다.';
  }
  if (run.strategy === 'parallel') {
    return '액션 내부 작업을 여러 subtask로 동시에 호출한 뒤 merge 호출로 최종 응답을 만든 결과입니다. 첫 결과 시간과 최종 완료 시간을 분리해서 봅니다.';
  }
  return '텍스트/구조화 subtask는 OpenAI, 시각 맥락과 최종 merge는 Claude로 나눠 호출한 결과입니다.';
}

function strategySortOrder(strategy) {
  if (strategy === 'single') return 0;
  if (strategy === 'parallel') return 1;
  return 2;
}

function caseTitle(testCase) {
  if (testCase.action === 'ask') return '이미지 질문 답변';
  if (testCase.action === 'describe') return '이미지 설명';
  if (testCase.action === 'translate') return 'OCR 번역';
  return testCase.id;
}

function casePurpose(testCase) {
  if (testCase.action === 'ask') {
    return '사용자가 스크린샷에 대해 질문했을 때, 이미지와 OCR 텍스트를 근거로 답변하는 액션입니다.';
  }
  if (testCase.action === 'describe') {
    return '스크린샷이 어떤 화면인지, 어떤 요소가 중요한지 설명하는 액션입니다.';
  }
  if (testCase.action === 'translate') {
    return 'OCR로 추출된 화면 텍스트를 목표 언어로 번역하고 이미지 맥락으로 보정하는 액션입니다.';
  }
  return '스크린샷 기반 AI 액션입니다.';
}

function readableRunLabel(label) {
  if (!label) return '';
  if (label.startsWith('single:openai:')) {
    return `Single / OpenAI / ${label.replace('single:openai:', '')}`;
  }
  if (label.startsWith('single:claude:')) {
    return `Single / Claude / ${label.replace('single:claude:', '')}`;
  }
  if (label.startsWith('parallel:openai:')) {
    return `Parallel / OpenAI / ${label.replace('parallel:openai:', '')}`;
  }
  if (label.startsWith('parallel:claude:')) {
    return `Parallel / Claude / ${label.replace('parallel:claude:', '')}`;
  }
  if (label.startsWith('mixed-provider:')) {
    return label
      .replace('mixed-provider:', 'Mixed / ')
      .replace('openai=', 'OpenAI ')
      .replace(':claude=', ' + Claude ');
  }
  return label;
}

function providerModelLabel(provider, model) {
  if (provider === 'openai') {
    return `OpenAI / ${model}`;
  }
  if (provider === 'claude') {
    return `Claude / ${model}`;
  }
  if (provider === 'mixed') {
    return `Mixed / ${model}`;
  }
  return `${provider} / ${model}`;
}

function aggregateReports(reports) {
  const groups = new Map();
  for (const report of reports) {
    for (const run of report.runs) {
      const labels = [
        `strategy:${run.strategy}`,
        `provider:${run.provider}`,
        run.openaiModel ? `openai:${run.openaiModel}` : '',
        run.claudeModel ? `claude:${run.claudeModel}` : '',
      ].filter(Boolean);

      for (const label of labels) {
        const group = groups.get(label) || {
          group: label,
          count: 0,
          successCount: 0,
          totalMs: 0,
          firstMs: 0,
          totalCostUsd: 0,
          totalInputTokens: 0,
          totalOutputTokens: 0,
          qualityScoreSum: 0,
          qualityScoreCount: 0,
        };

        group.count += 1;
        if (['success', 'partial_success'].includes(run.status)) {
          group.successCount += 1;
        }
        group.totalMs += run.latencyTotalMs || 0;
        group.firstMs += run.latencyFirstResultMs || 0;
        group.totalCostUsd += run.estimatedCostUsd || 0;
        group.totalInputTokens += run.usage?.inputTokens || 0;
        group.totalOutputTokens += run.usage?.outputTokens || 0;
        if (run.quality?.score !== null && run.quality?.score !== undefined) {
          group.qualityScoreSum += run.quality.score;
          group.qualityScoreCount += 1;
        }
        groups.set(label, group);
      }
    }
  }

  return [...groups.values()]
    .map((group) => ({
      ...group,
      avgTotalMs: Math.round(group.totalMs / group.count),
      avgFirstMs: Math.round(group.firstMs / group.count),
      totalCostUsd: Number(group.totalCostUsd.toFixed(6)),
      avgQualityScore: group.qualityScoreCount > 0
        ? Number((group.qualityScoreSum / group.qualityScoreCount).toFixed(3))
        : null,
    }))
    .sort((a, b) => a.group.localeCompare(b.group));
}

function mediaTypeForPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  if (ext === '.gif') return 'image/gif';
  throw new Error(`Unsupported image extension: ${ext}. Use png, jpg, jpeg, webp, or gif.`);
}

function minBy(items, getValue) {
  if (items.length === 0) {
    return null;
  }
  return items.reduce((best, item) => (getValue(item) < getValue(best) ? item : best), items[0]);
}

function maxBy(items, getValue) {
  if (items.length === 0) {
    return null;
  }
  return items.reduce((best, item) => (getValue(item) > getValue(best) ? item : best), items[0]);
}

function minPositive(values) {
  const positives = values.filter((value) => Number.isFinite(value) && value > 0);
  return positives.length > 0 ? Math.min(...positives) : 0;
}

function scoreLowerIsBetter(value, bestValue) {
  if (!Number.isFinite(value) || value <= 0 || !Number.isFinite(bestValue) || bestValue <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((bestValue / value) * 100)));
}

function deltaNumber(nextValue, previousValue) {
  if (!Number.isFinite(nextValue) || !Number.isFinite(previousValue)) {
    return null;
  }
  return nextValue - previousValue;
}

function formatSigned(value, digits = 0) {
  if (!Number.isFinite(value)) {
    return '-';
  }
  const rounded = digits > 0 ? Number(value).toFixed(digits) : Math.round(value);
  return `${value > 0 ? '+' : ''}${rounded}`;
}

function deltaClass(value, lowerIsBetter) {
  if (!Number.isFinite(value) || value === 0) {
    return '';
  }
  return (lowerIsBetter ? value < 0 : value > 0) ? 'delta-good' : 'delta-bad';
}

function splitCsv(value) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function sanitizeFileName(value) {
  return value.replace(/[^a-z0-9._-]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
}

function toTimestamp(date) {
  return date.toISOString().replace(/[:.]/g, '-');
}

function formatUsd(value) {
  return Number(value || 0).toFixed(6);
}

function formatQualityScore(quality) {
  if (!quality || quality.score === null || quality.score === undefined) {
    return '-';
  }
  return `${quality.matchedCount}/${quality.expectedCount} (${Math.round(quality.score * 100)}%)`;
}

function formatJudgeScore(judge) {
  if (!judge || !Number.isFinite(judge.overallScore)) {
    return '-';
  }
  return `${judge.overallScore}/100`;
}

function imagePathToFileUrl(imagePath) {
  const absolutePath = path.resolve(imagePath);
  return `file://${absolutePath.split(path.sep).map(encodeURIComponent).join('/')}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll('`', '&#96;');
}

function formatError(error) {
  if (error instanceof Error) {
    return error.stack || error.message;
  }
  return String(error);
}
