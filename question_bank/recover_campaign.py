"""Recover saved overflow candidates before continuing a capped campaign.

The original ledger is never reset: its exposure is deducted from the cap,
then a frozen recovery plan owns one new, version-consistent budget chain.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sqlite3

from dotenv import load_dotenv

from question_bank.cli import _configuration
from question_bank.contracts import Level, RunRequest, canonical_data
from question_bank.engine import EnrichmentEngine
from question_bank.live_export import refresh_export
from question_bank.providers import NativeGeminiAdapter, NativeOpenAIAdapter, ProviderRouter
from question_bank.semantic import FastEmbedAdapter, normalize_question


def build_plan(db, campaign_id, cap, target):
    db.row_factory = sqlite3.Row
    prefix = campaign_id + '-batch-'
    runs = db.execute('SELECT * FROM runs WHERE substr(idempotency_key,1,?)=? ORDER BY rowid',
                      (len(prefix), prefix)).fetchall()
    if not runs:
        raise ValueError('Original campaign not found')
    authorized = {int(r['authorized_microusd']) for r in runs}
    if authorized != {int(cap * 1_000_000)}:
        raise ValueError('Cap must match original campaign authorization')
    exposure = db.execute(
        "SELECT coalesce(sum(CASE WHEN l.state='reconciled' THEN l.actual_microusd "
        "WHEN l.state IN ('active','unknown') THEN l.reserved_microusd ELSE 0 END),0) "
        'FROM ledger_entries l JOIN runs r ON r.run_id=l.run_id '
        'WHERE substr(r.idempotency_key,1,?)=?', (len(prefix), prefix)).fetchone()[0]
    staged = {}
    for row in db.execute("SELECT candidate_id,text FROM candidates WHERE state='staged' ORDER BY rowid"):
        staged.setdefault(normalize_question(row['text']), row['candidate_id'])
    candidates = db.execute(
        'SELECT c.* FROM candidates c JOIN runs r ON r.run_id=c.run_id '
        'WHERE substr(r.idempotency_key,1,?)=? ORDER BY r.rowid,c.ordinal',
        (len(prefix), prefix)).fetchall()
    sources = {}
    for row in candidates:
        text = normalize_question(row['text'])
        if (row['state'] == 'operationally_unresolved'
                and 'pair_overflow' in json.loads(row['reason_codes_json']) and text not in staged):
            sources.setdefault(text, row['candidate_id'])
    remaining = cap - Decimal(exposure) / 1_000_000
    if remaining <= 0:
        raise ValueError('No remaining campaign budget')
    return dict(campaign_id=campaign_id, target=target, original_exposure_usd=str(Decimal(exposure)/1_000_000),
        authorization_usd=str(remaining), source_candidate_ids=list(sources.values()),
        comparison_candidate_ids=list(staged.values()), original_saved_proposals=len(candidates),
        generation_batches=max(0, (target-len(candidates))//20),
        generation_start_index=max(json.loads(r['request_json'])['batch_index'] for r in runs)+1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--target', type=int, required=True)
    parser.add_argument('--cap-usd', type=Decimal, required=True)
    parser.add_argument('--confirm-paid', action='store_true')
    parser.add_argument('--continue-generation', action='store_true')
    args = parser.parse_args()
    if not args.confirm_paid or args.target < 20 or args.target % 20:
        parser.error('Requires --confirm-paid and a target divisible by 20')
    database = args.root / 'question_bank_v2.sqlite3'
    output = args.root / f'{args.campaign_id}_generated_{args.target}_shallow_questions.csv'
    with (args.root / 'campaign.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        load_dotenv(Path.cwd() / '.env')
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as db:
            old = json.loads(db.execute('SELECT payload_json FROM configurations ORDER BY rowid DESC LIMIT 1').fetchone()[0])
            os.environ['QUESTION_BANK_EMBEDDING_CHECKSUM'] = old['embedding_checksum']
            config = _configuration()
            plan_path = args.root / f'{args.campaign_id}_recovery_plan.json'
            if plan_path.exists():
                plan = json.loads(plan_path.read_text())
                if (plan['configuration_id'] != config.manifest_id or plan['target'] != args.target
                        or Decimal(plan['cap_usd']) != args.cap_usd):
                    raise ValueError('Frozen recovery plan does not match requested configuration/cap/target')
            else:
                plan = build_plan(db, args.campaign_id, args.cap_usd, args.target)
                plan.update(configuration_id=config.manifest_id, cap_usd=str(args.cap_usd))
                with plan_path.open('x') as handle:
                    json.dump(plan, handle, indent=2)
        print(json.dumps({'event':'recovery_plan', 'saved_unique_to_reprocess':len(plan['source_candidate_ids']),
            'remaining_authorization_usd':plan['authorization_usd'],
            'original_exposure_usd':plan['original_exposure_usd'],
            'subsequent_generation_batches':plan['generation_batches']}), flush=True)
        engine = EnrichmentEngine(args.root, configuration=config,
            provider=ProviderRouter(openai=NativeOpenAIAdapter(),
                gemini=NativeGeminiAdapter(allow_estimated_total_generated_cap=True)),
            embedder=FastEmbedAdapter(checksum=config.embedding_checksum))
        prior = None
        sources = plan['source_candidate_ids']
        jobs = [('repair', i//20, sources[i:i+20]) for i in range(0,len(sources),20)]
        if args.continue_generation:
            jobs += [('continued', plan['generation_start_index']+i, None)
                     for i in range(plan['generation_batches'])]
        try:
            for kind, index, source_ids in jobs:
                request = RunRequest.production_batch(
                    idempotency_key=f'{args.campaign_id}-{kind}-{index}',
                    snapshot_id=engine.empty_snapshot_id, batch_index=index,
                    authorization_usd=plan['authorization_usd'], attempt_limit=960,
                    uncertainty_review_limit=6, configuration_id=config.manifest_id,
                    levels=(Level.SHALLOW,), comparison_candidate_ids=tuple(plan['comparison_candidate_ids']))
                if source_ids:
                    report = engine.reprocess_candidates(request, tuple(source_ids), prior_run_id=prior)
                else:
                    report = engine.continue_campaign(prior, request) if prior else engine.run(request)
                prior = report.run_id
                exported = refresh_export(database, output, args.campaign_id+'-', None,
                    per_level=args.target, replacement_prefix=args.campaign_id+'-repair-')
                print(json.dumps({'event':'batch_finished','kind':kind,'index':index,'run_id':prior,
                    'status':report.status,'stop_reason':report.stop_reason,'exported':exported,
                    'states':dict(report.metrics.get('candidate_counts',{})),
                    'ledger':canonical_data(report.ledger)}), flush=True)
                # Do not generate replacements while recovery has unfinished checks.
                if (report.status == 'stopped' or report.metrics['candidate_counts'].get('operationally_unresolved',0)
                        or report.stop_reason not in {'batch_complete','no_staged_questions','admission_review'}):
                    print(json.dumps({'event':'recovery_or_campaign_stopped','reason':report.stop_reason}), flush=True)
                    return 2
        finally:
            engine.close()
            refresh_export(database, output, args.campaign_id+'-', None,
                per_level=args.target, replacement_prefix=args.campaign_id+'-repair-')
        print(json.dumps({'event':'recovery_campaign_finished','csv':str(output)}),flush=True)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
