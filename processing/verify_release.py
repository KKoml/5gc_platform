#!/usr/bin/env python3
"""Read-only release checks; never imports or executes the platform programs."""
from pathlib import Path
import ast,csv,datetime,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def rows(p):
 with (ROOT/p).open(newline='') as f:return list(csv.DictReader(f))
def main():
 checks=[]
 def check(name,ok,detail=None):checks.append({'check':name,'passed':bool(ok),'detail':detail})
 expected={}
 for line in (ROOT/'SHA256SUMS.txt').read_text().splitlines():
  h,rel=line.split('  ',1);expected[rel]=h
 errors=[p for p,h in expected.items() if not (ROOT/p).is_file() or digest(ROOT/p)!=h]
 check('publication_sha256',not errors,{'files':len(expected),'mismatches':errors})
 files=[p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts]
 unlisted=[str(p.relative_to(ROOT)) for p in files if str(p.relative_to(ROOT)) not in expected and p.name not in {'SHA256SUMS.txt','CHECK_RESULTS.md','LOCAL_VALIDATION.json'}]
 check('manifest_file_scope',not unlisted,unlisted)
 py=[];sh=[];go=[];jsonerrors=[];csvbad=[];identity=[];secrets=[];oversized=[];links=[]
 sensitive=re.compile('|'.join([re.escape('/home/'+'f'+'nic'), re.escape('f'+'nic@'), re.escape('f'+'nic-Precision'), re.escape('f'+'nic-precision'), r'192\.168\.'+'161',r'10\.'+'29'+r'\.',re.escape('imsi-'+'208'+'93'), 'K'+'Koml','Ohayou-'+'630']))
 secret=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bghp_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}|\bAKIA[A-Z0-9]{16}')
 for p in files:
  rel=str(p.relative_to(ROOT))
  if p.stat().st_size>50*1024**2:oversized.append(rel)
  s=p.read_text(errors='replace')
  if sensitive.search(s):identity.append(rel)
  if secret.search(s) or re.search(r'AUTH_(?:KEY|OPC)\s*=\s*[\"\'][0-9a-fA-F]{32}[\"\']',s):secrets.append(rel)
  if p.suffix=='.py':
   try:ast.parse(s,filename=rel)
   except SyntaxError as e:py.append(f'{rel}:{e.lineno}:{e.msg}')
  if p.suffix=='.go':
   r=subprocess.run(['gofmt','-e',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
   if r.returncode:go.append(rel+':'+r.stderr)
  if p.suffix=='.sh':
   r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
   if r.returncode:sh.append(rel+':'+r.stderr)
  if p.suffix in {'.json','.jsonl'}:
   try:
    if p.suffix=='.json':json.loads(s)
    else:
     for line in s.splitlines():
      if line.strip():json.loads(line)
   except ValueError as e:jsonerrors.append(rel+':'+str(e))
  if p.suffix=='.csv':
   with p.open(newline='') as f:
    rd=csv.reader(f);head=next(rd,[])
    for i,row in enumerate(rd,2):
     if len(row)!=len(head):csvbad.append(f'{rel}:{i}')
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',s):
    if not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',target) and not (p.parent/target.split('#')[0]).exists():links.append(f'{rel}:{target}')
 check('go_parser_syntax',not go,go);check('python_ast_syntax',not py,py);check('bash_static_syntax',not sh,sh)
 check('json_jsonl_parse',not jsonerrors,jsonerrors);check('csv_row_width',not csvbad,csvbad)
 check('anonymous_site_identity_scan',not identity,identity);check('private_key_token_scan',not secrets,secrets)
 check('git_file_size_under_50MiB',not oversized,oversized);check('markdown_local_links',not links,links)
 d=rows('dictionaries/PLATFORM_FIELDS.csv');check('dictionary_scope_400_215',len(d)==400 and sum(x['field_role']=='metric' for x in d)==215)
 b=rows('dictionaries/BASE_TABLE_81.csv');check('base_dictionary_81_unique',len(b)==81 and len({x['field_name'] for x in b})==81)
 ledger=rows('tables/RUN_LEDGER.csv');check('seven_base_runs_611777_rows',len(ledger)==7 and sum(int(x['rows']) for x in ledger)==611777 and all(int(x['columns'])==81 and int(x['grid_gaps'])==0 for x in ledger))
 coverage=rows('tables/FIELD_COVERAGE.csv');check('coverage_metadata_matches_observed_cells',len(coverage)==567 and all(abs(float(x['coverage_ratio_recorded'])-float(x['coverage_ratio_recomputed']))<=0.00000051 for x in coverage))
 plan=json.loads((ROOT/'samples/W1-D06/config/runtime/fault-plan.json').read_text());ex=json.loads((ROOT/'samples/W1-D06/report/fault_timeline_execution.json').read_text());ids={x['fault_id'] for x in plan['faults']}
 check('sample_plan_execution_identity',len(ids)==144 and len(ex['results'])==288 and all(x['fault_id'] in ids and x['returncode']==0 for x in ex['results']))
 cp=[]
 for line in (ROOT/'samples/W1-D06/events/recovery_checkpoints.jsonl').read_text().splitlines():cp.append(json.loads(line))
 groups={x['overlap_group'] for x in plan['faults']}
 check('72_accepted_checkpoints_same_run_and_groups',len(cp)==72 and all(x['accepted'] and x['run_id']=='W1-D06' and x['overlap_group'] in groups for x in cp))
 sample=rows('samples/W1-D06/report/v3_timeseries.csv');ts=[datetime.datetime.fromisoformat(x['time']).timestamp() for x in sample]
 check('base_sample_81_columns_contiguous_real_grid',len(sample)>0 and all(len(x)==81 and x['run_id']=='W1-D06' for x in sample) and all(b-a==1 for a,b in zip(ts,ts[1:])),{'rows':len(sample)})
 features=json.loads((ROOT/'handoff/CORE24_CANDIDATE_FEATURES.json').read_text())['features'];check('core24_candidate_24_names_distinct',len(features)==24 and len(set(features))==24)
 sm=rows('manifests/SOURCE_FILES.csv');check('source_publication_hashes',all(digest(ROOT/x['relative_path'])==x['published_sha256'] for x in sm),{'files':len(sm)})
 provided=rows('manifests/PROVIDED_FILES.csv');check('provided_file_hashes_and_scope',all(digest(ROOT/x['provided_path'])==x['published_sha256'] and x['provision'] in {'sample_only','complete_file_anonymized'} for x in provided),{'entries':len(provided)})
 match=rows('manifests/RUNTIME_PROGRAM_MATCH.csv');check('saved_runtime_matches_pinned_source',len(match)==7 and all(x['byte_match']=='True' for x in match))
 print(json.dumps({'passed':all(x['passed'] for x in checks),'checks':checks},indent=2))
 return 0 if all(x['passed'] for x in checks) else 1
if __name__=='__main__':sys.exit(main())
