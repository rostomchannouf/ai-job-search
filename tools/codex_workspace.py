#!/usr/bin/env python3
"""Credential-free helpers for the connector-mediated Codex workspace.

All JSON inputs/outputs live outside the checkout. Proposals are NOT writes or
proof of user consent: the executing agent must verify approval in conversation.
"""
import argparse
import hashlib
import html
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

HEADERS = ['Company Name','Application Status','Role','Salary','Date Submitted',
           'Link to Job Request','Location','Working model','Match Score','Rejection Reason','Notes']
WEIGHTS = {'technical':30,'experience':25,'behavioral':15,'career':30}
FINAL = {'Rejected','Ghosted','Job Removed/Deactivated'}
ROOT = Path(__file__).resolve().parent.parent

def norm(value):
    return ' '.join(str(value or '').casefold().split())

def url_key(value):
    p = urlsplit(str(value).strip())
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:
        raise ValueError('Expected a public HTTP(S) posting URL')
    if p.hostname=='linkedin.com' or p.hostname.endswith('.linkedin.com'):
        match=re.search(r'/jobs/view/(?:[^/]*-)?(\d+)/?$',p.path)
        if match: return 'https://www.linkedin.com/jobs/view/'+match.group(1)
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('trk','trackingid','refid')]
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(query)),''))

def eligibility(job):
    country = str(job.get('country','')).upper()
    if country == 'DE' or 'DE' in job.get('remote_countries',[]):
        return 'PASS'
    return 'FAIL' if country else 'FLAG'

def language_gate(language, required, declared):
    if language not in declared:
        return 'FAIL'
    if norm(declared[language]) in ('none','no proficiency','a0',''):
        return 'FAIL' if required else 'PASS'
    levels = ['A1','A2','B1','B2','C1','C2','Native']
    actual = declared[language]
    if required in levels and actual in levels:
        return 'FLAG' if levels.index(required)>levels.index(actual) else 'PASS'
    return 'PASS' if not required or norm(required)==norm(actual) else 'FLAG'

def score(dimensions):
    if any(k not in dimensions or not isinstance(dimensions[k],(float,int)) or isinstance(dimensions[k],bool)
           or not math.isfinite(dimensions[k]) or not 0<=dimensions[k]<=100 for k in WEIGHTS):
        raise ValueError('Four finite dimension scores in 0..100 are required')
    total = sum(Decimal(str(dimensions[k])) * v for k,v in WEIGHTS.items()) / 1000
    return float(total.quantize(Decimal('.1'),rounding=ROUND_HALF_UP))

def records(snapshot):
    values = snapshot.get('values',[])
    if not values or values[0] != HEADERS:
        raise ValueError('Tracker headers changed; inspect and remap before proceeding')
    result=[]
    for number,row in enumerate(values[1:],2):
        if any(str(x).strip() for x in row):
            padded=(row+['']*len(HEADERS))[:len(HEADERS)]
            result.append(dict(zip(HEADERS,padded),_row=number))
    return result

def duplicate(job, rows):
    key=url_key(job['url'])
    possible=False
    for row in rows:
        old=row['Link to Job Request']
        if old:
            try:
                if key==url_key(old): return 'exact'
            except ValueError: pass
        if norm(job['company'])==norm(row['Company Name']) and norm(job['role'])==norm(row['Role']): possible=True
    return 'possible' if possible else 'new'

def fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot['values'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def propose(snapshot,jobs,approved_ids,approval):
    if not approval.strip() or not approved_ids:
        raise ValueError('Explicit user approval of identified entries required')
    fetched=datetime.fromisoformat(snapshot['fetched_at'].replace('Z','+00:00'))
    age=(datetime.now(timezone.utc)-fetched).total_seconds()
    if age < -60 or age > 300: raise ValueError('Refresh the live tracker immediately before proposing writes')
    current=records(snapshot)
    last=max((r['_row'] for r in current),default=1)
    known={j['id'] for j in jobs}
    if len(known)!=len(jobs) or not set(approved_ids)<=known: raise ValueError('Unknown or duplicate job identifiers')
    rows=[]; skipped=[]
    for job in jobs:
        if job['id'] not in approved_ids: continue
        state=duplicate(job,current)
        if state=='exact':
            skipped.append(job['id']); continue
        if state=='possible' and not job.get('distinct_requisition_verified'):
            raise ValueError('Possible historical duplicate: verify a distinct requisition first')
        if eligibility(job)!='PASS': raise ValueError('Germany eligibility must be verified')
        rating=job.get('score','')
        if rating!='' and (not isinstance(rating,(float,int)) or isinstance(rating,bool) or not math.isfinite(rating) or not 0<=rating<=10):
            raise ValueError('Match score must be 0..10')
        if not job.get('company','').strip() or not job.get('role','').strip(): raise ValueError('Company and role required')
        row=[job['company'],'Not Applied',job['role'],job.get('salary',''),'',job['url'],job.get('location',''),job.get('model',''),rating,'',job.get('notes','')]
        rows.append(row)
        current.append(dict(zip(HEADERS,row),_row=0))
    return {'kind':'append_proposal','snapshot_sha256':fingerprint(snapshot),'approval_evidence':approval,
            'start_row':last+1,'rows':rows,'skipped_existing':skipped,
            'instructions':'Re-read live data; rebuild if changed. Write literal cell values only. Preserve validation/formatting. Read back before marking committed.'}

def verify_rows(proposal, actual):
    def clean(row):
        result=[str(x) for x in (row+['']*11)[:11]]
        for column in (3,8):
            try: result[column]=str(Decimal(result[column]).normalize())
            except Exception: pass
        return result
    return [clean(r) for r in proposal['rows']]==[clean(r) for r in actual]

def ready(evidence):
    return all(evidence.get(k) is True for k in ('compile','pages','text','visual','factual','review'))

def email_proposal(message_id,signal,current,processed,match_count):
    if message_id in processed: return None
    if match_count!=1: return {'action':'ambiguous','message_id':message_id}
    if current in FINAL: return {'action':'conflict','message_id':message_id}
    states={'ack':'Submitted (Pending)','assessment':'Answered positively','interview':'Answered positively','offer':'Answered positively','rejection':'Rejected'}
    if signal not in states: return None
    if signal=='ack' and current!='Not Applied': return None
    return {'action':'propose','message_id':message_id,'status':states[signal],'stage':signal,'requires_approval':True}

def report(snapshot, events=()):
    rows=records(snapshot)
    submitted=sum(bool(r['Date Submitted']) for r in rows)
    rendered=''.join('<tr>'+''.join('<td>'+html.escape(str(r[h]))+'</td>' for h in HEADERS)+'</tr>' for r in rows)
    counts=Counter(str(r['Application Status']) or 'Unknown' for r in rows)
    known_urls=set()
    for r in rows:
        try: known_urls.add(url_key(r['Link to Job Request']))
        except ValueError: pass
    stages={'interview':set(),'offer':set()}
    for event in events:
        try: key=url_key(event.get('url',''))
        except ValueError: continue
        if key not in known_urls: continue
        if event.get('stage') in ('assessment','interview','offer','hired'): stages['interview'].add(key)
        if event.get('stage') in ('offer','hired'): stages['offer'].add(key)
    bars=''.join('<p>'+html.escape(status)+f' ({count}) <meter min="0" max="{max(len(rows),1)}" value="{count}"></meter></p>' for status,count in sorted(counts.items()))
    options=''.join('<option>'+html.escape(status)+'</option>' for status in sorted(counts))
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Job search report</title>'
            '<style>body{font:15px system-ui;margin:2rem;color:#17202a}table{border-collapse:collapse;width:100%}th,td{padding:8px;border:1px solid #ddd;text-align:left}tr:nth-child(even){background:#f5f7fa}</style>'
            f'<h1>Job search report</h1><p>Tracked: {len(rows)} · Submitted: {submitted}</p>'
            f'<p>Reached interview: {len(stages["interview"])} · Received offer: {len(stages["offer"])}</p>'+bars+
            '<p>Submitted count uses recorded submission dates. Missing dates and historical interview stages are unknown; no stages are inferred from rejection.</p>'
            '<label>Search <input id="query" oninput="filterRows()"></label> <label>Status <select id="status" onchange="filterRows()"><option value="">All</option>'+options+'</select></label>'
            '<table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in HEADERS)+'</tr></thead><tbody>'+rendered+'</tbody></table>'
            '<script type="text/javascript">function filterRows(){const q=document.getElementById("query").value.toLowerCase(),s=document.getElementById("status").value;document.querySelectorAll("tbody tr").forEach(r=>{r.hidden=!(r.textContent.toLowerCase().includes(q)&&(!s||r.cells[1].textContent===s));});}</script></html>')

