"""Run only after formal training exits successfully; no fitting or tuning here."""
from experiment import *
from evaluate import evaluate,metrics,baselines_raw
from audit import audit
from report import report
from audit_derived import audit_derived

def main():
    assert (ROOT/'metadata/training_complete.json').exists()
    dump('EXECUTION_STATUS.json',dict(status='RUNNING',stage='evaluation',utc=pd.Timestamp.now(tz='UTC').isoformat()))
    for p,h in json.load(open(ROOT/'metadata/training_complete.json'))['checkpoints'].items():assert sha(ROOT/'checkpoints'/p)==h
    freeze={'checkpoints':{p.name:sha(p) for p in (ROOT/'checkpoints').glob('*.pt')},'evaluation_masks':{p.name:sha(p) for p in (ROOT/'masks').glob('*.npz') if not p.name.startswith('train_')},'code':{p.name:sha(p) for p in (ROOT/'code').glob('*.py')},'utc':pd.Timestamp.now(tz='UTC').isoformat()}
    freeze['prepared_inputs']={str(p.relative_to(ROOT)):sha(p) for p in list((ROOT/'data').glob('*.npz'))+[ROOT/'metadata'/f for f in ['scales.npz','window_index.csv','segments.csv','config.json','runs.csv']]}
    dump('metadata/PRE_EVALUATION_FREEZE.json',freeze)
    # Hand-check interpolation boundaries, no predecessor, and native missing truth.
    raw=np.full((60,24),np.nan);raw[0,16]=1;raw[2,16]=3;v=np.isfinite(raw);base=baselines_raw(raw,v,16,np.full(24,7.));assert base[0,1]==7 and base[1,1]==1 and base[2,1]==2 and base[2,-1]==3
    v[0]=False;base=baselines_raw(raw,v,16,np.full(24,7.));assert base[1,0]==7 and base[2,0]==3
    assert np.mean(np.abs(np.array([1.,4.])-np.array([2.,2.])))==1.5
    dump('metadata/hand_checks.json',dict(status='PASS',cases=['median','forward_fallback','linear_internal','linear_boundary','known_MAE']))
    start=time.time();evaluate();metrics();dump('logs/evaluation_time.json',dict(seconds=time.time()-start));audit();report();audit_derived()
    for p,h in freeze['prepared_inputs'].items():assert sha(ROOT/p)==h
    for p,h in freeze['evaluation_masks'].items():assert sha(ROOT/'masks'/p)==h
    for p,h in freeze['checkpoints'].items():assert sha(ROOT/'checkpoints'/p)==h
    dump('EXECUTION_STATUS.json',dict(status='NUMERICAL_WORK_DONE',stage='awaiting_final_semantic_review',formal_fits=6,failed_fits=0,utc=pd.Timestamp.now(tz='UTC').isoformat()))
if __name__=='__main__':
    try:main()
    except Exception as e:
        dump('EXECUTION_STATUS.json',dict(status='ERROR',error=repr(e),utc=pd.Timestamp.now(tz='UTC').isoformat()));raise
