import { workflow, node, trigger, newCredential, expr, ifElse } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Agent input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'attempt_id', type: 'string' }, { name: 'parent_attempt_id', type: 'string' },
    { name: 'invocation_id', type: 'string' }, { name: 'campaign_id', type: 'string' },
    { name: 'batch_id', type: 'string' }, { name: 'candidate_id', type: 'string' },
    { name: 'mission_id', type: 'string' }, { name: 'agent_role', type: 'string' },
    { name: 'prompt_key', type: 'string' }, { name: 'prompt_version', type: 'string' },
    { name: 'rendered_prompt', type: 'string' }, { name: 'output_schema', type: 'object' },
    { name: 'model_id', type: 'string' }, { name: 'reasoning_setting', type: 'string' },
    { name: 'reservation_usd', type: 'number' },
    { name: 'input_cost_per_million_usd', type: 'number' }, { name: 'output_cost_per_million_usd', type: 'number' },
    { name: 'repair_of_invocation_id', type: 'string' },
    { name: 'work_group_id', type: 'string' },
  ] } } },
});

const reserve = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reserve this OpenAI attempt', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O4Sfd0diGAB53tsL' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"), campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"), candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.parent_attempt_id || '' }}"), agent_role: expr("{{ $('Agent input').item.json.agent_role }}"),
      provider: 'openai', requested_model: expr("{{ $('Agent input').item.json.model_id }}"),
      reasoning_setting: expr("{{ $('Agent input').item.json.reasoning_setting }}"), reservation_usd: expr("{{ $('Agent input').item.json.reservation_usd }}"),
      work_group_id: expr("{{ $('Agent input').item.json.work_group_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'provider', displayName: 'provider', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'requested_model', displayName: 'requested_model', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reasoning_setting', displayName: 'reasoning_setting', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reservation_usd', displayName: 'reservation_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'work_group_id', displayName: 'work_group_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const reserved = ifElse({ version: 2.3, config: { name: 'Reservation succeeded?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Reserve this OpenAI attempt').item.json.reserved }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ] },
} } });

const existingReconciled = ifElse({ version: 2.3, config: { name: 'Existing traced attempt?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Reserve this OpenAI attempt').item.json.status || '' }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const returnCached = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return cached OpenAI attempt', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'cached-status', name: 'status', type: 'string', value: expr("{{ $('Reserve this OpenAI attempt').item.json.structured_response?.transport_status || $('Reserve this OpenAI attempt').item.json.status }}") },
    { id: 'cached-invocation', name: 'invocation_id', type: 'string', value: expr("{{ $('Reserve this OpenAI attempt').item.json.invocation_id || '' }}") },
    { id: 'cached-attempt', name: 'attempt_id', type: 'string', value: expr("{{ $('Reserve this OpenAI attempt').item.json.attempt_id || $('Agent input').item.json.attempt_id }}") },
    { id: 'cached-raw', name: 'raw_response', type: 'string', value: expr("{{ $('Reserve this OpenAI attempt').item.json.raw_response || '' }}") },
    { id: 'cached-structured', name: 'structured_response', type: 'object', value: expr("{{ $('Reserve this OpenAI attempt').item.json.structured_response || {} }}") },
    { id: 'cached-repair', name: 'repair_of_invocation_id', type: 'string', value: expr("{{ $('Reserve this OpenAI attempt').item.json.repair_of_invocation_id || '' }}") },
  ] } } },
});

const stopDuplicateWorker = node({
  type: 'n8n-nodes-base.filter', version: 2.3,
  config: { name: 'Stop duplicate worker while lease is active', parameters: { conditions: {
    options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 }, combinator: 'and', conditions: [
      { leftValue: expr("{{ $('Return cached OpenAI attempt').item.json.status || '' }}"), rightValue: 'in_flight', operator: { type: 'string', operation: 'notEquals' } },
    ],
  } } },
});

const markSending = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Mark OpenAI request as possibly sent', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select qb3.mark_provider_attempt_sending($1) as marked;',
    options: { queryReplacement: expr("{{ [$('Agent input').item.json.attempt_id] }}") },
  } },
});

