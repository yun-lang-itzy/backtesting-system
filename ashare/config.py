from dataclasses import dataclass
@dataclass(frozen=True)
class Config:
    initial_cash: float = 1_000_000
    lookback: int = 20
    top_n: int = 20
    min_adv: float = 20_000_000  # Assumes amt is CNY, not vendor-confirmed.
    participation: float = .001
    fee_bps: float = 3
    sell_extra_bps: float = 5  # Constant scenario cost, NOT historical tax rules.
    slippage_bps: float = 5
    max_factor_jump: float = .30
    terminal_mode: str = 'hold'  # hold / liquidate / settle
    entry_mode: str = 'scheduled'  # scheduled / first_open
