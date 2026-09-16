import { workflow, node, trigger, newCredential, expr, merge } from '@n8n/workflow-sdk';

const input = trigger({
  type: 'n8n-nodes-base.executeWorkflowTrigger', version: 1.2,
  config: { name: 'Campaign input', parameters: { inputSource: 'workflowInputs', workflowInputs: { values: [
    { name: 'campaign_id', type: 'string' },
    { name: 'campaign_name', type: 'string' },
    { name: 'accepted_target', type: 'number' },
    { name: 'level_mode', type: 'string' },
    { name: 'authorized_budget_usd', type: 'number' },
    { name: 'notes', type: 'string' },
    { name: 'raw_input', type: 'object' },
  ] } } },
});

const prompts = node({
  type: 'n8n-nodes-base.dataTable', version: 1.1,
  config: { name: 'Read active prompt registry', parameters: {
    resource: 'row', operation: 'get',
    dataTableId: { __rl: true, mode: 'id', value: '90OyDDiirMaktgSm', cachedResultName: 'Question Bank v3 Prompt Registry' },
    matchType: 'allConditions', filters: { conditions: [{ keyName: 'status', condition: 'eq', keyValue: 'active' }] },
    returnAll: true,
  } },
});

const aggregatePrompts = node({
  type: 'n8n-nodes-base.aggregate', version: 1,
  config: { name: 'Freeze prompt rows', parameters: {
    aggregate: 'aggregateAllItemData', destinationFieldName: 'prompts', include: 'allFields',
    options: { includeBinaries: false },
  } },
});

const runtimes = node({
  type: 'n8n-nodes-base.dataTable', version: 1.1,
  config: { name: 'Read active runtime registry', parameters: {
    resource: 'row', operation: 'get',
    dataTableId: { __rl: true, mode: 'id', value: 'OYXu6ScEyx3IDULQ', cachedResultName: 'Question Bank v3 Runtime Registry' },
    matchType: 'allConditions', filters: { conditions: [{ keyName: 'status', condition: 'eq', keyValue: 'active' }] },
    returnAll: true,
  } },
});

const aggregateRuntimes = node({
  type: 'n8n-nodes-base.aggregate', version: 1,
  config: { name: 'Freeze runtime rows', parameters: {
    aggregate: 'aggregateAllItemData', destinationFieldName: 'runtimes', include: 'allFields',
    options: { includeBinaries: false },
  } },
});

const registries = merge({
  version: 3.2,
  config: { name: 'Combine frozen registries', parameters: {
    mode: 'combine', combineBy: 'combineByPosition', numberInputs: 2,
    options: { includeUnpaired: false },
  } },
});

const initialize = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Create campaign with immutable configuration', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select * from qb3.initialize_campaign($1, $2, $3::jsonb, $4, $5::integer, $6::numeric, $7::jsonb, 100, nullif($8, \'\'));',
    options: { queryReplacement: expr("{{ [$('Campaign input').item.json.campaign_id, $('Campaign input').item.json.campaign_name, JSON.stringify($('Campaign input').item.json.raw_input), $('Campaign input').item.json.level_mode, $('Campaign input').item.json.accepted_target, $('Campaign input').item.json.authorized_budget_usd, JSON.stringify({ prompts: $('Combine frozen registries').item.json.prompts, configuration: { runtimes: $('Combine frozen registries').item.json.runtimes } }), $('Campaign input').item.json.notes || ''] }}"), largeNumbersOutput: 'text' },
  } },
});

export default workflow('qb3-initialize-campaign', 'Initialize Question Bank campaign')
  .add(input.to(prompts.to(aggregatePrompts).to(registries.input(0))))
  .add(input.to(runtimes.to(aggregateRuntimes).to(registries.input(1))))
  .add(registries.to(initialize));