const openai = node({
  type: '@n8n/n8n-nodes-langchain.openAi', version: 2.3,
  config: { name: 'OpenAI role agent — paid', onError: 'continueRegularOutput', credentials: { openAiApi: newCredential('Question Bank v3 OpenAI', 'EtyHRCKzh3b0xyy0') }, parameters: {
    resource: 'text', operation: 'response', modelId: { __rl: true, mode: 'id', value: expr("{{ $('Agent input').item.json.model_id }}") },
    responses: { values: [{ type: 'text', role: 'user', content: expr("{{ $('Agent input').item.json.rendered_prompt }}") }] },
    simplify: false, builtInTools: {}, store: false,
    options: {
      maxTokens: 4096, serviceTier: 'default', parallelToolCalls: false, maxToolsIterations: 1,
      reasoning: { reasoningOptions: { effort: expr("{{ $('Agent input').item.json.reasoning_setting }}"), summary: 'none' } },
      textFormat: { textOptions: { type: 'json_schema', name: 'question_bank_agent_output', schema: expr("{{ JSON.stringify($('Agent input').item.json.output_schema) }}"), strict: true, verbosity: 'low' } },
    },
  } },
});

const succeeded = ifElse({ version: 2.3, config: { name: 'OpenAI returned output?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($('OpenAI role agent — paid').item.json.output?.length || $('OpenAI role agent — paid').item.json.output_text?.length || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const hasStatus = ifElse({ version: 2.3, config: { name: 'Provider returned HTTP status?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ String($('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode || '') }}"), rightValue: '', operator: { type: 'string', operation: 'notEmpty', singleValue: true } },
  ] },
} } });

