const fs = require('fs');
const path = require('path');

const MBTI_ROOT = path.resolve(__dirname, '..');
const DATA_PATH = path.join(MBTI_ROOT, 'prompt_reference.json');

const EXPECTED_TYPES = [
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

const PROMPT_REFERENCE_KEYS = [
  'coreIdentity',
  'behaviorCues',
  'communicationStyle',
  'decisionStyle',
  'collaborationStyle',
  'conflictStyle',
  'stressPattern',
  'promptDo',
  'promptDont',
  'scenarioRules',
];

function fail(message, details) {
  console.error(JSON.stringify({ ok: false, message, details }, null, 2));
  process.exit(1);
}

function assert(condition, message, details) {
  if (!condition) {
    fail(message, details);
  }
}

function unique(values) {
  return [...new Set(values)];
}

function main() {
  const data = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
  const types = data.types.map(item => item.type);
  const scenarioSlotIds = data.meta.scenarioSlots.map(slot => slot.id);

  assert(data.meta.purpose.includes('프롬프트') || data.meta.purpose.includes('prompt'), 'Purpose must describe prompt/rule usage.', data.meta.purpose);
  assert(data.types.length === 16, 'Expected 16 MBTI type records.', { actual: data.types.length });
  assert(unique(types).length === 16, 'Type records must be unique.', types);
  assert(scenarioSlotIds.length === 10, 'Expected 10 scenario slots for prompt/rule extraction.', { actual: scenarioSlotIds.length });
  assert(unique(scenarioSlotIds).length === scenarioSlotIds.length, 'Scenario slot IDs must be unique.', scenarioSlotIds);

  const missingTypes = EXPECTED_TYPES.filter(type => !types.includes(type));
  assert(missingTypes.length === 0, 'Missing MBTI type records.', missingTypes);

  const invalidUrls = data.types
    .filter(item => item.namuwikiUrl !== `https://namu.wiki/w/${item.type}`)
    .map(item => ({ type: item.type, namuwikiUrl: item.namuwikiUrl }));
  assert(invalidUrls.length === 0, 'Invalid NamuWiki URL mapping.', invalidUrls);

  const invalidTypeCodes = data.types
    .filter(item => `${item.typeCode.energy}${item.typeCode.perception}${item.typeCode.judgment}${item.typeCode.lifestyle}` !== item.type)
    .map(item => ({ type: item.type, typeCode: item.typeCode }));
  assert(invalidTypeCodes.length === 0, 'typeCode must match the MBTI type string.', invalidTypeCodes);

  const missingPromptKeys = data.types.flatMap(item =>
    PROMPT_REFERENCE_KEYS
      .filter(key => !(key in item.promptReference))
      .map(key => ({ type: item.type, missingKey: key })),
  );
  assert(missingPromptKeys.length === 0, 'Missing promptReference keys.', missingPromptKeys);

  const badPromptArrayFields = data.types.flatMap(item =>
    PROMPT_REFERENCE_KEYS
      .filter(key => key !== 'coreIdentity')
      .filter(key => !Array.isArray(item.promptReference[key]))
      .map(key => ({ type: item.type, key, actualType: typeof item.promptReference[key] })),
  );
  assert(badPromptArrayFields.length === 0, 'Prompt reference fields except coreIdentity must be arrays.', badPromptArrayFields);

  const incompleteSources = data.types
    .filter(item => item.sourceStatus !== 'extracted_from_local_clipping')
    .map(item => ({ type: item.type, sourceStatus: item.sourceStatus }));
  assert(incompleteSources.length === 0, 'All type records must be generated from local Clippings.', incompleteSources);

  const missingClippingRefs = data.types
    .filter(item => !item.clippingPath || !item.clippingPath.endsWith(`${item.type}.md`))
    .map(item => ({ type: item.type, clippingPath: item.clippingPath }));
  assert(missingClippingRefs.length === 0, 'Each type must keep its source clipping path.', missingClippingRefs);

  const incompleteExtracts = data.types.flatMap(item => {
    const errors = [];
    if (!item.promptReference.coreIdentity) errors.push('coreIdentity');
    if (item.functionStack.length !== 4) errors.push('functionStack');
    if (item.promptReference.behaviorCues.length < 5) errors.push('behaviorCues');
    if (item.promptReference.decisionStyle.length < 2) errors.push('decisionStyle');
    if (item.promptReference.promptDo.length < 3) errors.push('promptDo');
    if (item.promptReference.promptDont.length < 3) errors.push('promptDont');
    if (item.promptReference.scenarioRules.length !== 10) errors.push('scenarioRules');
    if (!item.rawExtracts.description.length) errors.push('rawExtracts.description');
    if (!item.rawExtracts.generalCharacteristics.length) errors.push('rawExtracts.generalCharacteristics');
    return errors.map(field => ({ type: item.type, field }));
  });
  assert(incompleteExtracts.length === 0, 'Generated prompt reference has incomplete fields.', incompleteExtracts);

  const completedSources = data.types.filter(item => item.sourceStatus === 'extracted_from_local_clipping').length;

  console.log(
    JSON.stringify(
      {
        ok: true,
        typeRecords: data.types.length,
        scenarioSlots: scenarioSlotIds.length,
        completedSources,
        pendingSources: 0,
        readsReadme: false,
        readsQuizQuestions: false,
      },
      null,
      2,
    ),
  );
}

main();
