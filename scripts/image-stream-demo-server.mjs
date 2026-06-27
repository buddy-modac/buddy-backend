#!/usr/bin/env node

import { createServer } from 'node:http';
import { createReadStream, existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const HOST = '127.0.0.1';
const PORT = Number(process.env.PORT || 8767);
const OPENAI_IMAGE_GENERATIONS_URL = 'https://api.openai.com/v1/images/generations';
const ROOT_DIR = process.cwd();

const env = await loadEnv(path.join(ROOT_DIR, '.env'));
const apiKey = env.OPENAI_API_KEY || env.CODEX_API_KEY || process.env.OPENAI_API_KEY || process.env.CODEX_API_KEY || '';

if (!apiKey) {
  console.error('Missing OPENAI_API_KEY or CODEX_API_KEY.');
  process.exit(1);
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || '/', `http://${HOST}:${PORT}`);
    if (request.method === 'POST' && url.pathname === '/api/image-stream') {
      await handleImageStream(request, response);
      return;
    }
    await serveStatic(url.pathname, response);
  } catch (error) {
    if (!response.headersSent) {
      response.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
    }
    response.end(JSON.stringify({ error: error?.message || String(error) }));
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Image stream demo server: http://${HOST}:${PORT}/eval/results/image-gen-model-matrix/stream-demo.html`);
});

async function handleImageStream(request, response) {
  const body = await readRequestJson(request);
  const payload = {
    model: body.model || 'gpt-image-2',
    prompt: body.prompt || '',
    size: body.size || '1024x1024',
    quality: body.quality || 'medium',
    output_format: body.outputFormat || 'png',
    n: 1,
    stream: true,
    partial_images: Number.isFinite(Number(body.partialImages)) ? Number(body.partialImages) : 2,
  };

  if (!payload.prompt.trim()) {
    throw new Error('prompt is required.');
  }

  response.writeHead(200, {
    'Content-Type': 'application/x-ndjson; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
  });

  const startedAt = Date.now();
  writeNdjson(response, { type: 'request.started', payload: redactPayload(payload), elapsedMs: 0 });

  const upstream = await fetch(OPENAI_IMAGE_GENERATIONS_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!upstream.ok || !upstream.body) {
    const errorText = await upstream.text();
    writeNdjson(response, {
      type: 'request.failed',
      status: upstream.status,
      message: extractErrorMessage(errorText),
      elapsedMs: Date.now() - startedAt,
    });
    response.end();
    return;
  }

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let imageCount = 0;
  let firstImageMs = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      const event = parseSseEvent(part);
      if (!event.data || event.data === '[DONE]') {
        continue;
      }

      let parsed;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        writeNdjson(response, { type: 'raw', event: event.event, data: event.data, elapsedMs: Date.now() - startedAt });
        continue;
      }

      const b64 = findBase64Image(parsed);
      if (b64) {
        imageCount += 1;
        firstImageMs ??= Date.now() - startedAt;
        writeNdjson(response, {
          type: 'image',
          phase: parsed.type || event.event || 'image',
          index: parsed.partial_image_index ?? parsed.index ?? imageCount - 1,
          elapsedMs: Date.now() - startedAt,
          b64_json: b64,
        });
      } else {
        writeNdjson(response, {
          type: parsed.type || event.event || 'event',
          elapsedMs: Date.now() - startedAt,
          event: parsed,
        });
      }
    }
  }

  writeNdjson(response, {
    type: 'request.completed',
    elapsedMs: Date.now() - startedAt,
    firstImageMs,
    imageCount,
  });
  response.end();
}

function parseSseEvent(chunk) {
  const lines = chunk.split(/\r?\n/);
  const result = { event: '', data: '' };
  for (const line of lines) {
    if (line.startsWith('event:')) {
      result.event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      result.data += `${line.slice(5).trim()}\n`;
    }
  }
  result.data = result.data.trim();
  return result;
}

function findBase64Image(value) {
  if (!value || typeof value !== 'object') {
    return '';
  }
  if (typeof value.b64_json === 'string') {
    return value.b64_json;
  }
  if (typeof value.partial_image_b64 === 'string') {
    return value.partial_image_b64;
  }
  if (typeof value.image_b64 === 'string') {
    return value.image_b64;
  }
  for (const item of Object.values(value)) {
    const nested = findBase64Image(item);
    if (nested) {
      return nested;
    }
  }
  return '';
}

async function serveStatic(urlPath, response) {
  const cleanPath = decodeURIComponent(urlPath === '/' ? '/eval/results/image-gen-model-matrix/stream-demo.html' : urlPath);
  const filePath = path.resolve(ROOT_DIR, `.${cleanPath}`);
  if (!filePath.startsWith(ROOT_DIR) || !existsSync(filePath)) {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Not found');
    return;
  }

  response.writeHead(200, { 'Content-Type': contentTypeForPath(filePath) });
  createReadStream(filePath).pipe(response);
}

function writeNdjson(response, value) {
  response.write(`${JSON.stringify(value)}\n`);
}

function redactPayload(payload) {
  return {
    ...payload,
    prompt: payload.prompt.length > 240 ? `${payload.prompt.slice(0, 240)}...` : payload.prompt,
  };
}

async function readRequestJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : {};
}

function extractErrorMessage(text) {
  try {
    return JSON.parse(text)?.error?.message || text;
  } catch {
    return text;
  }
}

async function loadEnv(envPath) {
  if (!existsSync(envPath)) {
    return {};
  }
  const envText = await readFile(envPath, 'utf8');
  const result = {};
  for (const line of envText.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
      continue;
    }
    const index = trimmed.indexOf('=');
    result[trimmed.slice(0, index).trim()] = trimmed.slice(index + 1).trim().replace(/^["']|["']$/g, '');
  }
  return result;
}

function contentTypeForPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.html') return 'text/html; charset=utf-8';
  if (ext === '.css') return 'text/css; charset=utf-8';
  if (ext === '.js') return 'text/javascript; charset=utf-8';
  if (ext === '.json') return 'application/json; charset=utf-8';
  if (ext === '.md') return 'text/markdown; charset=utf-8';
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  return 'application/octet-stream';
}
