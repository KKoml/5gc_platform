import csv
from datetime import datetime
from pathlib import Path
p=Path(__file__).with_name('illustrative_D06_first20_rows.csv')
with p.open(newline='',encoding='utf-8') as f:
 rows=list(csv.DictReader(f))
assert len(rows)==20
assert all(any(v=='D06' for v in r.values()) for r in rows)
key='cutoff_time' if 'cutoff_time' in rows[0] else 'timestamp'
t=[datetime.fromisoformat(r[key].replace('Z','+00:00')).timestamp() for r in rows]
assert all(t[i+1]-t[i]==5 for i in range(len(t)-1))
print('PASS sample_rows=20 grid_seconds=5 slot=D06 sample_only=true')
