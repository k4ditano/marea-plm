"""Compare native permission preparation on an owned state tree; no SDK or UI."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,statistics,subprocess,time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--before',type=Path,required=True,help='Baseline marea-agent.exe')
parser.add_argument('--after',type=Path,required=True,help='Updated marea-agent.exe with security-write tracing')
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True,help='New directory retaining owned fixtures, logs and report')
args=parser.parse_args();assert os.name=='nt','This measurement requires Windows'
sources={'before':args.before.resolve(strict=True),'after':args.after.resolve(strict=True)}
node=args.node.resolve(strict=True)
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
report={'scope':'Owned 500-file state; permission setup only, no SDK/model/UI or desktop input. Warm samples are not product startup latency.','results':{}}
try:
    for name,source in sources.items():
        bundle=out/name;(bundle/'bin').mkdir(parents=True);(bundle/'app/agent').mkdir(parents=True)
        (bundle/'app/agent/worker.mjs').write_text('// Preparation fixture; never executed.\n')
        for origin,destination in [(source,bundle/'bin/marea-agent.exe'),(node,bundle/'bin/node.exe')]:shutil.copy2(origin,destination)
        state=bundle/'local/Marea/Agent';state.mkdir(parents=True)
        for index in range(500):(state/f'owned-{index:04}.txt').write_text('Owned permission fixture.\n')
        report['results'][name]=dict(sha256=hashlib.sha256(source.read_bytes()).hexdigest(),samples=[])
    # Alternating samples reduce drift; first two passes establish each cache and inherited state.
    for repeat in range(7):
        for name in ('before','after') if repeat%2==0 else ('after','before'):
            bundle=out/name;started=time.perf_counter()
            result=subprocess.run([str(bundle/'bin/marea-agent.exe'),'--prepare'],env=dict(os.environ,LOCALAPPDATA=str(bundle/'local'),MAREA_AGENT_TRACE='1'),
                capture_output=True,text=True,encoding='utf-8',timeout=40,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            elapsed=time.perf_counter()-started;assert result.returncode==0,result.stderr
            (bundle/f'prepare-{repeat}.log').write_text(result.stderr,encoding='utf-8')
            writes=re.search(r'security updates \((\d+) writes\)',result.stderr)
            if repeat>=2:report['results'][name]['samples'].append(dict(seconds=elapsed,security_writes=None if not writes else int(writes[1])))
    for value in report['results'].values():value['median_seconds']=statistics.median(s['seconds'] for s in value['samples'])
    assert all(s['security_writes']==0 for s in report['results']['after']['samples'])
    report['passed']=True
finally:
    for name in sources:
        host=out/name/'bin/marea-agent.exe'
        if host.is_file():
            result=subprocess.run([str(host),'--remove-profile'],capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            report.setdefault('cleanup',{})[name]=result.returncode
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
