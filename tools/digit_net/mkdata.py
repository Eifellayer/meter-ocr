import sys, random, numpy as np, gen, feat
from multiprocessing import Pool
def work(seed):
    random.seed(seed)
    X=[];Y=[]
    for i in range(10000):
        im,c=gen.sample(); X.append(feat.features(im)); Y.append(c)
    return np.array(X,np.float32),np.array(Y,np.int64)
if __name__=='__main__':
    n=int(sys.argv[1]); off=int(sys.argv[2])
    with Pool(2) as p: parts=p.map(work, range(off,off+n))
    X=np.concatenate([a for a,b in parts]); Y=np.concatenate([b for a,b in parts])
    np.savez_compressed(sys.argv[3],X=X,Y=Y); print(X.shape)
