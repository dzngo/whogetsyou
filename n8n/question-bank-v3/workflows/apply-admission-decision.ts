import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'candidate_id', type: 'string' },
    { name: 'decision', type: 'string' },
    { name: 'reason_codes', type: 'array' },
    { name: 'feedback_note', type: 'string' },
    { name: 'stage_result', type: 'object' },
  ] } } },
});

const query = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply decision transaction', credentials: { postgres: newCredential('Question Bank v3 Postgres') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.apply_candidate_decision($1::uuid, $2, $3::jsonb, $4, $5::jsonb);',
    options: { queryReplacement: expr("{{ [$('Input').item.json.candidate_id, $('Input').item.json.decision, JSON.stringify($('Input').item.json.reason_codes || []), $('Input').item.json.feedback_note || '', JSON.stringify($('Input').item.json.stage_result || {})] }}") },
  } },
});

export default workflow('qb3-apply-admission-decision', 'Apply admission decision').add(input).to(query);
