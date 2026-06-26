const QUESTIONS = {
  EI: [
    {
      id: 'EI_001',
      question: '난 대학생(고등학생) 때 학교에서 유명했나?',
      options: [{ text: '네', type: 'E' }, { text: '아니오', type: 'I' }],
    },
    {
      id: 'EI_002',
      question: '다음 중 고르시오',
      options: [{ text: '장기자랑 10분하기', type: 'E' }, { text: '친한 친구 1년 동안 못 만나기', type: 'I' }],
    },
    {
      id: 'EI_003',
      question: '침대에 누워있는데 친구가 보자고 부른다',
      options: [
        { text: '아 일단 나갈까? 준비하고 가야지', type: 'E' },
        { text: '아 아프다고 할까.. 침대 좋은데', type: 'I' },
      ],
    },
  ],
  SN: [
    {
      id: 'SN_001',
      question: '하루종일 반복 작업을 하실 수 있나요?',
      options: [{ text: '절대 못함', type: 'N' }, { text: '할 수 있음', type: 'S' }],
    },
    {
      id: 'SN_002',
      question: '좀비가 세상을 지배하면 어떻게 하지?',
      options: [{ text: '그럴 일 있나?', type: 'S' }, { text: '헐.. 그러면 일단 …', type: 'N' }],
    },
  ],
  TF: [
    {
      id: 'TF_001',
      question: '어제 힘들어서 치킨 먹었어',
      options: [
        { text: '아이고 많이 힘들었나 보다, 토닥토닥 ㅠㅠ', type: 'F' },
        { text: '어디 치킨? 어떤 거? 맛있었겠다', type: 'T' },
      ],
    },
    {
      id: 'TF_002',
      question: '나 운전하다가 사고 났어',
      options: [
        { text: '괜찮아? 많이 안 다쳤어? 내가 갈까?', type: 'F' },
        { text: '어디서? 보험 불렀어? 사고 사진부터 찍어', type: 'T' },
      ],
    },
    {
      id: 'TF_003',
      question: '슬픔을 둘로 나누면?',
      options: [{ text: '당근 절반이 되지?', type: 'F' }, { text: '슬과 픔', type: 'T' }],
    },
    {
      id: 'TF_004',
      question: '"생각해 볼게"라는 말에 대해서 어떻게 생각하는가',
      options: [
        { text: '별로 안 급한가 보네, 나중에 말해주겠지?', type: 'T' },
        { text: '(동공지진) 내가 뭐 잘못했나..?', type: 'F' },
      ],
    },
  ],
  PJ: [
    {
      id: 'PJ_001',
      question: '계획을 세우고 틀어졌을 때 어떤 반응인가?',
      options: [
        { text: '계획이 틀어져도 스트레스 안 받는다', type: 'P' },
        { text: '계획이 틀어지는 것조차 계획이다', type: 'J' },
      ],
    },
    {
      id: 'PJ_002',
      question: '외출할 때',
      options: [
        { text: '누구랑 언제 어디로 무엇을 타고 왜 가는지를 알아야 외출한다', type: 'J' },
        { text: '어디 갈지는 모르지만, 고민하면 늦으니까 일단 출발한다', type: 'P' },
      ],
    },
  ],
};

const AXIS_ORDER = ['EI', 'SN', 'TF', 'PJ'];

function getAllQuestions() {
  return AXIS_ORDER.flatMap(cat => QUESTIONS[cat] ?? []);
}

function calcMbti(answers) {
  const counts = { E:0, I:0, S:0, N:0, T:0, F:0, J:0, P:0 };
  Object.values(answers).forEach(type => { if (type in counts) counts[type]++; });
  return [
    counts.E >= counts.I ? 'E' : 'I',
    counts.N >= counts.S ? 'N' : 'S',
    counts.T >= counts.F ? 'T' : 'F',
    counts.J >= counts.P ? 'J' : 'P',
  ].join('');
}

function randomMbti() {
  return AXIS_ORDER
    .map(axis => axis[Math.floor(Math.random() * 2)])
    .join('');
}
