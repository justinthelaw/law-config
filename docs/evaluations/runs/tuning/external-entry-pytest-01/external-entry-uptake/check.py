"""Verify immutable supplement identity against the normal exported pilot record."""
import argparse,hashlib,json
from pathlib import Path

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True);args=parser.parse_args();here=Path(__file__).resolve().parent
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();manifest=json.loads((here/'manifest.json').read_text())
 for path,digest in manifest['files'].items():
  if sha(here/path)!=digest:raise ValueError('Supplement file differs: '+path)
 s=json.loads((here/'supplement.json').read_text());r=json.loads(args.result.read_text())
 if r['name']!='external-entry-pytest-01' or r['registration_sha256']!=s['registration_sha256'] or r['result_sha256']!=s['raw_result_sha256']:raise ValueError('Different pilot registration or raw seal')
 for role,evidence in s['roles'].items():
  row=r['prior_develop'] if role=='prior' else r['submissions']['control' if role=='stock' else 'develop']
  for key in ('patch_sha256','proposal_sha256'):
   if row[key]!=evidence['bindings'][key]:raise ValueError(role+' final artifact differs')
  if role!='prior' and row['receipt_sha256']['native']!=evidence['bindings']['native_sha256']:raise ValueError(role+' native seal differs')
  if evidence['criteria']['declared_entry_final_pass'] is not None or evidence['criteria']['final_review_closed'] is not None:raise ValueError('Unknown execution/review evidence promoted')
  if any(c['route']!='python-module' for c in evidence['test_commands']):raise ValueError('Producer route differs')
  if evidence['review']['after_final_configured_completion'] is not False:raise ValueError('Pending review chronology differs')
 if s['roles']['candidate']['criteria']['inspect_before_replace'] is not None or s['roles']['candidate']['criterion_reasons']['inspect_before_replace']!='no representation replacement':raise ValueError('Inapplicable replacement branch promoted')
 if s['distinct_positive_mechanism'] is not None or s['complete_preregistered_uptake'] is not None:raise ValueError('Incomplete mechanism promoted')
 print('Verified #19 raw/registration/artifact bindings, scoped uptake and nullable evidence closure.')
if __name__=='__main__':main()
