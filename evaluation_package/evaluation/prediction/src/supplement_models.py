"""Pinned author backbones, with explicit V2 task adapters.

Author training/evaluation drivers are never executed. AST extraction preserves
the selected definitions byte-for-byte semantically and avoids dataset imports.
"""
import ast
import importlib.util
import sys
from types import SimpleNamespace
import numpy as np
import torch
from torch import nn
from .data import ROOT


def definitions(path, names, namespace):
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def source_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TimeFilter(nn.Module):
    def __init__(self, channels, target, architecture):
        super().__init__(); self.name='TimeFilter'; self.target_index=target
        p=ROOT/'third_party/timefilter'
        embed=source_module('_timefilter_embed',p/'layers/Embed.py')
        norm=source_module('_timefilter_norm',p/'layers/StandardNorm.py')
        layers=source_module('_timefilter_layers',p/'layers/TimeFilter_layers.py')
        ns=dict(torch=torch,nn=nn,PositionalEmbedding=embed.PositionalEmbedding,
                Normalize=norm.Normalize,TimeFilter_Backbone=layers.TimeFilter_Backbone)
        definitions(p/'models/TimeFilter.py',['PatchEmbed','Model'],ns)
        config=SimpleNamespace(task_name='long_term_forecast',seq_len=60,pred_len=1,
                               enc_in=channels,c_out=channels,**architecture)
        self.native=ns['Model'](config)
        n=60//architecture['patch_len']; length=channels*n; masks=[]
        for k in range(length):
            idx=torch.arange(length)
            spatial=((idx%n==k%n)&(idx!=k)).float()
            temporal=((idx>=k//n*n)&(idx<k//n*n+n)&(idx!=k)).float()
            mixed=1-spatial-temporal; mixed[k]=0
            masks.append(torch.stack([spatial,temporal,mixed]))
        self.register_buffer('graph_masks',torch.stack(masks))
        self.auxiliary_loss=None

    def forward(self,x):
        z,self.auxiliary_loss=self.native(x,self.graph_masks,is_training=self.training)
        return z[:,0,self.target_index]


class WPMixer(nn.Module):
    def __init__(self,channels,target,architecture):
        super().__init__();self.name='WPMixer';self.target_index=target
        p=ROOT/'third_party/wpmixer'
        # Use the author's vendored wavelet package (including its AMP controls).
        sys.path.insert(0,str(p))
        try:
            from pytorch_wavelets import DWT1DForward,DWT1DInverse
        finally:sys.path.remove(str(p))
        revin=source_module('_wpmixer_revin',p/'utils/RevIN.py')
        ns=dict(torch=torch,nn=nn,np=np,RevIN=revin.RevIN,DWT1DForward=DWT1DForward,DWT1DInverse=DWT1DInverse)
        definitions(p/'models/decomposition.py',['Decomposition'],ns)
        definitions(p/'models/wavelet_patch_mixer.py',['WPMixerCore','ResolutionBranch','Mixer','TokenMixer'],ns)
        a=architecture.copy()
        self.native=ns['WPMixerCore'](input_length=60,pred_length=1,wavelet_name=a['wavelet'],level=a['level'],
            channel=channels,batch_size=128,use_amp=False,device=torch.device('cpu'),no_decomposition=False,
            d_model=a['d_model'],dropout=a['dropout'],embedding_dropout=a['dropout'],
            tfactor=a['tfactor'],dfactor=a['dfactor'],patch_len=a['patch_len'],patch_stride=a['stride'])

    def forward(self,x):
        return self.native(x)[:,0,self.target_index]


class KANAD(nn.Module):
    def __init__(self,channels,architecture):
        super().__init__();self.name='KANAD';self.numeric_channels=channels//2
        ns=dict(th=torch,torch=torch,nn=nn)
        definitions(ROOT/'third_party/kanad/kanad/kanad.py',['KANADModel'],ns)
        # 60-point observed window: predict the anchor from its preceding 59
        # observations. Native first differencing leaves 58 input differences.
        self.native=ns['KANADModel'](window=58,order=architecture['order'])

    def forward(self,x):
        c=self.numeric_channels
        history=x[:,:-1,:c].transpose(1,2)
        delta=history[...,1:]-history[...,:-1]
        z=self.native(delta.reshape(-1,58)).reshape(len(x),c)
        return (z+x[:,-2,:c]).unsqueeze(1)


class CCMTAD(nn.Module):
    def __init__(self,channels,architecture):
        super().__init__();self.name='CCMTAD';self.numeric_channels=channels//2
        p=ROOT/'third_party/ccmtad'
        ns=dict(torch=torch,nn=nn,np=np,F=torch.nn.functional,init=torch.nn.init)
        definitions(p/'models/CausalLinearLayer.py',['CausalLinearLayer','create_anti_diagonal_mat'],ns)
        definitions(p/'utils/tools.py',['Permute'],ns)
        names=['CCM_TAD','__Model__','CausalMixer','TemporalMixer','Head','MultiHeadEmbedding']
        definitions(p/'models/CCM_TAD.py',names,ns)
        assert architecture['clusterid'] is not None,'Training-only clusters must be frozen first'
        config=SimpleNamespace(seq_len=60,pred_len=60,c_in=channels,batch_size=128,
            use_amp=False,device=torch.device('cpu'),**architecture)
        self.native=ns['CCM_TAD'](config)

    def forward(self,x):return self.native(x)


def build(spec,channels,target=0):
    cls=globals()[spec['id']]
    if spec['id'] in ['TimeFilter','WPMixer']:return cls(channels,target,spec['architecture'])
    return cls(channels,spec['architecture'])
