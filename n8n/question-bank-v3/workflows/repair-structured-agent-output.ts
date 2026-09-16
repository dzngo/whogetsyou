import { workflow, node, trigger, expr, switchCase, ifElse } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' }, { name: 'batch_id', type: 'string' },
    { name: 'candidate_id', type: 'string' }, { name: 'mission_id', type: 'string' },
    { name: 'attempt_id', type: 'string' }, { name: 'parent_attempt_id', type: 'string' },
    { name: 'invocation_id', type: 'string' },
    { name: 'context', type: 'object' },
    { name: 'provider_family', type: 'string' },
    { name: 'repair_of_invocation_id', type: 'string' },
  ] } } },
});

const loadPrompt = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Load frozen prompt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'U7PU7ThIM1W90rXb' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), prompt_key: 'repair_structured_output',
    }, matchingColumns: [], schema: [{ id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true }
  } },
});

const route = switchCase({ version: 3.4, config: { name: 'Use original provider family', parameters: {
  mode: 'rules', rules: { values: [
    { outputKey: 'gemini', conditions: { options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: expr("{{ $('Agent input').item.json.provider_family }}"), rightValue: 'gemini', operator: { type: 'string', operation: 'equals' } }] } },
    { outputKey: 'openai', conditions: { options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: expr("{{ $('Agent input').item.json.provider_family }}"), rightValue: 'openai', operator: { type: 'string', operation: 'equals' } }] } },
  ] }, options: { fallbackOutput: 'none' },
} } });

const gemini = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair output — Gemini low', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'YE5oyCWwpnQxVAi1' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.parent_attempt_id }}"),
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"), mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      prompt_version: expr("{{ $('Load frozen prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen prompt').item.json.prompt.template + '\\n\\nCONTEXT:\\n' + JSON.stringify($('Agent input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen prompt').item.json.prompt.outputSchema_object) : $('Load frozen prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].modelId; })() }}"),
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini').reservationUsd }}"),
      input_cost_per_million_usd: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].inputCostPerMillionUsd; })() }}"),
      output_cost_per_million_usd: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_gemini'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].outputCostPerMillionUsd; })() }}"),
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }
  } },
});

const openai = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair output — OpenAI low', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'p6V8CLoucC9GvQCd' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.parent_attempt_id }}"),
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"), mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      prompt_version: expr("{{ $('Load frozen prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen prompt').item.json.prompt.template + '\\n\\nCONTEXT:\\n' + JSON.stringify($('Agent input').item.json.context) }}"),
      output_schema: expr("{{ typeof $('Load frozen prompt').item.json.prompt.outputSchema_object === 'string' ? JSON.parse($('Load frozen prompt').item.json.prompt.outputSchema_object) : $('Load frozen prompt').item.json.prompt.outputSchema_object }}"),
      model_id: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].modelId; })() }}"),
      reservation_usd: expr("{{ $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai').reservationUsd }}"),
      input_cost_per_million_usd: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].inputCostPerMillionUsd; })() }}"),
      output_cost_per_million_usd: expr("{{ (() => { const r = $('Load frozen prompt').item.json.configuration.runtimes.find(x => x.runtimeKey === 'structured_output_repair_openai'); const w = typeof r.modelWaterfall_object === 'string' ? JSON.parse(r.modelWaterfall_object) : r.modelWaterfall_object; return w[0].outputCostPerMillionUsd; })() }}"),
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_schema', displayName: 'output_schema', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'model_id', displayName: 'model_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'input_cost_per_million_usd', displayName: 'input_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'output_cost_per_million_usd', displayName: 'output_cost_per_million_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true }
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true }
  } },
});

