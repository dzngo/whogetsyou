import { workflow, node, trigger, newCredential, expr, ifElse, sticky } from '@n8n/workflow-sdk';

const form = trigger({
  type: 'n8n-nodes-base.formTrigger', version: 2.3,
  config: { name: 'Campaign control form', credentials: { httpBasicAuth: newCredential('Question Bank v3 Operator Basic Auth', 'RhDqaHYrJyNybEEm') }, parameters: {
    authentication: 'basicAuth',
    formTitle: 'Control Question Bank v3 campaign',
    formDescription: 'Status is read-only. Cancel is cooperative. Resume requires new positive spending authorization.',
    formFields: { values: [
      { fieldName: 'campaign_id', fieldLabel: 'Campaign ID', fieldType: 'text', requiredField: true },
      { fieldName: 'action', fieldLabel: 'Action', fieldType: 'dropdown', requiredField: true, fieldOptions: { values: [
        { option: 'status' }, { option: 'cancel' }, { option: 'resume' },
      ] } },
      { fieldName: 'additional_budget_usd', fieldLabel: 'Additional budget USD (resume only)', fieldType: 'number', defaultValue: '0' },
    ] },
    responseMode: 'lastNode',
    options: { path: 'question-bank-v3-control', buttonLabel: 'Apply', appendAttribution: false },
  } },
});

const command = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Apply campaign command', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: 'select result from qb3.campaign_command($1, $2, $3::numeric);',
    options: { queryReplacement: expr("{{ [$('Campaign control form').item.json.campaign_id, $('Campaign control form').item.json.action, $('Campaign control form').item.json.additional_budget_usd || 0] }}"), largeNumbersOutput: 'text' },
  } },
});

const isResume = ifElse({ version: 2.3, config: { name: 'Resume requested?', parameters: { conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' }, combinator: 'and', conditions: [
    { leftValue: expr("{{ $('Campaign control form').item.json.action }}"), rightValue: 'resume', operator: { type: 'string', operation: 'equals' } },
  ],
} } } });

const worker = node({
  type: 'n8n-nodes-base.executeWorkflow', version: 1.3,
  config: { name: 'Start a new worker execution', parameters: {
    mode: 'once', source: 'database', workflowId: { __rl: true, mode: 'id', value: 'Tn2Waxk1Btu6i4LO' },
    workflowInputs: { mappingMode: 'defineBelow', value: {
      campaign_id: expr("{{ $('Campaign control form').item.json.campaign_id }}"),
    }, matchingColumns: [], schema: [
      { id: 'campaign_id', displayName: 'campaign_id', type: 'string' },
    ], attemptToConvertTypes: false, convertFieldsToString: true }, options: { waitForSubWorkflow: false },
  } },
});

const note = sticky('## Durable controls\nStatus never invokes a provider. Cancel is cooperative. Resume first records a new positive budget authorization, then launches a fresh worker execution from PostgreSQL state. Internal continuation remains an orchestration detail and is not exposed as an operator action.', [form, command, isResume, worker], { color: 5 });

export default workflow('qb3-control-campaign', 'Control Question Bank campaign')
  .add(form).to(command).to(isResume.onTrue(worker))
  .add(note);
