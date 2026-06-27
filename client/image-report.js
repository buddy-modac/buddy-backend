const reportData = {
  metrics: {
    realRuns: 15,
    modelMatrixCost: '$0.5806',
    totalCost: '$0.9143',
    firstPreview: '10.04s',
  },
  insights: [
    'gpt-image-1.5는 이번 매트릭스에서 속도는 gpt-image-1과 비슷하고 파일 크기는 더 작게 나왔습니다.',
    'gpt-image-2는 모든 기사형 편집 케이스에서 49~53초대로 느렸습니다.',
    '긴 기사형 스크린샷은 모델을 바꿔도 텍스트가 깨지는 문제가 남아 crop/mask 기반 편집이 필요합니다.',
    '스트리밍은 최종 완료 시간은 줄이지 않지만 첫 preview를 약 10초에 보여줘 체감 대기를 줄였습니다.',
  ],
  stream: {
    model: 'gpt-image-1.5',
    size: '1024x1024',
    quality: 'medium',
    partialImages: 2,
    firstPartial: '10.04s',
    secondPartial: '14.31s',
    finalImage: '17.97s',
    saved: '7.92s',
    reportHref: '../eval/results/image-gen-model-matrix/stream-demo-result.md',
  },
  links: [
    { label: '모델 매트릭스 HTML', href: '../eval/results/image-gen-model-matrix/index.html' },
    { label: '비용 리포트 HTML', href: '../eval/results/image-gen-model-matrix/cost.html' },
    { label: '스트리밍 데모', href: '../eval/results/image-gen-model-matrix/stream-demo.html' },
    { label: '기사형 리포트 HTML', href: '../eval/results/image-gen-article-real/index.html' },
    { label: '요약 Markdown', href: '../docs/image-gen-eval-report.md' },
    { label: '비용 Markdown', href: '../docs/image-gen-cost-estimate.md' },
  ],
  runs: [
    ['medium-article-translate-ko', 'translate-text', 'gpt-image-1', '30.516s', '1,629,917', '$0.0672', 'medium-article-translate-ko-gpt-image-1-0.png', 'medium-article-translate-ko-gpt-image-1-2026-06-27T05-59-02-348Z.md'],
    ['medium-article-translate-ko', 'translate-text', 'gpt-image-1.5', '29.314s', '968,275', '$0.0795', 'medium-article-translate-ko-gpt-image-1.5-0.png', 'medium-article-translate-ko-gpt-image-1.5-2026-06-27T05-59-31-670Z.md'],
    ['medium-article-translate-ko', 'translate-text', 'gpt-image-2', '48.738s', '1,558,404', '$0.0515', 'medium-article-translate-ko-gpt-image-2-0.png', 'medium-article-translate-ko-gpt-image-2-2026-06-27T06-00-20-413Z.md'],
    ['medium-article-image-change', 'edit-image', 'gpt-image-1', '27.080s', '1,594,668', '$0.0672', 'medium-article-image-change-gpt-image-1-0.png', 'medium-article-image-change-gpt-image-1-2026-06-27T06-00-47-500Z.md'],
    ['medium-article-image-change', 'edit-image', 'gpt-image-1.5', '29.538s', '1,353,362', '$0.0729', 'medium-article-image-change-gpt-image-1.5-0.png', 'medium-article-image-change-gpt-image-1.5-2026-06-27T06-01-17-048Z.md'],
    ['medium-article-image-change', 'edit-image', 'gpt-image-2', '53.427s', '1,791,524', '$0.0515', 'medium-article-image-change-gpt-image-2-0.png', 'medium-article-image-change-gpt-image-2-2026-06-27T06-02-10-485Z.md'],
    ['medium-article-speech-bubble', 'edit-image', 'gpt-image-1', '28.575s', '1,576,946', '$0.0672', 'medium-article-speech-bubble-gpt-image-1-0.png', 'medium-article-speech-bubble-gpt-image-1-2026-06-27T06-02-39-067Z.md'],
    ['medium-article-speech-bubble', 'edit-image', 'gpt-image-1.5', '29.882s', '1,121,982', '$0.0722', 'medium-article-speech-bubble-gpt-image-1.5-0.png', 'medium-article-speech-bubble-gpt-image-1.5-2026-06-27T06-03-08-964Z.md'],
    ['medium-article-speech-bubble', 'edit-image', 'gpt-image-2', '50.997s', '1,567,449', '$0.0515', 'medium-article-speech-bubble-gpt-image-2-0.png', 'medium-article-speech-bubble-gpt-image-2-2026-06-27T06-03-59-973Z.md'],
  ].map(([caseId, action, model, latency, bytes, cost, imageName, reportName]) => ({
    caseId,
    action,
    model,
    latency,
    bytes,
    cost,
    image: `../eval/results/image-gen-model-matrix/assets/${imageName}`,
    report: `../eval/results/image-gen-model-matrix/${reportName}`,
  })),
};

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function link(label, href, className) {
  const anchor = el('a', className, label);
  anchor.href = href;
  return anchor;
}

function renderMetrics() {
  document.getElementById('metric-runs').textContent = String(reportData.metrics.realRuns);
  document.getElementById('metric-matrix-cost').textContent = reportData.metrics.modelMatrixCost;
  document.getElementById('metric-total-cost').textContent = reportData.metrics.totalCost;
  document.getElementById('metric-first-preview').textContent = reportData.metrics.firstPreview;
}

function renderTable() {
  const tbody = document.getElementById('model-table');
  tbody.replaceChildren(...reportData.runs.map((run) => {
    const row = document.createElement('tr');
    [run.caseId, run.model, run.action, run.latency, run.bytes, run.cost].forEach((value) => row.append(el('td', '', value)));
    const reportCell = document.createElement('td');
    reportCell.append(link('열기', run.report));
    row.append(reportCell);
    return row;
  }));
}

function renderGallery() {
  const gallery = document.getElementById('gallery');
  gallery.replaceChildren(...reportData.runs.map((run) => {
    const card = el('article', 'report-image-card');
    const image = document.createElement('img');
    image.src = run.image;
    image.alt = `${run.caseId} ${run.model}`;
    const body = el('div', 'report-image-card__body');
    body.append(el('h3', '', run.caseId));
    body.append(el('p', '', `${run.model} · ${run.latency} · ${run.bytes} bytes`));
    body.append(link('상세 리포트', run.report));
    card.append(image, body);
    return card;
  }));
}

function renderInsights() {
  const list = document.getElementById('insights');
  list.replaceChildren(...reportData.insights.map((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    return li;
  }));
}

function renderLinks() {
  const list = document.getElementById('report-links');
  list.replaceChildren(...reportData.links.map((item) => link(item.label, item.href, 'report-link')));
}

function renderStreamSummary() {
  const stream = reportData.stream;
  const rows = [
    ['Model', stream.model],
    ['Size', stream.size],
    ['Quality', stream.quality],
    ['Partial images', String(stream.partialImages)],
    ['First partial', stream.firstPartial],
    ['Second partial', stream.secondPartial],
    ['Final image', stream.finalImage],
    ['Perceived wait saved', stream.saved],
  ];
  const dl = el('dl', 'stream-grid');
  rows.forEach(([key, value]) => {
    const item = el('div', 'stream-item');
    item.append(el('dt', '', key));
    item.append(el('dd', '', value));
    dl.append(item);
  });
  document.getElementById('stream-summary').replaceChildren(dl, link('스트리밍 결과 원문', stream.reportHref, 'report-link'));
}

renderMetrics();
renderTable();
renderGallery();
renderInsights();
renderLinks();
renderStreamSummary();
