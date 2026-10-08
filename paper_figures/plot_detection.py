"""Recreate Figure 3 with two vertically stacked panels from adjacent CSV data."""
from pathlib import Path
import csv, os, tempfile
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "d_gate_matplotlib"))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
R=Path(__file__).resolve().parent
# Two-times final publication dimensions: all typography scales to 7-8 pt.
FONT=next((n for n in ['Arial','Helvetica','DejaVu Sans'] if any(f.name==n for f in font_manager.fontManager.ttflist)), 'DejaVu Sans')
plt.rcParams.update({'font.family':FONT,'font.size':16,'axes.labelsize':16,'xtick.labelsize':14,'ytick.labelsize':14,'axes.linewidth':1.5,'axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,'svg.fonttype':'none','pdf.fonttype':42,'hatch.linewidth':.7,'savefig.facecolor':'white'})
P={'blue':'#3775BA','red':'#E9A6A1','green':'#8BCF8B'}
checks=[]
def finish(fig,name):
 fig.canvas.draw()
 renderer=fig.canvas.get_renderer();box=fig.bbox
 for obj in fig.findobj(matplotlib.text.Text):
  if obj.get_visible() and obj.get_text():
   b=obj.get_window_extent(renderer)
   assert b.x0>=-1 and b.y0>=-1 and b.x1<=box.x1+1 and b.y1<=box.y1+1,(name,obj.get_text(),b.bounds)
 for ext in ['pdf','svg','png']:fig.savefig(R/f'{name}.{ext}',dpi=600)
 plt.close(fig)
def clean(ax):
 ax.set_axisbelow(True);ax.grid(axis='y',color='#E4E4E4',lw=.8);ax.tick_params(width=1.3,length=4)
rows=list(csv.DictReader((R/'detection_metrics.csv').open()));assert len(rows)==8
models=['Autoencoder','KAN-AD (adapted)','TranAD (adapted)','Random Forest']
fig,ax=plt.subplots(2,1,figsize=(7.08,6.7),sharex=True,gridspec_kw={'height_ratios':[1,1]})
fig.subplots_adjust(left=.15,right=.985,top=.835,bottom=.14,hspace=.28)
for k,budget in enumerate([.1,1.]):
 rr=[next(r for r in rows if r['Method']==m and float(r['Budget'])==budget) for m in models]
 for aa,mean,sd in zip(ax,['Recall','FAR'],['Recall_SD','FAR_SD']):
  xx=np.arange(4)+(k-.5)*.36;y=np.array([float(r[mean]) for r in rr]);err=np.array([float(r[sd]) for r in rr])
  bars=aa.bar(xx,y,.32,bottom=0,color=[P['blue'],P['red']][k],edgecolor='#272727',linewidth=1,hatch=['','//'][k],label=f'{budget:g}/h',yerr=err,error_kw={'ecolor':'#272727','elinewidth':1.2,'capsize':3,'capthick':1.2},zorder=3)
  assert np.allclose([b.get_height() for b in bars],y,rtol=0,atol=0)
  for x,v,er,row in zip(xx,y,err,rr):
   checks.append(dict(figure='fault_detection',method=row['Method'],condition=budget,metric=mean,value=v,sd=er))
   value_label=f'{v:.2f}' if mean=='Recall' else f'{v:.3f}'
   aa.annotate(value_label,(x,v+er),xytext=(0,5),textcoords='offset points',ha='center',va='bottom',fontsize=13)
   # A visible zero-value marker keeps zero distinct from missing data without
   # assigning a nonzero height to the bar.
   if v==0:aa.plot(x,0,'o',ms=6,mfc='white',mec=[P['blue'],P['red']][k],mew=1.5,clip_on=False,zorder=5)
for aa in ax:clean(aa);aa.set_xlim(-.65,3.65)
ax[0].set_ylim(0,88);ax[0].set_yticks([0,20,40,60,80]);ax[0].set_ylabel('Event recall (%)')
# Full symmetric sample SD retained, including the tiny below-zero lower bound.
ax[1].set_ylim(-.025,1.5);ax[1].set_yticks([0,.5,1,1.5]);ax[1].set_ylabel('False alarms/h')
# Align the visible baseline with the bar origins, not the negative SD margin.
for aa in ax:
 aa.spines['bottom'].set_position(('data',0))
ax[1].set_xticks(range(4),['Autoencoder','KAN-AD\n(adapted)','TranAD\n(adapted)','Random\nForest']);ax[1].set_xlabel('Method',labelpad=7)
for a,label in zip(ax,['(a)','(b)']):a.text(.015,.97,label,ha='left',va='top',transform=a.transAxes,fontsize=14,fontweight='bold')
fig.legend(*ax[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.565,.997),ncol=2,title='Validation false-alarm target',fontsize=14,title_fontsize=15,handlelength=1.6,columnspacing=2)
assert np.allclose(ax[0].get_position().bounds[::2],ax[1].get_position().bounds[::2])
finish(fig,'fault_detection')
print("Figure 3 exported with the original two-panel layout; 16 mean/SD pairs retained.")
