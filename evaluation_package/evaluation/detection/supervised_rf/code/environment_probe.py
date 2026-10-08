import json, sys, numpy as np, pandas as pd, sklearn, pyarrow
from sklearn.ensemble import HistGradientBoostingClassifier
rng=np.random.default_rng(17);x=rng.normal(size=(256,8));y=(x[:,0]+x[:,1]>0).astype(int)
m=HistGradientBoostingClassifier(max_iter=5,random_state=17).fit(x,y);p=m.predict_proba(x)
assert p.shape==(256,2) and np.isfinite(p).all()
print("CPU_EXPERIMENT_WITNESS_OK",json.dumps({"python":sys.version.split()[0],"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__,"pyarrow":pyarrow.__version__,"prediction_shape":list(p.shape)}))
