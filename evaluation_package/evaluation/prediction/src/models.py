"""Small heads on pinned official models; native anomaly objectives below."""
import sys
from types import SimpleNamespace
import importlib
import numpy as np
import torch
from torch import nn
from .data import ROOT
sys.path.insert(0,str(ROOT/'dependencies'))
sys.path.insert(0,str(ROOT/'third_party/tslib'))
from .classic_native import LSTMForecaster, TCNForecaster, DenseAutoencoder, LSTMAutoencoder
from .tranad_native import TranAD
from third_party.anomaly_transformer.model.AnomalyTransformer import AnomalyTransformer

def select_target(y, target_index):
    assert y.ndim==3 and y.shape[1]==1
    return y[:,0,target_index]

def native_config(channels,architecture,task):
    d=dict(task_name='long_term_forecast' if task=='T1' else 'anomaly_detection',seq_len=60,pred_len=1 if task=='T1' else 0,
        label_len=0,enc_in=channels,dec_in=channels,c_out=channels,d_model=64,n_heads=4,e_layers=2,d_ff=128,
        dropout=.1,moving_avg=13,embed='timeF',freq='s',factor=1,activation='gelu',
        decomp_method='moving_avg',use_norm=1,down_sampling_method='avg',down_sampling_window=2,
        down_sampling_layers=1,channel_independence=0,use_future_temporal_feature=False,top_k=3,num_kernels=3)
    d.update(architecture if isinstance(architecture,dict) else {})
    return SimpleNamespace(**d)

class Forecast(nn.Module):
    def __init__(self,name,channels,target_index,architecture):
        super().__init__(); self.name=name; self.target_index=target_index
        if name=='LSTM': self.native=LSTMForecaster(channels,architecture['hidden'],architecture['layers'],architecture['dropout'])
        elif name=='TCN': self.native=TCNForecaster(channels,architecture['channels'],architecture['dropout'])
        else:
            c=native_config(channels,architecture,'T1'); constructor=importlib.import_module('models.'+name).Model
            kwargs={k:architecture[k] for k in ['patch_len','stride']} if name=='PatchTST' else {}
            self.native=constructor(c,**kwargs)
    def forward(self,x):
        if self.name in ['LSTM','TCN']: return self.native(x)
        return select_target(self.native(x,None,None,None),self.target_index)

class Detection(nn.Module):
    def __init__(self,name,channels,architecture):
        super().__init__(); self.name=name; self.numeric_channels=channels//2
        if name=='AE': self.native=DenseAutoencoder(60,channels,architecture['hidden'],architecture['latent'])
        elif name=='LSTMAE': self.native=LSTMAutoencoder(channels,architecture['hidden'],architecture['latent'])
        elif name=='TranAD': self.native=TranAD(channels)
        elif name=='AnomalyTransformer':
            # Unspecified feed-forward width retains the official constructor default, 512.
            self.native=AnomalyTransformer(60,channels,channels,d_model=architecture['d_model'],n_heads=architecture['n_heads'],e_layers=architecture['e_layers'])
        elif name=='TimesNet': self.native=importlib.import_module('models.TimesNet').Model(native_config(channels,architecture,'T2'))
        else: raise ValueError(name)
    def forward(self,x):
        if self.name=='TranAD':
            z=self.native(x.transpose(0,1),x[:,-1].unsqueeze(0))
            return tuple(t.transpose(0,1) for t in z)
        if self.name=='TimesNet': return self.native(x,None,None,None)
        return self.native(x)

def numeric_error(x,z):
    c=x.shape[-1]//2
    if z.shape[1]==1: x=x[:,-1:]
    valid=1-x[...,c:]; error=(x[...,:c]-z[...,:c]).square()*valid
    return error,valid

def reconstruction(x,z):
    err,mask=numeric_error(x,z)
    return err.sum()/mask.sum().clamp_min(1)

def kl(p,q):
    # Same FP32 epsilon and head averaging as the author's my_kl_loss.
    return (p*(torch.log(p+0.0001)-torch.log(q+0.0001))).sum(-1).mean(1)

def associations(series,prior):
    sl=0.;pl=0.;energy=0.
    for s,p in zip(series,prior):
        p=p/p.sum(-1,keepdim=True)
        sl=sl+(kl(s,p.detach())+kl(p.detach(),s)).mean()
        pl=pl+(kl(p,s.detach())+kl(s.detach(),p)).mean()
        energy=energy+50*(kl(s,p.detach())+kl(p,s.detach()))
    return sl/len(series),pl/len(series),torch.softmax(-energy,dim=-1)

def losses(model,x,epoch):
    z=model(x)
    if model.name=='TranAD':
        loss=reconstruction(x,z[0])/(epoch+1)+(1-1/(epoch+1))*reconstruction(x,z[1])
        return (loss,),reconstruction(x,z[1])
    if model.name=='AnomalyTransformer':
        output,series,prior,_=z; rec=reconstruction(x,output);sl,pl,_=associations(series,prior)
        return (rec-3*sl,rec+3*pl),rec
    rec=reconstruction(x,z)
    return (rec,),rec

def scores(model,x):
    z=model(x); weight=None
    if model.name=='KANAD':
        c=x.shape[-1]//2;valid=1-x[:,-1,c:]
        return ((x[:,-1,:c]-z[:,0,:c]).abs()*valid).sum(-1)/valid.sum(-1).clamp_min(1)
    if model.name=='TranAD': z=z[1]
    elif model.name=='AnomalyTransformer':
        z,series,prior,_=z;_,_,weight=associations(series,prior)
    err,valid=numeric_error(x,z)
    mse=err.sum(-1)/valid.sum(-1).clamp_min(1)
    return mse[:,-1] if weight is None else (mse*weight)[:,-1]

def build(spec,channels,target_index=0,task='T1'):
    if spec['id'] in ['TimeFilter','WPMixer','KANAD','CCMTAD']:
        from .supplement_models import build as supplement_build
        return supplement_build(spec,channels,target_index)
    return Forecast(spec['id'],channels,target_index,spec.get('architecture',{})) if task=='T1' else Detection(spec['id'],channels,spec.get('architecture',{}))
