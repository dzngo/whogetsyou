import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger',
  version: 1.2,
  config: {
    name: 'Input',
    parameters: {
      inputSource: 'workflowInputs',
      workflowInputs: {
        values: [
          { name: 'attempt_id', type: 'string' },
          { name: 'campaign_id', type: 'string' },
          { name: 'batch_id', type: 'string' },
          { name: 'candidate_id', type: 'string' },
          { name: 'parent_attempt_id', type: 'string' },
          { name: 'agent_role', type: 'string' },
          { name: 'provider', type: 'string' },
          { name: 'requested_model', type: 'string' },
          { name: 'reasoning_setting', type: 'string' },
          { name: 'reservation_usd', type: 'number' },
        ],
      },
    },
    output: [{
      attempt_id: 'campaign:1:creative:1',
      campaign_id: 'campaign',
      batch_id: '',
      candidate_id: '',
      parent_attempt_id: '',
      agent_role: 'creative',
      provider: 'gemini',
      requested_model: 'models/gemini-flash-lite',
      reasoning_setting: 'high',
      reservation_usd: 0.01,
    }],
  },
});

const reserve = node({
  type: 'n8n-nodes-base.postgres',
  version: 2.7,
  config: {
    name: 'Reserve in PostgreSQL',
    parameters: {
      operation: 'executeQuery',
      query: "select * from qb3.reserve_provider_budget($1, $2, nullif($3, '')::uuid, nullif($4, '')::uuid, nullif($5, ''), $6, $7, $8, $9, $10::numeric);",
      options: {
        queryReplacement: expr("{{ [$('Input').item.json.attempt_id, $('Input').item.json.campaign_id, $('Input').item.json.batch_id || '', $('Input').item.json.candidate_id || '', $('Input').item.json.parent_attempt_id || '', $('Input').item.json.agent_role, $('Input').item.json.provider, $('Input').item.json.requested_model, $('Input').item.json.reasoning_setting, $('Input').item.json.reservation_usd] }}"),
        largeNumbersOutput: 'text',
      },
    },
    credentials: { postgres: newCredential('Question Bank v3 Postgres') },
    output: [{ reserved: true, reason: 'reserved', remaining_usd: '5.990000' }],
  },
});

const result = node({
  type: 'n8n-nodes-base.set',
  version: 3.5,
  config: {
    name: 'Return reservation',
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: {
        assignments: [
          { id: 'reserved', name: 'reserved', value: expr("{{ $('Reserve in PostgreSQL').item.json.reserved }}"), type: 'boolean' },
          { id: 'reason', name: 'reason', value: expr("{{ $('Reserve in PostgreSQL').item.json.reason }}"), type: 'string' },
          { id: 'remaining-usd', name: 'remaining_usd', value: expr("{{ $('Reserve in PostgreSQL').item.json.remaining_usd }}"), type: 'string' },
        ],
      },
    },
    output: [{ reserved: true, reason: 'reserved', remaining_usd: '5.990000' }],
  },
});

export default workflow('qb3-reserve-provider-budget', 'Reserve provider budget')
  .add(input)
  .to(reserve)
  .to(result);
