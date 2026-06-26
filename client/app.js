// 백엔드 서버 주소 — 로컬 테스트 시 'http://localhost:8000', 배포 서버로 변경 시 여기만 수정
// ⚠️ GitHub Pages(https)에서 사용할 때는 배포 서버도 반드시 https 주소여야 혼합 콘텐츠 차단을 피할 수 있음
const API_BASE_URL = 'http://localhost:8000';

let allQuestions = [];  // [{id, question, options: [{text, type}]}, ...]
let answers = {};       // { questionId: selectedType }
let currentIndex = 0;

const screens = {
  start: document.getElementById('screen-start'),
  quiz: document.getElementById('screen-quiz'),
  result: document.getElementById('screen-result'),
  error: document.getElementById('screen-error'),
};

function showScreen(name) {
  Object.values(screens).forEach(s => s.classList.add('hidden'));
  screens[name].classList.remove('hidden');
}

// 질문 전체 로드
async function loadQuestions() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/questions`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // { EI: [...], SN: [...], TF: [...], PJ: [...] } → 순서대로 flat
    const ORDER = ['EI', 'SN', 'TF', 'PJ'];
    allQuestions = ORDER.flatMap(cat => data.questions?.[cat] ?? []);

    if (allQuestions.length === 0) throw new Error('질문 데이터가 비어있어요');

    currentIndex = 0;
    answers = {};
    showScreen('quiz');
    renderQuestion();
  } catch (err) {
    showError(`질문 로드 실패: ${err.message}`);
  }
}

function renderQuestion() {
  const q = allQuestions[currentIndex];
  const progressEl = document.getElementById('progress');
  const questionEl = document.getElementById('question-text');
  const optionsEl = document.getElementById('options');

  progressEl.textContent = `${currentIndex + 1} / ${allQuestions.length}`;
  questionEl.textContent = q.question;

  optionsEl.innerHTML = '';
  q.options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.textContent = opt.text;
    btn.addEventListener('click', () => selectAnswer(q.id, opt.type));
    optionsEl.appendChild(btn);
  });
}

function selectAnswer(questionId, type) {
  answers[questionId] = type;

  if (currentIndex < allQuestions.length - 1) {
    currentIndex++;
    renderQuestion();
  } else {
    submitAnswers();
  }
}

// 답변 제출 → 결과 수신
async function submitAnswers() {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}/api/result`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    });
  } catch {
    // 네트워크 오류(서버 미실행) → 로컬 계산 fallback
    const mbti = calcMbtiLocal();
    showResult({ mbti, note: '(로컬 계산 — 서버에 연결할 수 없음)' });
    return;
  }

  // 404/501: 엔드포인트 미구현 → 로컬 계산 fallback
  if (res.status === 404 || res.status === 501) {
    const mbti = calcMbtiLocal();
    showResult({ mbti, note: '(로컬 계산 — 백엔드 /api/result 미구현)' });
    return;
  }

  // 그 외 HTTP 오류(400, 422, 500 등) → 에러 화면으로 표시
  if (!res.ok) {
    showError(`결과 조회 실패: HTTP ${res.status}`);
    return;
  }

  const data = await res.json();
  showResult(data);
}

// 백엔드 없이 로컬에서 MBTI 계산 (fallback)
function calcMbtiLocal() {
  const axes = { EI: {E:0,I:0}, SN: {S:0,N:0}, TF: {T:0,F:0}, PJ: {P:0,J:0} };
  const axisMap = { E:'EI',I:'EI', S:'SN',N:'SN', T:'TF',F:'TF', P:'PJ',J:'PJ' };

  allQuestions.forEach(q => {
    const type = answers[q.id];
    if (type && axisMap[type]) axes[axisMap[type]][type]++;
  });

  const mbti = [
    axes.EI.E >= axes.EI.I ? 'E' : 'I',
    axes.SN.N >= axes.SN.S ? 'N' : 'S',
    axes.TF.T >= axes.TF.F ? 'T' : 'F',
    axes.PJ.J >= axes.PJ.P ? 'J' : 'P',
  ].join('');

  return mbti;
}

function showResult(data) {
  document.getElementById('mbti-result').textContent = data.mbti ?? '??';

  const scoresEl = document.getElementById('scores');
  scoresEl.innerHTML = '';
  if (data.scores) {
    Object.entries(data.scores).forEach(([, counts]) => {
      const row = document.createElement('div');
      row.className = 'score-row';
      row.textContent = Object.entries(counts).map(([t, n]) => `${t}: ${n}`).join(' / ');
      scoresEl.appendChild(row);
    });
  }

  if (data.note) {
    const noteEl = document.createElement('p');
    noteEl.className = 'note';
    noteEl.textContent = data.note;
    scoresEl.appendChild(noteEl);
  }

  showScreen('result');
}

function showError(message) {
  document.getElementById('error-message').textContent = message;
  showScreen('error');
}

// 이벤트 바인딩
document.getElementById('btn-start').addEventListener('click', loadQuestions);
document.getElementById('btn-retry').addEventListener('click', () => {
  currentIndex = 0;
  answers = {};
  showScreen('start');
});
document.getElementById('btn-error-retry').addEventListener('click', () => showScreen('start'));
