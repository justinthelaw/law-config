"""Bounded public stream state model with operation-preserving replay minimization."""
import itertools,json,warnings
from werkzeug import Response

TEXTS=['','A','\u0080','é','漢','😀','Aé','漢😀']

def execute(chunks,normalize):
    response=Response()
    expected=b''
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',DeprecationWarning)
            stream=response.stream
            for text in chunks:
                stream.write(text)
                expected+=text.encode('utf-8')
                if normalize:
                    actual=response.get_data()
                    if actual!=expected:return {'operation':'get_data','expected':list(expected),'actual':list(actual)}
                actual=stream.tell()
                if actual!=len(expected):return {'operation':'tell','expected':len(expected),'actual':actual}
                actual=response.get_data()
                if actual!=expected:return {'operation':'get_data','expected':list(expected),'actual':list(actual)}
                actual=stream.tell()
                if actual!=len(expected):return {'operation':'tell_after_get_data','expected':len(expected),'actual':actual}
        return None
    finally:
        response.close()

def minimize(chunks,normalize,operation):
    while True:
        candidates=[chunks[:i]+chunks[i+1:] for i in range(len(chunks))]
        candidates += [chunks[:i]+[text[:j]+text[j+1:]]+chunks[i+1:]
                       for i,text in enumerate(chunks) for j in range(len(text))]
        for candidate in candidates:
            failure=execute(candidate,normalize)
            if failure and failure['operation']==operation:
                chunks=candidate
                break
        else:
            return chunks

def main():
    failures=[];total=0
    for length in (1,2):
        for chunks in itertools.product(TEXTS,repeat=length):
            for normalize in (False,True):
                total+=1
                failure=execute(chunks,normalize)
                if failure:failures.append({'chunks':list(chunks),'normalize_before_tell':normalize,**failure})
    minimal=None
    if failures:
        witness=min(failures,key=lambda row:(len(row['chunks']),sum(map(len,row['chunks'])),row['chunks']))
        normalize=witness['normalize_before_tell']
        chunks=minimize(witness['chunks'],normalize,witness['operation'])
        failure=execute(chunks,normalize)
        assert failure and failure['operation']==witness['operation']
        minimal={'chunks':chunks,'normalize_before_tell':normalize,**failure}
    print(json.dumps({'outcome':'red-behavior' if failures else 'green','generated_cases':total,
        'failing_cases':len(failures),'minimal_replay':minimal,
        'oracle':'UTF-8 bytes accumulated by public writes; tell equals byte count; get_data preserves bytes; repeat tell after normalization.'},ensure_ascii=True))
    return 42 if failures else 0

if __name__=='__main__':
    raise SystemExit(main())
