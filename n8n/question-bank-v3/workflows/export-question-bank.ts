import { workflow, node, trigger, newCredential, expr } from '@n8n/workflow-sdk';

const form = trigger({
  type: 'n8n-nodes-base.formTrigger', version: 2.3,
  config: { name: 'Export filters', credentials: { httpBasicAuth: newCredential('Question Bank v3 Operator Basic Auth', 'RhDqaHYrJyNybEEm') }, parameters: {
    authentication: 'basicAuth',
    formTitle: 'Export Question Bank v3',
    formDescription: 'Export accepted questions or campaign candidates. Leave text filters blank to include all.',
    formFields: { values: [
      { fieldName: 'dataset', fieldLabel: 'Dataset', fieldType: 'dropdown', requiredField: true, fieldOptions: { values: [{ option: 'accepted' }, { option: 'candidates' }] } },
      { fieldName: 'level', fieldLabel: 'Level', fieldType: 'dropdown', fieldOptions: { values: [{ option: 'all' }, { option: 'shallow' }, { option: 'deep' }] }, defaultValue: 'all' },
      { fieldName: 'theme', fieldLabel: 'Theme code (accepted only)', fieldType: 'text' },
      { fieldName: 'state', fieldLabel: 'Candidate state', fieldType: 'text' },
      { fieldName: 'campaign_id', fieldLabel: 'Campaign ID', fieldType: 'text' },
    ] },
    responseMode: 'lastNode',
    options: { path: 'question-bank-v3-export', buttonLabel: 'Download CSV', appendAttribution: false },
  } },
});

const selectRows = node({
  type: 'n8n-nodes-base.postgres', version: 2.7,
  config: { name: 'Select authoritative rows', credentials: { postgres: newCredential('Question Bank v3 Postgres', 'h3ZyIgobxf9KpDG3') }, parameters: {
    operation: 'executeQuery',
    query: `select q.question_id::text as record_id, q.question_text, q.level,
      'accepted'::text as state, c.campaign_id,
      coalesce(string_agg(distinct qt.theme_code, ',' order by qt.theme_code), '') as themes,
      q.accepted_at as created_at
    from qb3.ready_questions q
    join qb3.candidates c using (candidate_id)
    left join qb3.question_themes qt using (question_id)
    where $1 = 'accepted'
      and ($2 = 'all' or q.level = $2)
      and ($3 = '' or exists (
        select 1 from qb3.question_themes fqt
        where fqt.question_id = q.question_id and fqt.theme_code = $3
      ))
      and ($5 = '' or c.campaign_id = $5)
    group by q.question_id, q.question_text, q.level, c.campaign_id, q.accepted_at
    union all
    select c.candidate_id::text, c.question_text, c.level, c.state,
      c.campaign_id, ''::text, c.created_at
    from qb3.candidates c
    where $1 = 'candidates'
      and ($2 = 'all' or c.level = $2)
      and ($4 = '' or c.state = $4)
      and ($5 = '' or c.campaign_id = $5)
    order by created_at;`,
    options: { queryReplacement: expr("{{ [($('Export filters').item.json.dataset || $('Export filters').item.json['Dataset']), ($('Export filters').item.json.level || $('Export filters').item.json['Level'] || 'all'), ($('Export filters').item.json.theme || $('Export filters').item.json['Theme code (accepted only)'] || ''), ($('Export filters').item.json.state || $('Export filters').item.json['Candidate state'] || ''), ($('Export filters').item.json.campaign_id || $('Export filters').item.json['Campaign ID'] || '')] }}") },
  } },
});

const csv = node({
  type: 'n8n-nodes-base.convertToFile', version: 1.1,
  config: { name: 'Create CSV', parameters: {
    operation: 'csv', binaryPropertyName: 'data',
    options: { fileName: expr("{{ 'question-bank-v3-' + ($('Export filters').item.json.dataset || $('Export filters').item.json['Dataset']) + '.csv' }}"), headerRow: true },
  } },
});

export default workflow('qb3-export-question-bank', 'Export Question Bank').add(form.to(selectRows).to(csv));
