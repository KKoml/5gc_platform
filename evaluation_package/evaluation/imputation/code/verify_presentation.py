from experiment import *
from html.parser import HTMLParser
truth=pd.read_parquet(ROOT/'predictions/D06_truth.parquet');metrics=pd.read_csv(ROOT/'results/example_metrics.csv');checks=[]
for t in range(3):
    q=truth[(truth.window==0)&(truth.target==t)&(truth.condition==3)&(truth.mask_seed==101)];unit=1e6 if t<2 else 1
    for method,col in [('linear','linear_MAE'),('M_17','M_MAE'),('H_17','H_MAE')]:
        p=pd.read_parquet(ROOT/f'predictions/D06_{method}.parquet');mae=np.abs(p.loc[q.index,'prediction'].to_numpy()-q.truth.to_numpy()).mean()/unit;assert np.isclose(mae,metrics.iloc[t][col],rtol=1e-5,atol=1e-5);checks.append({'target':t,'method':method,'saved_prediction_MAE':float(mae),'plot_MAE':float(metrics.iloc[t][col])})
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.images=[];self.tables=0
    def handle_starttag(self,tag,attrs):
        if tag=='img':self.images.append(dict(attrs)['src'])
        if tag=='table':self.tables+=1
p=Parser();p.feed((ROOT/'REPORT_ZH.html').read_text());assert len(p.images)==2 and all(s.startswith('data:image/png;base64,') for s in p.images);assert p.tables>=6
dump('results/FIGURE_REPORT_CHECK.json',dict(status='PASS',examples=checks,html_embedded_figures=len(p.images),html_tables=p.tables,visual_check='all panels inspected; example bitrate prediction plotting units fixed and re-inspected'))
print('EXAMPLE AND HTML CHECK PASS',p.tables)
