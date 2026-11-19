import numpy as np, sys, time
sys.path.insert(0,'.')
from cnn import Net
d=np.load(sys.argv[1]); X,Y=d['X'].astype(np.float32),d['Y']
rng=np.random.default_rng(1); idx=rng.permutation(len(X)); X,Y=X[idx],Y[idx]
nv=5000; Xv,Yv=X[:nv],Y[:nv]; X,Y=X[nv:],Y[nv:]
EP=int(sys.argv[2]); net=Net(rng, c1=int(sys.argv[3]), c2=int(sys.argv[4]), f=int(sys.argv[5]))
M={k:np.zeros_like(v) for k,v in net.p.items()}; V={k:np.zeros_like(v) for k,v in net.p.items()}
lr=2e-3; t=0
for ep in range(EP):
    t0=time.time(); perm=rng.permutation(len(X))
    for i in range(0,len(X),128):
        bi=perm[i:i+128]; pr=net.forward(X[bi],keep=True); g=net.backward(pr,Y[bi]); t+=1
        for k in net.p:
            M[k]=.9*M[k]+.1*g[k]; V[k]=.999*V[k]+.001*g[k]**2
            net.p[k]-=lr*(M[k]/(1-.9**t))/(np.sqrt(V[k]/(1-.999**t))+1e-8)
    if ep in (int(EP*.6),int(EP*.85)): lr*=.3
    acc=np.mean(np.concatenate([net.forward(Xv[j:j+1000]).argmax(1) for j in range(0,nv,1000)])==Yv)
    print(ep,'val',round(float(acc),4),round(time.time()-t0),'s',flush=True)
    np.savez(sys.argv[6],**net.p)
