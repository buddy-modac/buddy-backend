const fs = require('fs');
const path = require('path');

const MBTI_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(MBTI_ROOT, '..', '..');
const WORKSPACE_ROOT = path.resolve(REPO_ROOT, '..');
const CLIPPINGS_DIR = path.join(WORKSPACE_ROOT, 'Clippings');
const OUT_PATH = path.join(MBTI_ROOT, 'prompt_reference.json');

const TYPES = [
  'ENFJ',
  'ENFP',
  'ENTJ',
  'ENTP',
  'ESFJ',
  'ESFP',
  'ESTJ',
  'ESTP',
  'INFJ',
  'INFP',
  'INTJ',
  'INTP',
  'ISFJ',
  'ISFP',
  'ISTJ',
  'ISTP',
];

const FUNCTION_NAMES = {
  Fe: '외향 감정',
  Fi: '내향 감정',
  Ne: '외향 직관',
  Ni: '내향 직관',
  Se: '외향 감각',
  Si: '내향 감각',
  Te: '외향 사고',
  Ti: '내향 사고',
};

const FUNCTION_STACKS = {
  ENFJ: ['Fe', 'Ni', 'Se', 'Ti'],
  ENFP: ['Ne', 'Fi', 'Te', 'Si'],
  ENTJ: ['Te', 'Ni', 'Se', 'Fi'],
  ENTP: ['Ne', 'Ti', 'Fe', 'Si'],
  ESFJ: ['Fe', 'Si', 'Ne', 'Ti'],
  ESFP: ['Se', 'Fi', 'Te', 'Ni'],
  ESTJ: ['Te', 'Si', 'Ne', 'Fi'],
  ESTP: ['Se', 'Ti', 'Fe', 'Ni'],
  INFJ: ['Ni', 'Fe', 'Ti', 'Se'],
  INFP: ['Fi', 'Ne', 'Si', 'Te'],
  INTJ: ['Ni', 'Te', 'Fi', 'Se'],
  INTP: ['Ti', 'Ne', 'Si', 'Fe'],
  ISFJ: ['Si', 'Fe', 'Ti', 'Ne'],
  ISFP: ['Fi', 'Se', 'Ni', 'Te'],
  ISTJ: ['Si', 'Te', 'Fi', 'Ne'],
  ISTP: ['Ti', 'Se', 'Ni', 'Fe'],
};

const SCENARIO_SLOTS = [
  ['sudden_invite', '갑작스러운 약속 제안'],
  ['friend_worry', '친구가 고민 상담'],
  ['team_deadline_miss', '팀원이 마감 미준수'],
  ['trip_planning', '여행 계획 짜기'],
  ['menu_choice', '메뉴 고르기'],
  ['opinion_conflict', '의견 충돌'],
  ['first_meeting', '처음 만난 사람과 대화'],
  ['plan_changed', '일정 변경'],
  ['presentation_prep', '발표 준비'],
  ['bug_or_incident', '버그/장애 대응'],
];

