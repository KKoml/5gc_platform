"""Exact prompt-authorized role exception, never a global alias."""
CORE_RUN='supp_core24h'
CORE_SLOT='supp_core24h'
RULE='core24h_source_role_clarification_v1'
VALID={'train','validation','test','external_validation','supplementary_only','diagnostic_holdout','development_only'}
def resolve_role(run_id,slot,source_episode_run_split,registry_split,index_split=None):
 if registry_split not in VALID:raise ValueError('Unknown registry role')
 if index_split is not None and index_split!=registry_split:raise ValueError('Index and registry split disagree')
 if run_id==CORE_RUN or slot==CORE_SLOT:
  if run_id!=CORE_RUN or slot!=CORE_SLOT or registry_split!='supplementary_only':raise ValueError('Core24h identity or effective role changed')
 if source_episode_run_split==registry_split:return registry_split,'exact_role_match'
 if (run_id,slot,source_episode_run_split,registry_split)==(CORE_RUN,CORE_SLOT,'event_block_protocol','supplementary_only'):
  return registry_split,RULE
 raise ValueError('Unrecognized source role mismatch')
def tests():
 assert resolve_role(CORE_RUN,CORE_SLOT,'event_block_protocol','supplementary_only','supplementary_only')==('supplementary_only',RULE)
 assert resolve_role(CORE_RUN,CORE_SLOT,'event_block_protocol','supplementary_only')[0]=='supplementary_only'
 assert resolve_role('D01','D01','train','train','train')==('train','exact_role_match')
 bad=[(CORE_RUN,CORE_SLOT,'event_block_protocol','train','train'),(CORE_RUN,CORE_SLOT,'event_block_protocol','test','test'),('other',CORE_SLOT,'event_block_protocol','supplementary_only','supplementary_only'),(CORE_RUN,'wrong','event_block_protocol','supplementary_only','supplementary_only'),('other','D01','event_block_protocol','train','train'),(CORE_RUN,CORE_SLOT,'unknown','supplementary_only','supplementary_only'),('D01','D01','train','train','test'),(CORE_RUN,CORE_SLOT,'test','test','test')]
 for args in bad:
  try:resolve_role(*args)
  except ValueError:continue
  raise AssertionError(args)
 return {'positive_cases':3,'negative_cases':len(bad),'status':'PASS'}
