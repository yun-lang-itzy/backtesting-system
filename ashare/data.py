from __future__ import annotations
import numpy as np
import pandas as pd
import hashlib
from pathlib import Path
FIELDS = ('open', 'high', 'low', 'close', 'amt', 'num_trades', 'cumadj')

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_data(root):
    data, audit = {}, {}
    for name in FIELDS:
        path = root / f'{name}.feather'
        frame = pd.read_feather(path).set_index('date')
        if not frame.index.is_unique or not frame.index.is_monotonic_increasing or not frame.columns.is_unique:
            raise ValueError('Duplicate or unordered index')
        if data:
            first = data['open']
            if not frame.index.equals(first.index) or not frame.columns.equals(first.columns):
                raise ValueError('Unaligned matrices')
        arr = frame.to_numpy(dtype=float)
        if np.isinf(arr).any() or (arr[np.isfinite(arr)] < 0).any():
            raise ValueError(f'Invalid values: {name}')
        if name not in ('amt', 'num_trades') and (arr == 0).any():
            raise ValueError(f'Zero price/factor: {name}')
        data[name] = frame
        audit[name] = dict(sha256=sha256(path), shape=list(frame.shape),
                           missing=int(frame.isna().sum().sum()), zeros=int((frame == 0).sum().sum()),
                           final_valid=int(frame.iloc[-1].notna().sum()))
    bad = ((data['high'] < data['low']) | (data['high'] < data['open']) |
           (data['high'] < data['close']) | (data['low'] > data['open']) | (data['low'] > data['close']))
    if bad.to_numpy().any():
        raise ValueError('OHLC violations')
    audit['contract'] = dict(start=str(frame.index[0]), end=str(frame.index[-1]),
        factor_convention='ASSUMED: adjusted_price = raw_price * cumadj', amt_unit='ASSUMED CNY',
        archive_hash_status='Not verified: supplied hash target archive not identified',
        supplied_archive_hash=None)
    return data, audit
