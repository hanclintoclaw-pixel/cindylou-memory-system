#!/usr/bin/env python3
"""Prepare a new disposable isolated native partition from a trusted v2 registry."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unification.partition import materialize_public
from unification.registry import load_registry


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--embedding-url',required=True,help='existing loopback OpenAI-compatible embedding endpoint; never managed by this experiment')
    args=ap.parse_args()
    endpoint=urlparse(args.embedding_url)
    if endpoint.scheme != 'http' or endpoint.hostname not in {'127.0.0.1','::1'} or endpoint.username or endpoint.password:
        ap.error('an explicit unauthenticated loopback endpoint is required')
    target=args.output.absolute()
    manifest=materialize_public(load_registry(args.registry),target)
    state=target/'state'
    cfg={'agents':{'defaults':{'workspace':str(target/'workspace')},'entries':{
        'pilot':{'workspace':str(target/'workspace'),'agentDir':str(state/'agents/pilot/agent')}}},
        'memory':{'search':{'enabled':True,'provider':'openai-compatible','model':'embeddinggemma-300m-qat-q8_0','fallback':'none','sources':['memory'],
            'rememberAcrossConversations':False,'experimental':{'sessionMemory':False},
            'extraPaths':[], 'remote':{'baseUrl':args.embedding_url,'apiKey':'public-partition-local'},
            'query':{'minScore':0},'store':{'vector':{'enabled':True}},
            'sync':{'watch':False,'onSearch':False,'onSessionStart':False}}},
        'plugins':{'allow':['memory-core'],'slots':{'memory':'memory-core'},'entries':{'memory-core':{'enabled':True}}}}
    config=target/'openclaw.json'
    config.write_text(json.dumps(cfg,indent=2)+'\n');config.chmod(0o600)
    print(json.dumps({'partition':str(target),'records':len(manifest['records'])}))


if __name__=='__main__':
    main()
