"""Rebuild and train the full classifier in a fresh run directory from packaged data."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time
HERE=Path(__file__).resolve().parent;TOP=HERE.parents[2];SRC=TOP/'evaluation_package'/'evaluation'/'localization';DATA=TOP/'data_machine'/'dataset'/'task_data'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);a=ap.parse_args();run=Path(a.run_dir).resolve();R=run/'localization'
 if run.exists() and any(run.iterdir()):raise FileExistsError(f'Use a new empty run directory: {run}')
 run.mkdir(parents=True,exist_ok=True);R.mkdir()
 for rel in ['code','legacy_reference']:
  shutil.copytree(SRC/rel,R/rel,ignore=shutil.ignore_patterns('__pycache__','.git'))
 shutil.copy2(SRC/'config.json',R/'config.json')
 for name in ['audit','cache','data_contract','logs','metrics','models','predictions','reports']:(R/name).mkdir()
 # Verify every current task-package member before preparation; do not rely on legacy 154-path receipts.
 rows=[]
 for line in (DATA/'SHA256SUMS.txt').read_text().splitlines():
  h,rel=line.split(maxsplit=1);rel=rel.lstrip('*');actual=sha(DATA/rel);rows.append({'path':rel,'expected':h,'actual':actual,'ok':h==actual})
 assert rows and all(x['ok'] for x in rows)
 (R/'logs/preflight.log').write_text(f'PREFLIGHT_PASS PACKAGE_MANIFEST_PASS entries={len(rows)} sha256={sha(DATA/"SHA256SUMS.txt")}\n')
 env=os.environ.copy();env['DGATE_LOCALIZATION_DATA_PACKAGE']=str(DATA.resolve());env['MPLCONFIGDIR']=str(run/'.mplconfig')
 py=sys.executable
 def run_cmd(*args):subprocess.run([py,*map(str,args)],cwd=R,env=env,check=True)
 start=time.time();run_cmd('code/pipeline.py','prepare');run_cmd('code/pipeline.py','smoke')
 # Freeze the actual portable candidate code and its prepared data before any formal fit.
 code={str(p.relative_to(R)):sha(p) for p in sorted((R/'code').glob('*.py'))}
 contract={str(p.relative_to(R)):sha(p) for p in sorted((R/'data_contract').glob('*')) if p.is_file()}
 freeze={'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'config_sha256':sha(R/'config.json'),'code':code,'contract':contract,'preprocess_sha256':sha(R/'models/preprocessing.json'),'training_smoke_sha256':sha(R/'audit/training_smoke.json'),'formal_fits_started':False,'heldout_inference_started':False,'data_source':'packaged data_machine/dataset/task_data'}
 (R/'audit/FORMAL_START_FREEZE.json').write_text(json.dumps(freeze,indent=2,ensure_ascii=False)+'\n')
 run_cmd('code/pipeline.py','train');run_cmd('code/pipeline.py','evaluate')
 tracker=json.loads((R/'tracker.json').read_text());assert len(tracker)==15 and all(x['status']=='success' for x in tracker)
 testfreeze=json.loads((R/'audit/TEST_FREEZE.json').read_text());assert testfreeze['all15_success']
 summary={'run_id':'DGATE_FL_BUNDLE_TRAIN_'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()),'status':'DONE','scope':'fresh full 12-class retraining: 5 model variants x 3 seeds; fit D01-D04, select on D05, evaluate D06/D07 only after TEST_FREEZE','test_status':'previously_accessed post-hoc; not blind','package_manifest_sha256':sha(DATA/'SHA256SUMS.txt'),'package_member_count':len(rows),'package_members_verified':sum(x['ok'] for x in rows),'code_sha256':code,'freeze_sha256':sha(R/'audit/TEST_FREEZE.json'),'tracker_sha256':sha(R/'tracker.json'),'successful_fits':len(tracker),'metrics_sha256':sha(R/'metrics/ALL_METRICS.csv'),'seconds':time.time()-start,'fits':[{'model':x['model'],'seed':x['seed'],'selected_epoch':x.get('selected_epoch'),'seconds':x.get('seconds'),'peak_cuda_allocated_bytes':x.get('peak_cuda_allocated_bytes'),'fit_sample_ids_sha256':x.get('fit_sample_ids_sha256')} for x in tracker]}
 (run/'NEW_RUN_MANIFEST.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':summary['status'],'run_id':summary['run_id'],'fits':summary['successful_fits'],'seconds':summary['seconds'],'run_dir':str(run)},ensure_ascii=False))
if __name__=='__main__':main()