function readText(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function extractFrontmatter(text) {
  if (!text.startsWith('---')) return {};
  const end = text.indexOf('\n---', 3);
  if (end === -1) return {};
  const frontmatter = text.slice(3, end).split(/\r?\n/);
  const result = {};
  for (const line of frontmatter) {
    const match = line.match(/^([A-Za-z_-]+):\s*(.*)$/);
    if (match) {
      result[match[1]] = match[2].replace(/^"|"$/g, '').trim();
    }
  }
  return result;
}

function decodeEntities(text) {
  return text
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"');
}

function cleanText(value) {
  return decodeEntities(value)
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<sup>.*?<\/sup>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\[\^?\d+(?:\.\d+)?\]/g, '')
    .replace(/\[\\?\[[^\]]+\\?\]\]\([^)]*\)/g, '')
    .replace(/\[\\?\[[^\]]+\\?\]\]/g, '')
    .replace(/\[\[[^\]]+\]\]/g, '')
    .replace(/\[[^\]]*\]\(#(?:fn|rfn|s)-?[^)]*\)/g, '')
    .replace(/\[\[?편집\]?\]/g, '')
    .replace(/\\\[/g, '[')
    .replace(/\\\]/g, ']')
    .replace(/\\-/g, '-')
    .replace(/\*\*/g, '')
    .replace(/__/g, '')
    .replace(/`/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function cleanHeading(value) {
  return cleanText(value).replace(/\[편집\]/g, '').replace(/편집$/g, '').trim();
}

function isNoiseLine(line) {
  const text = cleanText(line);
  return (
    !text ||
    text === '---' ||
    text === '편집 요청' ||
    text.startsWith('출처:') ||
    text.startsWith('└') ||
    text.includes('ACL 탭') ||
    text.includes('편집 권한') ||
    text.includes('문서함에 추가') ||
    text.includes('분류') ||
    text.includes('나무위키') ||
    text.includes('해당 문서') ||
    text.includes('토론') ||
    text.includes('역사')
  );
}

function parseSections(lines) {
  const headings = [];
  lines.forEach((line, index) => {
    const match = line.match(/^(#{2,6})\s+(.+)$/);
    if (match) {
      headings.push({
        index,
        level: match[1].length,
        title: cleanHeading(match[2]),
      });
    }
  });

  return headings.map((heading, idx) => {
    let end = lines.length;
    for (let next = idx + 1; next < headings.length; next += 1) {
      if (headings[next].level <= heading.level) {
        end = headings[next].index;
        break;
      }
    }
    return {
      title: heading.title,
      level: heading.level,
      startLine: heading.index + 1,
      endLine: end,
      lines: lines.slice(heading.index + 1, end),
    };
  });
}

function findFirstSection(sections, patterns) {
  return sections.find(section => patterns.some(pattern => pattern.test(section.title)));
}

function getSectionLines(sections, patterns) {
  const section = findFirstSection(sections, patterns);
  return section ? section.lines : [];
}

function getCleanLines(lines, limit = 20) {
  const result = [];
  for (const line of lines) {
    const cleaned = cleanText(line.replace(/^\s*[-*]\s*/, ''));
    if (isNoiseLine(cleaned)) continue;
    if (cleaned.length < 8) continue;
    if (/^\|?\s*-{2,}/.test(cleaned)) continue;
    if (/^\|/.test(cleaned)) continue;
    if (/^\d+$/.test(cleaned)) continue;
    result.push(cleaned);
    if (result.length >= limit) break;
  }
  return result;
}

function getBulletLines(lines, limit = 18) {
  const result = [];
  for (const line of lines) {
    if (!/^\s*[-*]\s+/.test(line)) continue;
    const cleaned = cleanText(line.replace(/^\s*[-*]\s+/, ''));
    if (isNoiseLine(cleaned)) continue;
    if (cleaned.length < 8) continue;
    if (cleaned.includes('테스트별 별칭')) continue;
    if (cleaned.includes('주의: MBTI')) continue;
    if (cleaned.includes('출처')) continue;
    result.push(cleaned);
    if (result.length >= limit) break;
  }
  return result;
}

function extractKeywordBlock(lines, startPattern, stopPatterns) {
  const start = lines.findIndex(line => startPattern.test(line));
  if (start === -1) return [];
  const collected = [];
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^#{2,6}\s+/.test(line)) break;
    if (stopPatterns.some(pattern => pattern.test(line))) break;
    const cleaned = cleanText(line);
    if (!cleaned || cleaned.includes('키워드')) continue;
    collected.push(cleaned);
  }
  return collected
    .join(' · ')
    .split(/\s*[·•]\s*|\s*,\s*/)
    .map(item => cleanText(item))
    .filter(item => item && item.length >= 2)
    .filter((item, index, all) => all.indexOf(item) === index)
    .slice(0, 30);
}

function extractAliases(lines, type) {
  const start = lines.findIndex(line => line.includes('테스트별 별칭'));
  if (start === -1) return [];
  const window = lines.slice(start, start + 12).map(cleanText).filter(Boolean);
  const aliases = [];
  for (const line of window) {
    if (!line.includes('|')) continue;
    const pieces = line
      .split('|')
      .map(piece => cleanText(piece))
      .filter(Boolean)
      .filter(piece => !['---', '영어', '한국어'].includes(piece));
    pieces.forEach(piece => {
      if (!piece.includes(type) && piece.length > 1 && !aliases.includes(piece)) {
        aliases.push(piece);
      }
    });
  }
  return aliases.slice(0, 8);
}

function axisMeaning(type) {
  const [energy, perception, judgment, lifestyle] = type.split('');
  return {
    energy,
    perception,
    judgment,
    lifestyle,
    labels: {
      energy: energy === 'E' ? '외향: 외부 활동, 표출, 사회적 상호작용을 우선 관찰' : '내향: 내면 처리, 에너지 보존, 깊은 관계를 우선 관찰',
      perception: perception === 'N' ? '직관: 가능성, 의미, 미래 방향, 패턴 해석을 우선 관찰' : '감각: 현실성, 경험, 구체 정보, 실용성을 우선 관찰',
      judgment: judgment === 'F' ? '감정: 관계 영향, 가치 판단, 정서 반응을 우선 관찰' : '사고: 논리, 기준, 효율, 사실 판단을 우선 관찰',
      lifestyle: lifestyle === 'J' ? '판단: 계획, 마감, 기준, 결정성을 우선 관찰' : '인식: 자율성, 유동성, 즉흥 조정을 우선 관찰',
    },
  };
}

function functionStack(type) {
  const roles = ['dominant', 'auxiliary', 'tertiary', 'inferior'];
  const roleLabels = ['주기능', '부기능', '3차 기능', '열등 기능'];
  return FUNCTION_STACKS[type].map((code, index) => ({
    role: roles[index],
    roleLabel: roleLabels[index],
    code,
    name: FUNCTION_NAMES[code],
  }));
}

function pickByKeywords(items, keywords, limit) {
  return items
    .filter(item => keywords.some(keyword => item.includes(keyword)))
    .slice(0, limit);
}

function fallbackList(primary, fallback, limit) {
  const merged = [...primary, ...fallback].filter(Boolean);
  return merged.filter((item, index, all) => all.indexOf(item) === index).slice(0, limit);
}

function compactSentence(text, maxLength = 180) {
  if (!text) return null;
  const cleaned = cleanText(text);
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1).trim()}…`;
}

function makeScenarioRules(type, closeKeywords, farKeywords) {
  const axis = axisMeaning(type);
  const [EorI, SorN, TorF, JorP] = type.split('');
  const close = closeKeywords.slice(0, 6);
  const far = farKeywords.slice(0, 4);

  const socialStart =
    EorI === 'E'
      ? '사람/분위기/참여 가능성을 먼저 확인한다'
      : '내 에너지, 친밀도, 목적을 먼저 확인한다';
  const planningBias =
    JorP === 'J'
      ? '시간·장소·역할을 정리해 예측 가능하게 만든다'
      : '흥미와 흐름을 보며 선택지를 열어 둔다';
  const careBias =
    TorF === 'F'
      ? '상대 감정과 관계 영향을 먼저 안정시킨다'
      : '문제 원인과 해결 조건을 먼저 분리한다';
  const infoBias =
    SorN === 'N'
      ? '표면 정보보다 의미, 패턴, 장기 가능성을 해석한다'
      : '현재 사실, 경험, 구체 조건을 기준으로 판단한다';

  const data = {
    sudden_invite: `${socialStart}. 이후 ${planningBias}.`,
    friend_worry: `${careBias}. ${infoBias}.`,
    team_deadline_miss:
      JorP === 'J'
        ? `${careBias}. 남은 범위, 담당자, 마감을 다시 고정한다.`
        : `${careBias}. 지금 가능한 우회책과 임시 조정을 빠르게 찾는다.`,
    trip_planning:
      JorP === 'J'
        ? `${infoBias}. 동선, 예약, 마감 시간을 먼저 구조화한다.`
        : `${infoBias}. 현장 선택지와 재미 요소를 남겨 둔다.`,
    menu_choice:
      TorF === 'F'
        ? `동행자의 취향과 분위기를 살피고 ${SorN === 'N' ? '새로운 의미나 경험' : '실제 만족도'}를 고려한다.`
        : `가격, 효율, 실패 가능성, ${SorN === 'N' ? '새로움' : '검증된 맛'}을 기준으로 좁힌다.`,
    opinion_conflict:
      TorF === 'F'
        ? `관계 손상을 줄이는 표현을 먼저 고르고, 합의 가능한 지점을 찾는다.`
        : `논점, 기준, 근거를 분리해 무엇이 맞는지 검증한다.`,
    first_meeting:
      EorI === 'E'
        ? `먼저 말을 걸거나 리액션으로 분위기를 열고, 공통 관심사를 찾는다.`
        : `상대의 말투와 관심사를 관찰한 뒤 안전한 주제로 천천히 들어간다.`,
    plan_changed:
      JorP === 'J'
        ? `변경 원인을 확인하고 새 계획, 기준, 마감을 다시 잡아 안정화한다.`
        : `변경을 새로운 선택지로 받아들이고 현재 가능한 방향으로 전환한다.`,
    presentation_prep:
      TorF === 'F'
        ? `청중 반응, 메시지의 설득력, 정서적 납득을 우선 조정한다.`
        : `논리 구조, 근거, 핵심 결론의 명확성을 우선 조정한다.`,
    bug_or_incident:
      TorF === 'T'
        ? `증상, 원인, 재현 조건을 분리하고 임시 조치와 근본 해결을 나눈다.`
        : `영향을 받는 사람을 안심시키고 상황 공유와 복구 흐름을 정리한다.`,
  };

  return SCENARIO_SLOTS.map(([scenarioId, label]) => ({
    scenarioId,
    label,
    expectedBehavior: data[scenarioId],
    promptRule: `사용자 행동이 ${type}로 추론될 때는 ${axis.labels.energy}; ${axis.labels.perception}; ${axis.labels.judgment}; ${axis.labels.lifestyle} 기준으로 해석하되, 근거 태그 ${close.join(', ') || type}를 우선 참고한다.`,
    evidenceTags: close,
    avoidOverclaiming: far.length ? `반대/거리 키워드(${far.join(', ')})를 단정형 페널티로 쓰지 말고 보조 신호로만 사용한다.` : '반대 성향은 보조 신호로만 사용한다.',
  }));
}

function buildTypeRecord(type) {
  const filePath = path.join(CLIPPINGS_DIR, `${type}.md`);
  const raw = readText(filePath);
  const lines = raw.split(/\r?\n/);
  const frontmatter = extractFrontmatter(raw);
  const sections = parseSections(lines);
  const sectionTitles = sections.map(section => section.title);

  const descriptionLines = getSectionLines(sections, [/^(설명|총론)$/]);
  const detailLines = getSectionLines(sections, [/상세|사고방식|내면|외면/]);
  const featureLines = getSectionLines(sections, [/일반적인 특징|^특징$|유형의 특징|강점|약점|의사소통|인간관계|성격의 장단점|보완해야 할 점|조언/]);
  const abilityLines = getSectionLines(sections, [/능력 발휘|적성 분야|직장생활|직무|직업/]);
  const relationshipLines = getSectionLines(sections, [/타 .*관계|궁합|사회관계|우정과 인간관계|인간관계/]);
  const romanceLines = getSectionLines(sections, [/연애 스타일|사랑과 로맨스/]);

  const closeKeywords = extractKeywordBlock(lines, /가까울 수 있는 키워드/, [/멀 수 있는 키워드/]);
  const farKeywords = extractKeywordBlock(lines, /멀 수 있는 키워드/, [/^#{2,6}\s+/, /통계 및 여담/]);
  const aliases = extractAliases(lines, type);

  const description = getCleanLines(descriptionLines, 5);
  const details = getCleanLines(detailLines, 10);
  const features = fallbackList(getBulletLines(featureLines, 16), [...getCleanLines(featureLines, 8), ...getCleanLines(detailLines, 8)], 16);
  const abilities = fallbackList(getBulletLines(abilityLines, 10), getCleanLines(abilityLines, 6), 10);
  const relationships = fallbackList(getBulletLines(relationshipLines, 10), getCleanLines(relationshipLines, 6), 10);
  const romance = fallbackList(getCleanLines(romanceLines, 4), getBulletLines(romanceLines, 4), 4);

  const behaviorCues = fallbackList(closeKeywords.slice(0, 12), features.slice(0, 6), 12);
  const communicationStyle = fallbackList(
    pickByKeywords([...features, ...details, ...description], ['말', '대화', '소통', '표현', '언변', '직설', '감정', '관계', '눈치'], 6),
    closeKeywords.filter(keyword => /대화|언변|관계|리액션|표현|눈치|침묵|직설/.test(keyword)),
    6,
  );
  const decisionStyle = fallbackList(
    pickByKeywords([...features, ...details, ...description], ['계획', '논리', '가치', '효율', '현실', '미래', '가능성', '목표', '기준', '선택', '판단'], 6),
    [axisMeaning(type).labels.perception, axisMeaning(type).labels.judgment, axisMeaning(type).labels.lifestyle],
    6,
  );
  const collaborationStyle = fallbackList(
    pickByKeywords([...abilities, ...features, ...relationships], ['리더', '협력', '조화', '팀', '조직', '역할', '책임', '관리', '도움', '직업', '일'], 6),
    abilities.slice(0, 4),
    6,
  );
  const conflictStyle = fallbackList(
    pickByKeywords([...features, ...relationships, ...details], ['갈등', '비판', '고집', '불편', '단점', '약점', '상처', '논쟁', '충돌', '싫어'], 6),
    farKeywords.slice(0, 6),
    6,
  );
  const stressPattern = fallbackList(
    pickByKeywords([...features, ...details], ['스트레스', '급해', '충동', '불안', '예민', '힘들', '압박', '방치', '피로', '완벽'], 6),
    farKeywords.slice(0, 5),
    6,
  );
  const promptBehaviorCues = behaviorCues.map(item => compactSentence(item, 90)).filter(Boolean);
  const promptCommunicationStyle = communicationStyle.map(item => compactSentence(item, 150)).filter(Boolean);
  const promptDecisionStyle = decisionStyle.map(item => compactSentence(item, 150)).filter(Boolean);
  const promptCollaborationStyle = collaborationStyle.map(item => compactSentence(item, 150)).filter(Boolean);
  const promptConflictStyle = conflictStyle.map(item => compactSentence(item, 150)).filter(Boolean);
  const promptStressPattern = stressPattern.map(item => compactSentence(item, 150)).filter(Boolean);

  return {
    type,
    namuwikiUrl: frontmatter.source || `https://namu.wiki/w/${type}`,
    clippingPath: path.relative(WORKSPACE_ROOT, filePath),
    sourceStatus: 'extracted_from_local_clipping',
    sourceMeta: {
      title: frontmatter.title || type,
      source: frontmatter.source || `https://namu.wiki/w/${type}`,
      published: frontmatter.published || null,
      clippedAt: frontmatter.created || null,
      lineCount: lines.length,
      extractedSectionTitles: sectionTitles.slice(0, 40),
    },
    typeCode: axisMeaning(type),
    functionStack: functionStack(type),
    rawExtracts: {
      aliases,
      description: description.map(item => compactSentence(item, 220)),
      details: details.map(item => compactSentence(item, 220)),
      closeKeywords,
      farKeywords,
      generalCharacteristics: features.map(item => compactSentence(item, 220)),
      abilityFields: abilities.map(item => compactSentence(item, 180)),
      relationshipNotes: relationships.map(item => compactSentence(item, 180)),
      romanceStyle: romance.map(item => compactSentence(item, 220)),
    },
    promptReference: {
      coreIdentity: compactSentence(description[0] || details[0] || `${type} 유형`, 220),
      behaviorCues: promptBehaviorCues,
      communicationStyle: promptCommunicationStyle,
      decisionStyle: promptDecisionStyle,
      collaborationStyle: promptCollaborationStyle,
      conflictStyle: promptConflictStyle,
      stressPattern: promptStressPattern,
      promptDo: [
        `${type}를 단정하지 말고, 관찰된 행동을 ${type}의 선호 지표 및 원문 키워드와 함께 해석한다.`,
        `프롬프트에는 ${promptBehaviorCues.slice(0, 5).join(', ') || type} 같은 가까운 키워드를 행동 힌트로 사용한다.`,
        `상황별 응답은 ${type}의 ${axisMeaning(type).labels.energy}, ${axisMeaning(type).labels.judgment} 경향을 함께 반영한다.`,
      ],
      promptDont: [
        'MBTI 하나만으로 사용자의 성격이나 행동을 확정하지 않는다.',
        farKeywords.length
          ? `거리 키워드(${farKeywords.slice(0, 5).join(', ')})를 혐오/비난 문구로 쓰지 않는다.`
          : '거리 키워드는 보조 신호로만 사용한다.',
        '나무위키의 유명인 목록이나 커뮤니티 여담은 prompt rule의 핵심 근거로 쓰지 않는다.',
      ],
      scenarioRules: makeScenarioRules(type, promptBehaviorCues, farKeywords),
    },
  };
}

function main() {
  const missing = TYPES.filter(type => !fs.existsSync(path.join(CLIPPINGS_DIR, `${type}.md`)));
  if (missing.length) {
    console.error(JSON.stringify({ ok: false, missing }, null, 2));
    process.exit(1);
  }

  const data = {
    meta: {
      name: 'MBTI prompt/rule reference dataset',
      version: '1.0.0',
      language: 'ko',
      purpose: '팀원이 MBTI 기반 프롬프트와 룰을 만들 때 참고할 수 있도록, 로컬 Clippings의 나무위키 16개 MBTI 문서를 구조화한 데이터입니다.',
      sourceBaseDir: path.relative(WORKSPACE_ROOT, CLIPPINGS_DIR),
      sourceStatus: 'generated_from_local_namuwiki_clippings',
      excludedContext: [
        'buddy-backend README',
        '기존 퀴즈 질문셋',
        '프론트엔드 테스트 UI',
        '결과 계산용 답변 벡터',
      ],
      categoryUrl: 'https://namu.wiki/w/%EB%B6%84%EB%A5%98:16%EA%B0%80%EC%A7%80%20%EC%84%B1%EA%B2%A9%20%EC%9C%A0%ED%98%95',
      sourceTypes: TYPES,
      scenarioSlots: SCENARIO_SLOTS.map(([id, label]) => ({ id, label })),
      promptRulePrinciples: [
        'MBTI는 확정 진단이 아니라 경향값으로만 사용합니다.',
        '프롬프트는 특정 유형을 고정관념으로 단정하지 않고, 관찰된 행동과 상황을 함께 반영합니다.',
        '나무위키 문장 그대로를 길게 주입하지 않고, 짧은 근거 단위로 정규화해 룰화합니다.',
        '유형별 장점/단점 한쪽만 쓰지 않고 core, behavior, communication, decision, collaboration, conflict, stress를 함께 봅니다.',
      ],
    },
    types: TYPES.map(buildTypeRecord),
  };

  fs.writeFileSync(OUT_PATH, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ ok: true, outPath: path.relative(WORKSPACE_ROOT, OUT_PATH), typeRecords: data.types.length }, null, 2));
}

main();
