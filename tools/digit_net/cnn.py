import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

def im2col(x, k, pad):
    # x: N,C,H,W -> N,H,W,C*k*k
    x = np.pad(x, ((0,0),(0,0),(pad,pad),(pad,pad)))
    w = swv(x, (k, k), axis=(2, 3))  # N,C,H,W,k,k
    N, C, H, W = w.shape[:4]
    return w.transpose(0, 2, 3, 1, 4, 5).reshape(N, H, W, C * k * k)

def col2im(dcol, shape, k, pad):
    N, C, H, W = shape
    dx = np.zeros((N, C, H + 2 * pad, W + 2 * pad), dcol.dtype)
    d = dcol.reshape(N, H, W, C, k, k)
    for i in range(k):
        for j in range(k):
            dx[:, :, i:i + H, j:j + W] += d[:, :, :, :, i, j].transpose(0, 3, 1, 2)
    return dx[:, :, pad:pad + H, pad:pad + W]

class Net:
    def __init__(self, rng, c1=8, c2=16, f=64, classes=11):
        self.p = {
            'k1': rng.normal(0, np.sqrt(2 / 25), (25, c1)).astype(np.float32), 'b1': np.zeros(c1, np.float32),
            'k2': rng.normal(0, np.sqrt(2 / (9 * c1)), (9 * c1, c2)).astype(np.float32), 'b2': np.zeros(c2, np.float32),
            'w3': rng.normal(0, np.sqrt(2 / (24 * c2)), (24 * c2, f)).astype(np.float32), 'b3': np.zeros(f, np.float32),
            'w4': rng.normal(0, np.sqrt(2 / f), (f, classes)).astype(np.float32), 'b4': np.zeros(classes, np.float32)}
        self.c1, self.c2 = c1, c2

    def forward(self, x, keep=False):
        p = self.p; N = len(x)
        x = x.reshape(N, 1, 24, 16)
        col1 = im2col(x, 5, 2)                      # N,24,16,25
        a1 = col1 @ p['k1'] + p['b1']               # N,24,16,c1
        r1 = np.maximum(a1, 0)
        q1 = r1.reshape(N, 12, 2, 8, 2, self.c1).max(axis=(2, 4))   # N,12,8,c1
        x2 = q1.transpose(0, 3, 1, 2)
        col2 = im2col(x2, 3, 1)                     # N,12,8,9c1
        a2 = col2 @ p['k2'] + p['b2']
        r2 = np.maximum(a2, 0)
        q2 = r2.reshape(N, 6, 2, 4, 2, self.c2).max(axis=(2, 4))    # N,6,4,c2
        flat = q2.reshape(N, -1)
        a3 = flat @ p['w3'] + p['b3']; r3 = np.maximum(a3, 0)
        z = r3 @ p['w4'] + p['b4']
        z = z - z.max(1, keepdims=True); e = np.exp(z); prob = e / e.sum(1, keepdims=True)
        if keep:
            self.cache = (x, col1, a1, r1, q1, x2, col2, a2, r2, q2, flat, a3, r3)
        return prob

    def backward(self, prob, y, wd=1e-4):
        p = self.p; (x, col1, a1, r1, q1, x2, col2, a2, r2, q2, flat, a3, r3) = self.cache
        N = len(y); g = {}
        dz = prob.copy(); dz[np.arange(N), y] -= 1; dz /= N
        g['w4'] = r3.T @ dz + wd * p['w4']; g['b4'] = dz.sum(0)
        dr3 = dz @ p['w4'].T; dr3[a3 <= 0] = 0
        g['w3'] = flat.T @ dr3 + wd * p['w3']; g['b3'] = dr3.sum(0)
        dq2 = (dr3 @ p['w3'].T).reshape(q2.shape)
        mask2 = (r2.reshape(N, 6, 2, 4, 2, self.c2) == q2[:, :, None, :, None, :])
        dr2 = (mask2 * dq2[:, :, None, :, None, :]).reshape(r2.shape); dr2[a2 <= 0] = 0
        g['k2'] = col2.reshape(-1, col2.shape[-1]).T @ dr2.reshape(-1, self.c2) + wd * p['k2']; g['b2'] = dr2.sum((0, 1, 2))
        dcol2 = dr2 @ p['k2'].T
        dx2 = col2im(dcol2, x2.shape, 3, 1)
        dq1 = dx2.transpose(0, 2, 3, 1)
        mask1 = (r1.reshape(N, 12, 2, 8, 2, self.c1) == q1[:, :, None, :, None, :])
        dr1 = (mask1 * dq1[:, :, None, :, None, :]).reshape(r1.shape); dr1[a1 <= 0] = 0
        g['k1'] = col1.reshape(-1, 25).T @ dr1.reshape(-1, self.c1) + wd * p['k1']; g['b1'] = dr1.sum((0, 1, 2))
        return g