def external(path):
    path=Path(path).resolve()
    if path==ROOT or ROOT in path.parents: raise ValueError('Private files must remain outside the public checkout')
    return path

def workspace_path(path, config):
    path=external(path); root=Path(config['paths']['workspace']).resolve()
    if path!=root and root not in path.parents: raise ValueError('Path must stay inside the configured synced workspace')
    return path

def bind_snapshot(snapshot, config):
    for field in ('spreadsheet_id','sheet'):
        if snapshot.get(field)!=config['tracker'][field]: raise ValueError('Tracker snapshot belongs to a different destination')
    return snapshot

def load_config(path):
    config=json.loads(external(path).read_text(encoding='utf-8-sig'))
    if config.get('version')!=1: raise ValueError('Expected configuration version 1')
    for path in config['paths'].values(): workspace_path(path,config)
    return config

def preflight(config):
    checks={}
    for name in ('bun','lualatex','xelatex'):
        executable=config.get('executables',{}).get(name) or shutil.which(name)
        checks[name]=False
        if executable and Path(executable).is_file():
            try:
                checks[name]=subprocess.run([str(executable),'--version'],capture_output=True,timeout=30,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).returncode==0
            except (OSError,subprocess.TimeoutExpired): pass
    for name in ('pypdf','fitz'): checks[name]=importlib.util.find_spec(name) is not None
    for name,path in config['paths'].items(): checks['path:'+name]=Path(path).is_dir()
    checks['profile_snapshots']=all((Path(config['paths']['profile'])/(name+'.md')).is_file() for name in config['sources'])
    return {'local_checks':checks,'local_ok':all(checks.values()),
            'connector_checks':'Agent must live-read Drive, both resumes, tracker metadata and Gmail; local scripts cannot verify connector authentication.',
            'compile_check':'Compile template smoke tests and inspect PDFs separately; executable presence is not compile success.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('preflight')
    r=sub.add_parser('report'); r.add_argument('--snapshot',required=True); r.add_argument('--output',required=True); r.add_argument('--events')
    a=sub.add_parser('propose'); a.add_argument('--snapshot',required=True); a.add_argument('--jobs',required=True); a.add_argument('--approved',nargs='+',required=True); a.add_argument('--approval',required=True); a.add_argument('--output',required=True)
    args=p.parse_args(); config=load_config(args.config)
    if args.command=='preflight':
        result=preflight(config); print(json.dumps(result,indent=2)); return 0 if result['local_ok'] else 1
    snapshot=bind_snapshot(json.loads(workspace_path(args.snapshot,config).read_text(encoding='utf-8-sig')),config)
    if args.command=='report':
        events=json.loads(workspace_path(args.events,config).read_text(encoding='utf-8-sig')) if args.events else []
        content=report(snapshot,events)
    else:
        jobs=json.loads(workspace_path(args.jobs,config).read_text(encoding='utf-8-sig'))
        proposal=propose(snapshot,jobs,args.approved,args.approval)
        proposal['destination']={k:config['tracker'][k] for k in ('spreadsheet_id','sheet')}
        content=json.dumps(proposal,indent=2,ensure_ascii=False)
    output=workspace_path(args.output,config); output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f: f.write(content)
    print(str(output)); return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,KeyError,OSError) as e: print(str(e),file=sys.stderr); sys.exit(1)
