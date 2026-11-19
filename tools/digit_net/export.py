import numpy as np, json, base64, sys
d=np.load(sys.argv[1]); c1=d['k1'].shape[1]; c2=d['k2'].shape[1]; f=d['w3'].shape[1]; C=d['w4'].shape[1]
out={'layout':[c1,c2,f,C],'tensors':{}}
for k in ['k1','b1','k2','b2','w3','b3','w4','b4']:
    a=d[k].astype(np.float64); s=float(np.abs(a).max()/127) or 1.0
    q=np.clip(np.round(a/s),-127,127).astype(np.int8)
    out['tensors'][k]={'shape':list(a.shape),'scale':s,'data':base64.b64encode(q.tobytes()).decode()}
json.dump(out,open(sys.argv[2],'w'),separators=(',',':'))
