let allQuestions = getAllQuestions();
let answers = {};
let currentIndex = 0;

function showScreen(name) {
  document.querySelectorAll('[id^="screen-"]').forEach(el => el.classList.add('hidden'));
  document.getElementById(`screen-${name}`).classList.remove('hidden');
}

function renderQuestion() {
  const q = allQuestions[currentIndex];
  document.getElementById('progress').textContent = `${currentIndex + 1} / ${allQuestions.length}`;
  document.getElementById('question-text').textContent = q.question;

  const optionsEl = document.getElementById('options');
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
    showResult();
  }
}

function showResult() {
  const mbti = calcMbti(answers);
  document.getElementById('mbti-result').textContent = mbti;

  const counts = { E:0, I:0, S:0, N:0, T:0, F:0, J:0, P:0 };
  Object.values(answers).forEach(type => { if (type in counts) counts[type]++; });

  const scoresEl = document.getElementById('scores');
  scoresEl.innerHTML = '';
  [['E','I'], ['S','N'], ['T','F'], ['J','P']].forEach(([a, b]) => {
    const row = document.createElement('div');
    row.className = 'score-row';
    row.textContent = `${a}: ${counts[a]}  /  ${b}: ${counts[b]}`;
    scoresEl.appendChild(row);
  });

  showScreen('result');
}

document.getElementById('btn-retry').addEventListener('click', () => {
  currentIndex = 0;
  answers = {};
  showScreen('quiz');
  renderQuestion();
});

renderQuestion();
