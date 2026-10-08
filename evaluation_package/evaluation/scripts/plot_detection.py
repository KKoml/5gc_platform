from pathlib import Path
import csv
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_panel_alignment import require_matplotlib_panel_alignment
# New quantitative figure: compare event detection yield, with aligned alarm burden.
# Eight source rows retained. Means and sample SD across three training seeds.
OUT=Path(__file__).resolve().parents[1] / 'generated_figures'
OUT.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((OUT.parent/'evidence/detection_metrics.csv').open()))
assert len(rows)==8
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],
 'font.size':6.5,'pdf.fonttype':42,'svg.fonttype':'none','axes.linewidth':.6})
fig,ax=plt.subplots(figsize=(3.5433,2.65))
fig.subplots_adjust(left=.285,right=.70,bottom=.17,top=.81)
colors=['#527EA9','#D29566']
models=['Autoencoder','KAN-AD (adapted)','TranAD (adapted)','Random Forest']
ax.set_xlim(0,100);ax.set_ylim(-.65,6.65)
ax.set_yticks([6,4,2,0],['Autoencoder','KAN-AD\n(adapted)','TranAD\n(adapted)','Random Forest']);ax.tick_params(axis='y',length=0,pad=6)
ax.set_xticks([0,25,50,75,100]);ax.tick_params(axis='x',length=3,labelsize=7)
ax.set_xlabel('Event recall (%)',labelpad=6)
for side in ['top','right','left']:ax.spines[side].set_visible(False)
for y in [1,3,5]:ax.axhline(y,color='#E8ECEF',linewidth=.65)
for r in rows:
 i=models.index(r['Method']);k=0 if float(r['Budget'])==.1 else 1
 y=6-2*i+(.24 if k==0 else -.24)
 v,sd=float(r['Recall']),float(r['Recall_SD'])
 ax.barh(y,v,height=.34,color=colors[k],zorder=2)
 if sd>0:ax.errorbar(v,y,xerr=sd,fmt='none',ecolor='#33434A',elinewidth=.7,capsize=1.5,zorder=3)
 ax.text(v+sd+1.8,y,f'{v:.1f}',ha='left',va='center',fontsize=6.4,color='#26343B')
 far,fs=float(r['FAR']),float(r['FAR_SD'])
 ax.text(1.12,y,f'{far:.3f} ± {fs:.3f}',transform=ax.get_yaxis_transform(),
         ha='left',va='center',fontsize=6.4,color=colors[k],clip_on=False)
ax.text(1.12,1.045,'False alarms/h',transform=ax.transAxes,ha='left',va='bottom',fontsize=6.5)
fig.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(colors,['0.1/h','1.0/h'])],
 title='Validation false-alarm target',title_fontsize=7, loc='upper center',bbox_to_anchor=(.54,1.01),ncol=2,frameon=False,fontsize=7,handlelength=1.3,columnspacing=1.7,borderaxespad=0)

fig.canvas.draw()
require_matplotlib_panel_alignment(fig,json_out=OUT/'fault_detection_alignment.json',strict=True)
fig.savefig(OUT/'fault_detection.png',dpi=600,facecolor='white')
fig.savefig(OUT/'fault_detection.pdf',facecolor='white')
fig.savefig(OUT/'fault_detection.svg',facecolor='white')

plt.close(fig)
