import { workflow, node, trigger, newCredential, expr, sticky } from '@n8n/workflow-sdk';

const form = trigger({
  type: 'n8n-nodes-base.formTrigger', version: 2.4,
  config: { name: 'Launch campaign form', credentials: { httpBasicAuth: newCredential('Question Bank v3 Operator Basic Auth', 'RhDqaHYrJyNybEEm') }, parameters: {
    authentication: 'basicAuth', formTitle: 'Question Bank v3 campaign',
    formDescription: 'Create a new empty-bank generation campaign. A campaign keeps running in internal batches until its accepted target or hard USD budget is reached.',
    formFields: { values: [
      { fieldLabel: 'Campaign name', fieldName: 'campaign_name', fieldType: 'text', requiredField: true },
      { fieldLabel: 'Accepted question target', fieldName: 'accepted_target', fieldType: 'number', defaultValue: '100', requiredField: true },
      { fieldLabel: 'Question level', fieldName: 'level_mode', fieldType: 'dropdown', defaultValue: 'shallow', requiredField: true, fieldOptions: { values: [
        { option: 'shallow' }, { option: 'deep' }, { option: 'mixed' },
      ] } },
      { fieldLabel: 'Hard budget (USD)', fieldName: 'authorized_budget_usd', fieldType: 'number', defaultValue: '6', requiredField: true },
      { fieldLabel: 'Notes', fieldName: 'notes', fieldType: 'textarea', requiredField: false },
    ] },
    responseMode: 'lastNode', options: { appendAttribution: false, buttonLabel: 'Launch campaign', path: 'question-bank-v3-campaign', respondWithOptions: { values: {
      respondWith: 'text', formSubmittedText: expr('Campaign {{ $json.campaign_id }} was saved and its worker was started. Use the Control Question Bank campaign workflow to inspect or cancel it.'),
    } } },
  } },
});

const initialize = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Persist raw input and freeze configuration', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'GUZXXnYfKj3qWY4S' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ 'qb3-' + $execution.id }}"), campaign_name: expr('{{ $json.campaign_name }}'),
      accepted_target: expr('{{ Number($json.accepted_target) }}'), level_mode: expr('{{ $json.level_mode }}'),
      authorized_budget_usd: expr('{{ Number($json.authorized_budget_usd) }}'), notes: expr("{{ $json.notes || '' }}"), raw_input: expr('{{ $json }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' }, { id: 'campaign_name', displayName: 'campaign_name', type: 'string' },
      { id: 'accepted_target', displayName: 'accepted_target', type: 'number' }, { id: 'level_mode', displayName: 'level_mode', type: 'string' },
      { id: 'authorized_budget_usd', displayName: 'authorized_budget_usd', type: 'number' }, { id: 'notes', displayName: 'notes', type: 'string' },
      { id: 'raw_input', displayName: 'raw_input', type: 'object' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: true },
  } },
});

const worker = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Start durable campaign worker', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'Tn2Waxk1Btu6i4LO' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr('{{ $json.campaign_id }}'),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: false },
  } },
});

const accepted = node({
  type: 'n8n-nodes-base.set', version: 3.5,
  config: { name: 'Return launch receipt', parameters: { mode: 'manual', includeOtherFields: false, assignments: { assignments: [
    { id: 'accepted', name: 'accepted', value: true, type: 'boolean' },
    { id: 'campaign', name: 'campaign_id', value: expr("{{ $('Persist raw input and freeze configuration').item.json.campaign_id }}"), type: 'string' },
    { id: 'status', name: 'status', value: 'running', type: 'string' },
  ] } } },
});

const note = sticky('## Operator entry point\nThe raw form response is persisted before any paid call. Prompt and runtime rows are frozen into the campaign snapshot. The long-running worker is then launched asynchronously.', [form, initialize, worker, accepted], { color: 5 });

export default workflow('qb3-run-campaign', 'Run Question Bank campaign')
  .add(form).to(initialize).to(worker).to(accepted)
  .add(note);
