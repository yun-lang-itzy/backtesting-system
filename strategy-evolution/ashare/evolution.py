"""Evaluate a frozen strategy or a local variation under one execution contract."""
from pathlib import Path
import numpy as np
import pandas as pd
from .config import Config
from .data import load_data, sha256
from .engine import simulate
from .factors import TEMPLATES, template_source
from .report import summarize
from .strategy import Strategy, validate_weights
from .universe import StatusFilter


def prepare_period(exp, holdout=False):
    settings = exp['settings']
    if settings.get('strict'):
        raise ValueError('当前数据无法支持严格成交模式')
    data, audit = load_data(Path(settings['data']))
    fingerprint = {k: audit[k]['sha256'] for k in data}
    exclusions = settings.get('exclusions')
    if exclusions:
        fingerprint['exclusions'] = sha256(exclusions)
    if exp.get('fingerprint', fingerprint) != fingerprint:
        raise ValueError('行情或排除清单已变化，请新建实验')
    split = pd.Timestamp(exp['split'])
    start = split + pd.Timedelta(days=1) if holdout else pd.Timestamp(settings['start'])
    end = pd.Timestamp(settings['end']) if holdout else split
    symbols = settings['symbols'] or data['close'].columns
    data = {k: v.loc[:end, symbols] for k, v in data.items()}
    if len(data['close'].loc[start:end]) < 2:
        raise ValueError('本区间至少需要两个交易日')
    config = Config(**settings['engine'])
    status = StatusFilter(exclusions or None, settings['unknown_status_policy'])
    scope = {'__name__': 'user_strategy'}
    exec(compile(exp['source'], 'strategy.py', 'exec'), scope)
    cls = scope['UserStrategy']
    if not issubclass(cls, Strategy):
        raise ValueError('UserStrategy 必须继承 Strategy')
    return fingerprint, data, config, start, end, status, cls


def evaluate_versions(exp, versions, holdout=False, prepared=None):
    fingerprint, data, config, start, end, status, cls = prepared or prepare_period(exp, holdout)
    results = []
    for version in versions:
        strategy = cls(**version['params'])
        if version.get('factor'):
            strategy = FactorTilt(strategy, version['factor'])
        frames = simulate(data, config, strategy, start, end, status_filter=status)
        summary = summarize(frames, config)
        if isinstance(strategy, FactorTilt):
            summary.update(strategy.diagnostics(data, start, end))
        results.append(summary)
    return fingerprint, results


class FactorTilt(Strategy):
    """Tilt existing targets by cross-sectional factor rank, preserving exposure caps."""
    def __init__(self, base, name):
        self.base = base
        kind, self.window, self.skip, self.higher = TEMPLATES[name]
        scope = {}
        exec(template_source(kind), scope)
        self.factor = scope['factor']
        self.samples = []

    def on_close(self, context):
        targets = self.base.on_close(context)
        if not targets:
            return targets
        validate_weights(targets, context.symbols)
        if len(context.history('close', self.window + self.skip + 1)) < self.window + self.skip + 1:
            return targets
        scores = self.factor(context, self.window, self.skip).reindex(targets)
        ranks = scores.replace([np.inf, -np.inf], np.nan).rank(pct=True, ascending=self.higher)
        weights = pd.Series(targets, dtype=float)
        tilted = weights * ranks.fillna(1.)
        self.samples.append((context.date, pd.concat(
            [ranks.rename('factor'), weights.rename('base'), tilted.rename('combined')], axis=1)))
        return tilted.to_dict()

    def diagnostics(self, data, start, end):
        prices = data['open'] * data['cumadj']
        forward = prices.shift(-6) / prices.shift(-1) - 1
        values = {'factor': [], 'increment': [], 'correlation': []}
        for day, snapshot in self.samples:
            if day < start or day > end:
                continue
            frame = snapshot.join(forward.loc[day].rename('label')).dropna().rank()
            if len(frame) < 3 or frame.label.nunique() < 2:
                continue
            corr = frame.corr()
            values['factor'].append(corr.loc['factor','label'])
            values['increment'].append(corr.loc['combined','label'] - corr.loc['base','label'])
            values['correlation'].append(corr.loc['factor','base'])
        return {key: float(np.nanmean(v)) if np.isfinite(v).any() else None
                for key, v in values.items()}


def verdict(value, baseline, exp):
    if value['trades'] == 0 or baseline['trades'] == 0:
        return '证据不足：无成交'
    if value[exp['metric']] <= baseline[exp['metric']]:
        return '淘汰：主指标未改善'
    if baseline['max_drawdown'] - value['max_drawdown'] > exp['dd_limit']:
        return '淘汰：回撤增幅超过上限'
    return '通过'
