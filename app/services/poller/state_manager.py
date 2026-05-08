from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict


class DedupSet:
    """Optimized deduplication set with O(1) operations using OrderedDict"""

    def __init__(self, maxlen: int = 2000) -> None:
        self._maxlen = maxlen
        self._data: OrderedDict[str, None] = OrderedDict()

    def add(self, key: str) -> bool:
        """Add key to set. Returns True if key was added, False if already exists"""
        if key in self._data:
            return False
        self._data[key] = None
        if len(self._data) > self._maxlen:
            self._data.popitem(last=False)  # O(1) removal of oldest item
        return True

    def __contains__(self, key: str) -> bool:
        """Check if key exists in set"""
        return key in self._data

    def __len__(self) -> int:
        """Get number of items in set"""
        return len(self._data)


@dataclass
class AccountLeaderState:
    """State tracking for a single account-leader subscription"""

    last_order_time: int
    last_detail_refresh: int = 0
    leader_margin: float = 0.0
    leader_aum: float = 0.0
    follower_equity: float = 0.0
    last_follower_equity_refresh: int = 0
    dedup: DedupSet = field(default_factory=DedupSet)
    positions: Dict[str, float] = field(default_factory=dict)
    follower_positions: Dict[str, float] = field(default_factory=dict)
    last_fetch_at: int = 0
    last_fetch_ok: bool = False
    last_fetch_error: str = ""
    last_fetch_auth_error: bool = False
    backoff_ms: int = 0
    last_debug_log_at: int = 0
    last_position_refresh: int = 0
    last_positions_log_at: int = 0
    positions_snapshot: list[Dict[str, object]] = field(default_factory=list)
    positions_hash: str = ""
    closed_positions_seen: Dict[str, int] = field(default_factory=dict)

    # Position monitoring
    leader_current_positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    position_show: bool = True
    position_hidden_notified: bool = False
    empty_positions_hits: int = 0
    api_empty_notified: bool = False
    position_signature_hits: Dict[str, int] = field(default_factory=dict)
    position_signature: Dict[str, str] = field(default_factory=dict)
    position_missing_hits: Dict[str, int] = field(default_factory=dict)
    first_run: bool = True
    initial_positions_copied: bool = False

    # Rolling window of fetch_positions() latency samples in milliseconds.
    # Round 2: surfaced via /api/leaders and /api/health/poller for ops UX.
    poll_latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=20))

    # Rolling window of leader equity samples (margin or AUM, whichever is
    # available) used to render the trader-card sparkline + recent PnL %.
    # Each entry is the latest non-zero leader equity seen during a
    # _refresh_detail tick. Bounded to the last 30 samples so memory stays
    # constant per project.
    equity_history: Deque[float] = field(default_factory=lambda: deque(maxlen=30))


# Backward compatibility alias
ProjectState = AccountLeaderState
