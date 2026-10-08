import json,sys,platform,hashlib
from pathlib import Path
import torch,numpy,pandas,sklearn,pyarrow
from legacy_models import SequenceClassifier
r=Path(__file__).resolve().parents[1]
torch.manual_seed(17);torch.set_num_threads(4)
m=SequenceClassifier('LSTM',48,12).cuda();x=torch.randn(4,12,48,device='cuda');y=m(x);y.square().mean().backward();torch.cuda.synchronize()
assert y.shape==(4,12) and torch.isfinite(y).all() and all(p.grad is not None for p in m.parameters())
spec={'python':sys.version,'executable':sys.executable,'torch':torch.__version__,'numpy':numpy.__version__,'pandas':pandas.__version__,'sklearn':sklearn.__version__,'pyarrow':pyarrow.__version__,'device':torch.cuda.get_device_name(),'threads':4,'reuse':'existing environment, no installation'}
(r/'audit/environment_witness.json').write_text(json.dumps(spec,indent=2));print('RCA_ENV_WITNESS_OK',spec)