const reconcile = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Reconcile OpenAI usage', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'O2721VLonNSui2TW' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      actual_cost_usd: expr("{{ ((($('OpenAI role agent — paid').item.json.usage?.input_tokens || 0) * $('Agent input').item.json.input_cost_per_million_usd) + (($('OpenAI role agent — paid').item.json.usage?.output_tokens || 0) * $('Agent input').item.json.output_cost_per_million_usd)) / 1000000 }}"),
      reported_model: expr("{{ $('OpenAI role agent — paid').item.json.model || $('Agent input').item.json.model_id }}"),
      usage: expr("{{ $('OpenAI role agent — paid').item.json.usage || {} }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'actual_cost_usd', displayName: 'actual_cost_usd', type: 'number', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'reported_model', displayName: 'reported_model', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'usage', displayName: 'usage', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const parseAndValidate = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Parse and validate structured output', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'parse-result', name: 'parse_result', type: 'object', value: expr(`{{ (() => {
      const response = $('OpenAI role agent — paid').item.json;
      const raw = response.output_text || response.output?.flatMap(item => item.content || []).find(content => content.type === 'output_text')?.text || '';
      try {
        const value = typeof raw === 'string' ? JSON.parse(raw) : raw;
        const schema = $('Agent input').item.json.output_schema || {};
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
          if (rule.required?.some(key => !(key in candidate))) return false;
          if (rule.additionalProperties === false && rule.properties && Object.keys(candidate).some(key => !(key in rule.properties))) return false;
          if (rule.properties && !Object.entries(rule.properties).every(([key, child]) => !(key in candidate) || valid(candidate[key], child))) return false;
          if (rule.items && Array.isArray(candidate) && !candidate.every(item => valid(item, rule.items))) return false;
          return true;
        };
        return valid(value, schema)
          ? { ok: true, value, raw_text: typeof raw === 'string' ? raw : JSON.stringify(raw), error: '' }
          : { ok: false, value: {}, raw_text: typeof raw === 'string' ? raw : JSON.stringify(raw), error: 'json_schema_mismatch' };
      } catch (error) {
        return { ok: false, value: {}, raw_text: typeof raw === 'string' ? raw : JSON.stringify(raw), error: String(error?.message || error) };
      }
    })() }}`) },
  ] } } },
});

const schemaValid = ifElse({ version: 2.3, config: { name: 'Structured output matches schema?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Parse and validate structured output').item.json.parse_result.ok }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ],
} } } });

const persist = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist prompt and output', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 't7YcO0u9cCMxETbS' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"), attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"), mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Agent input').item.json.agent_role }}"), prompt_key: expr("{{ $('Agent input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Agent input').item.json.prompt_version }}"), rendered_prompt: expr("{{ $('Agent input').item.json.rendered_prompt }}"),
      raw_response: expr("{{ JSON.stringify($('OpenAI role agent — paid').item.json) }}"),
      structured_response: expr("{{ $('Parse and validate structured output').item.json.parse_result.value }}"),
      status: 'succeeded', repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'raw_response', displayName: 'raw_response', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'structured_response', displayName: 'structured_response', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'status', displayName: 'status', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const persistSchemaFailure = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist schema failure', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 't7YcO0u9cCMxETbS' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"), attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"), batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"), mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      agent_role: expr("{{ $('Agent input').item.json.agent_role }}"), prompt_key: expr("{{ $('Agent input').item.json.prompt_key }}"),
      prompt_version: expr("{{ $('Agent input').item.json.prompt_version }}"), rendered_prompt: expr("{{ $('Agent input').item.json.rendered_prompt }}"),
      raw_response: expr("{{ JSON.stringify($('OpenAI role agent — paid').item.json) }}"), structured_response: {},
      status: 'schema_failed', repair_of_invocation_id: expr("{{ $('Agent input').item.json.repair_of_invocation_id || '' }}"),
    }, matchingColumns: [], schema: [
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'agent_role', displayName: 'agent_role', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_key', displayName: 'prompt_key', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'prompt_version', displayName: 'prompt_version', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'rendered_prompt', displayName: 'rendered_prompt', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'raw_response', displayName: 'raw_response', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'structured_response', displayName: 'structured_response', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'status', displayName: 'status', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const repairAllowed = ifElse({ version: 2.3, config: { name: 'Repair attempt allowed?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Agent input').item.json.agent_role }}"), rightValue: 'structured_output_repair', operator: { type: 'string', operation: 'notEquals' } },
  ],
} } } });

const repairMalformedOutput = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Repair malformed structured output', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: '2urITibrmjZ4fQwh' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Agent input').item.json.campaign_id }}"),
      batch_id: expr("{{ $('Agent input').item.json.batch_id || '' }}"),
      candidate_id: expr("{{ $('Agent input').item.json.candidate_id || '' }}"),
      mission_id: expr("{{ $('Agent input').item.json.mission_id || '' }}"),
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id + '-repair' }}"),
      parent_attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      invocation_id: expr("{{ $('Agent input').item.json.invocation_id + '-repair' }}"),
      provider_family: 'openai',
      repair_of_invocation_id: expr("{{ $('Agent input').item.json.invocation_id }}"),
      context: expr("{{ ({ malformed_response: $('Parse and validate structured output').item.json.parse_result.raw_text, validation_error: $('Parse and validate structured output').item.json.parse_result.error, required_output_schema: $('Agent input').item.json.output_schema, original_agent_role: $('Agent input').item.json.agent_role, original_prompt_key: $('Agent input').item.json.prompt_key }) }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'batch_id', displayName: 'batch_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'candidate_id', displayName: 'candidate_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'mission_id', displayName: 'mission_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'parent_attempt_id', displayName: 'parent_attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'invocation_id', displayName: 'invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'context', displayName: 'context', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'provider_family', displayName: 'provider_family', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'repair_of_invocation_id', displayName: 'repair_of_invocation_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const repairFailed = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return unrepairable schema failure', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'operationally_unresolved', type: 'string' },
    { id: 'reason', name: 'reason', value: 'structured_output_repair_failed', type: 'string' },
    { id: 'attempt-id', name: 'attempt_id', value: expr("{{ $('Agent input').item.json.attempt_id }}"), type: 'string' },
  ] } } },
});

const release = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Release confirmed failure reservation', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'z0kaN1S9ci6Ekn1R' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'openai_http_error', status_code: $('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode, message: $('OpenAI role agent — paid').item.json.error?.message || $('OpenAI role agent — paid').item.json.message || 'OpenAI request failed' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const retrySignal = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return explicit retry signal', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'retryable_failure', type: 'string' },
    { id: 'attempt-id', name: 'attempt_id', value: expr("{{ $('Agent input').item.json.attempt_id }}"), type: 'string' },
    { id: 'retry-after', name: 'retry_after_seconds', value: expr("{{ (() => { const response = $('OpenAI role agent — paid').item.json; const headers = response.headers || response.error?.headers || response.error?.response?.headers || {}; const raw = headers['retry-after'] || headers['Retry-After'] || headers.get?.('retry-after'); if (!raw) return 10; const seconds = Number(raw); const parsed = Number.isFinite(seconds) ? seconds : (Date.parse(String(raw)) - Date.now()) / 1000; return Number.isFinite(parsed) ? Math.max(1, Math.min(300, Math.ceil(parsed))) : 10; })() }}"), type: 'number' },
  ] } } },
});

const unknown = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Record ambiguous OpenAI spend', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'DsoqFjpqv1mhOQU8' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      attempt_id: expr("{{ $('Agent input').item.json.attempt_id }}"),
      sanitized_error: expr("{{ { kind: 'openai_ambiguous_transport', message: $('OpenAI role agent — paid').item.json.error?.message || $('OpenAI role agent — paid').item.json.message || 'OpenAI result unknown' } }}"),
    }, matchingColumns: [], schema: [
      { id: 'attempt_id', displayName: 'attempt_id', type: 'string', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
      { id: 'sanitized_error', displayName: 'sanitized_error', type: 'object', required: false, defaultMatch: false, display: true, canBeUsedToMatch: true },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const persistProviderFailure = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Persist failed OpenAI invocation', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.persist_agent_run($1,$2,$3,$4::uuid,$5::uuid,$6::uuid,$7,$8,$9,$10,$11,$12::jsonb,$13,$14);',
    options: { queryReplacement: expr("{{ [$('Agent input').item.json.invocation_id, $('Agent input').item.json.attempt_id, $('Agent input').item.json.campaign_id, $('Agent input').item.json.batch_id || null, $('Agent input').item.json.candidate_id || null, $('Agent input').item.json.mission_id || null, $('Agent input').item.json.agent_role, $('Agent input').item.json.prompt_key, $('Agent input').item.json.prompt_version, $('Agent input').item.json.rendered_prompt, JSON.stringify($('OpenAI role agent — paid').item.json), JSON.stringify({ error: $('OpenAI role agent — paid').item.json.error || $('OpenAI role agent — paid').item.json.message || 'provider_failure', transport_status: !Number($('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode || 0) ? 'unknown_spend' : [408, 409, 425, 429, 500, 502, 503, 504].includes(Number($('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode || 0)) ? 'retryable_failure' : 'configuration_failure' }), 'failed', $('Agent input').item.json.repair_of_invocation_id || null] }}") },
  } },
});

const failedWasDefinite = ifElse({ version: 2.3, config: { name: 'Failed invocation was definite?', parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ [408, 409, 425, 429, 500, 502, 503, 504].includes(Number($('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode || 0)) }}"), rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } },
  ] },
} } });

const failedSignal = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return traced OpenAI failure', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'status', name: 'status', value: 'configuration_failure', type: 'string' },
    { id: 'reason', name: 'reason', value: expr("{{ 'openai_http_' + String($('OpenAI role agent — paid').item.json.statusCode || $('OpenAI role agent — paid').item.json.httpCode || 'other') }}"), type: 'string' },
    { id: 'attempt-id', name: 'attempt_id', value: expr("{{ $('Agent input').item.json.attempt_id }}"), type: 'string' },
  ] } } },
});

export default workflow('qb3-invoke-openai-attempt', 'Invoke OpenAI agent attempt')
  .add(input.to(reserve)
  .to(existingReconciled
    .onTrue(returnCached.to(stopDuplicateWorker))
    .onFalse(reserved.onTrue(markSending.to(openai).to(succeeded
      .onTrue(reconcile.to(parseAndValidate).to(schemaValid
        .onTrue(persist)
        .onFalse(persistSchemaFailure.to(repairAllowed
          .onTrue(repairMalformedOutput)
          .onFalse(repairFailed)))))
      .onFalse(hasStatus
        .onTrue(release.to(persistProviderFailure).to(failedWasDefinite
          .onTrue(retrySignal)
          .onFalse(failedSignal)))
        .onFalse(unknown.to(persistProviderFailure))))))));
