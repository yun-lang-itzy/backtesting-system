from __future__ import annotations
import numpy as np
import pandas as pd
def band(symbol, date):
    if symbol.startswith('688'):
        return .20
    if symbol.startswith(('300', '301')):
        return .20 if pd.Timestamp(date) >= pd.Timestamp('2020-08-24') else .10
    if symbol.startswith(('000', '001', '002', '003', '600', '601', '603', '605')):
        return .10
    return None


def limits(symbol, date, previous_close, previous_factor, factor):
    rate = band(symbol, date)
    if rate is None or not np.all(np.isfinite([previous_close, previous_factor, factor])) or min(previous_close, previous_factor, factor) <= 0:
        return None
    ref = previous_close * previous_factor / factor
    # Decimal half-up to one tick; small epsilon only addresses binary float noise.
    return (np.floor(ref * (1-rate)*100 + .5 + 1e-9)/100,
            np.floor(ref * (1+rate)*100 + .5 + 1e-9)/100)


def rejection(side, o, h, l, c, amount, factor, previous_close, previous_factor, symbol, date, config):
    if not np.all(np.isfinite([o,h,l,c,amount,factor])) or min(o,h,l,c,factor) <= 0:
        return 'missing_data'
    if amount <= 0:
        return 'zero_amount'
    bounds = limits(symbol, date, previous_close, previous_factor, factor)
    if bounds is None:
        return 'unknown_reference'
    if abs(factor / previous_factor - 1) > config.max_factor_jump:
        return 'factor_jump'
    if max(o,h,l,c) - min(o,h,l,c) < 1e-8:
        return 'one_price_bar'
    down, up = bounds
    if side == 'buy' and o >= up - 1e-8:
        return 'estimated_limit_up'
    if side == 'sell' and o <= down + 1e-8:
        return 'estimated_limit_down'
    return ''