const validateOriginalSchema = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Validate repaired original contract', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'validation-result', name: 'validation_result', type: 'object', value: expr(`{{ (() => {
      const response = $json;
      const repaired = response.structured_response?.repaired_output;
      const schema = $('Agent input').item.json.context?.required_output_schema || {};
      const valid = (candidate, rule) => {
        if (!rule || typeof rule !== 'object') return true;
        const types = rule.type ? (Array.isArray(rule.type) ? rule.type : [rule.type]) : [];
        const matchesType = type => type === 'null' ? candidate === null
          : type === 'object' ? candidate !== null && !Array.isArray(candidate) && typeof candidate === 'object'
          : type === 'array' ? Array.isArray(candidate)
          : type === 'integer' ? Number.isInteger(candidate)
          : type === 'number' ? typeof candidate === 'number' && Number.isFinite(candidate)
          : typeof candidate === type;
        if (types.length && !types.some(matchesType)) return false;
        if (rule.enum && !rule.enum.includes(candidate)) return false;
        if (candidate === null) return true;
        if (Array.isArray(candidate) && rule.minItems !== undefined && candidate.length < rule.minItems) return false;
        if (Array.isArray(candidate) && rule.maxItems !== undefined && candidate.length > rule.maxItems) return false;
        if (typeof candidate === 'string' && rule.minLength !== undefined && candidate.length < rule.minLength) return false;
        if (typeof candidate === 'string' && rule.maxLength !== undefined && candidate.length > rule.maxLength) return false;
        if (typeof candidate === 'number' && rule.minimum !== undefined && candidate < rule.minimum) return false;
        if (typeof candidate === 'number' && rule.maximum !== undefined && candidate > rule.maximum) return false;
        if (rule.required?.some(key => candidate === null || typeof candidate !== 'object' || !(key in candidate))) return false;
        if (rule.additionalProperties === false && rule.properties && Object.keys(candidate || {}).some(key => !(key in rule.properties))) return false;
        if (rule.properties && !Object.entries(rule.properties).every(([key, child]) => candidate !== null && typeof candidate === 'object' && (!(key in candidate) || valid(candidate[key], child)))) return false;
        if (rule.items && Array.isArray(candidate) && !candidate.every(item => valid(item, rule.items))) return false;
        return true;
      };
      const ok = response.status === 'succeeded'
        && response.structured_response?.repairable === true
        && repaired !== undefined
        && valid(repaired, schema);
      return {
        ok,
        repaired_output: ok ? repaired : {},
        invocation_id: response.invocation_id || '',
        raw_response: response.raw_response || JSON.stringify(response),
        repair_envelope: response.structured_response || {},
        reason: ok ? '' : (response.structured_response?.error || response.reason || 'structured_output_repair_schema_mismatch'),
      };
    })() }}`) },
  ] } } },
});

const repairedValid = ifElse({ version: 2.3, config: { name: 'Repaired output matches original schema?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Validate repaired original contract').item.json.validation_result.ok }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const returnRepair = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return validated repair', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'succeeded', type: 'string' },
    { id: 'structured-response', name: 'structured_response', value: expr("{{ $('Validate repaired original contract').item.json.validation_result.repaired_output }}"), type: 'object' },
    { id: 'invocation-id', name: 'invocation_id', value: expr("{{ $('Validate repaired original contract').item.json.validation_result.invocation_id }}"), type: 'string' },
    { id: 'reason', name: 'reason', value: '', type: 'string' },
  ] } } },
});

const persistValidRepair = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist validated repair outcome', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 't7YcO0u9cCMxETbS' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      invocation_id: expr("{{ $('Validate repaired original contract').item.json.validation_result.invocation_id }}"),
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      prompt_version: expr("{{ $('Load frozen prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen prompt').item.json.prompt.template + '\\n\\nCONTEXT:\\n' + JSON.stringify($('Agent input').item.json.context) }}"),
      raw_response: expr("{{ $('Validate repaired original contract').item.json.validation_result.raw_response }}"),
      structured_response: expr("{{ ({ ...$('Validate repaired original contract').item.json.validation_result.repair_envelope, original_schema_validated: true }) }}"),
      status: 'succeeded',
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string' }, { id: 'attempt_id', displayName: 'attempt_id', type: 'string' },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'agent_role', displayName: 'agent_role', type: 'string' }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string' },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string' }, { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string' },
      { id: 'raw_response', displayName: 'raw_response', type: 'string' }, { id: 'structured_response', displayName: 'structured_response', type: 'object' },
      { id: 'status', displayName: 'status', type: 'string' }, { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const persistInvalidRepair = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist invalid repair outcome', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 't7YcO0u9cCMxETbS' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      invocation_id: expr("{{ $('Validate repaired original contract').item.json.validation_result.invocation_id }}"),
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: 'structured_output_repair', prompt_key: 'repair_structured_output',
      prompt_version: expr("{{ $('Load frozen prompt').item.json.prompt.version }}"),
      rendered_prompt: expr("{{ $('Load frozen prompt').item.json.prompt.template + '\\n\\nCONTEXT:\\n' + JSON.stringify($('Agent input').item.json.context) }}"),
      raw_response: expr("{{ $('Validate repaired original contract').item.json.validation_result.raw_response }}"),
      structured_response: expr("{{ $('Validate repaired original contract').item.json.validation_result.repair_envelope }}"),
      status: 'schema_failed',
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string' }, { id: 'attempt_id', displayName: 'attempt_id', type: 'string' },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'batch_id', displayName: 'batch_id', type: 'string' },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string' }, { id: 'mission_id', displayName: 'mission_id', type: 'string' },
      { id: 'agent_role', displayName: 'agent_role', type: 'string' }, { id: 'prompt_key', displayName: 'prompt_key', type: 'string' },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string' }, { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string' },
      { id: 'raw_response', displayName: 'raw_response', type: 'string' }, { id: 'structured_response', displayName: 'structured_response', type: 'object' },
      { id: 'status', displayName: 'status', type: 'string' }, { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true },
    options: { waitForSubWorkflow: true },
  } },
});

const returnUnresolved = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return repair schema mismatch', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'operationally_unresolved', type: 'string' },
    { id: 'structured-response', name: 'structured_response', value: expr('{{ ({}) }}'), type: 'object' },
    { id: 'invocation-id', name: 'invocation_id', value: expr("{{ $('Validate repaired original contract').item.json.validation_result.invocation_id }}"), type: 'string' },
    { id: 'reason', name: 'reason', value: expr("{{ $('Validate repaired original contract').item.json.validation_result.reason }}"), type: 'string' },
  ] } } },
});

export default workflow('qb3-repair-structured-output', 'Repair structured agent output')
  .add(input).to(loadPrompt).to(route
    .onCase(0, gemini.to(validateOriginalSchema))
    .onCase(1, openai.to(validateOriginalSchema))
  )
  .add(validateOriginalSchema).to(repairedValid
    .onTrue(persistValidRepair.to(returnRepair))
    .onFalse(persistInvalidRepair.to(returnUnresolved)));
