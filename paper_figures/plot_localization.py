"""Portable extraction of the located current classification figure renderer."""
from pathlib import Path
import csv,json,hashlib,shutil
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
rows=list(csv.DictReader((R/'localization_display.csv').open()));raw=list(csv.DictReader((R/'localization_metrics.csv').open()));assert len(rows)==9
models=['LSTM','TCN','Random Forest'];metrics=['Fault type','Location','Joint'];columns=['Fault_type_accuracy','Location_accuracy','Joint_accuracy']
fig,ax=plt.subplots(figsize=(7.08,4.6));fig.subplots_adjust(left=.15,right=.985,top=.80,bottom=.17)
for k,(metric,col) in enumerate(zip(metrics,columns)):
 rr=[next(r for r in rows if r['Model']==m and r['Metric']==metric) for m in models];y=np.array([float(r['Mean']) for r in rr]);err=np.array([float(r['Sample_SD']) for r in rr]);xx=np.arange(3)+(k-1)*.26
 for model,v,sd in zip(models,y,err):
  vals=[float(r[col]) for r in raw if r['Model']==model];assert len(vals)==3 and np.isclose(np.mean(vals),v,atol=1e-12) and np.isclose(np.std(vals,ddof=1),sd,atol=1e-12)
  checks.append(dict(figure='fault_localization',method=model,metric=metric,value=v,sd=sd))
 bars=ax.bar(xx,y,.23,color=[P['red'],P['green'],P['blue']][k],edgecolor='#272727',linewidth=1,hatch=['//','..',''][k],label=metric,yerr=err,error_kw={'ecolor':'#272727','elinewidth':1.2,'capsize':3,'capthick':1.2},zorder=3)
 assert np.allclose([b.get_height() for b in bars],y,rtol=0,atol=0)
 for x,v,sd in zip(xx,y,err):ax.annotate(f'{v:.1f}',(x,v+sd),xytext=(0,4),textcoords='offset points',ha='center',va='bottom',fontsize=13)
clean(ax);ax.set_ylim(0,112);ax.set_yticks([0,25,50,75,100]);ax.set_ylabel('Accuracy (%)');ax.set_xticks(range(3),models);ax.set_xlabel('Method',labelpad=7);ax.set_xlim(-.6,2.6)
fig.legend(*ax.get_legend_handles_labels(),ncol=3,loc='upper center',bbox_to_anchor=(.56,.98),fontsize=14,handlelength=1.6,columnspacing=1.4)
finish(fig,'fault_localization')
