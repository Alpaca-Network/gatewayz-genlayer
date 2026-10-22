"""Off-chain ledger escrow for card-funded users (plan P2, "ledger rail").

Reference model of the money states that the backend ports to `credit_transactions`.
Double-entry: every movement is one journal row (debit, credit, amount, memo), and a
balance is the sum of its rows, so money is conserved by construction. Amounts are
integer nano-USD, as in gzgl/billing.py.

Accounts
    user:<id>:available   spendable credit
    user:<id>:pending     billed lines inside an open or unfinalized epoch
    user:<id>:held        lines under dispute, waiting for a FINALIZED verdict
    user:<id>:bond        dispute bonds
    provider:<id>:payable owed to an open provider (paid in arrears, after the window)
    gatewayz:upstream     recoups what Gatewayz prepaid a lab for an underwritten line
    gatewayz:reserve      clawback reserve, funded by the escrow fee; may go negative
    gatewayz:fees         forfeited bonds (they pay for adjudication)
    external:card         money in from card top-ups

Who pays a clawback
    provider  open providers that accepted terms: their line is still unpaid, so the
              refund simply never reaches them.
    reserve   lab models Gatewayz chose to underwrite: the lab was paid upfront, so the
              refund is made whole from the reserve. Only on the terms' allowlist, and
              for a much higher fee.
    Anything else is billed without escrow and cannot be disputed.

A verdict is applied only as the relayer read it from FINALIZED GenLayer state; the
ledger re-checks that it covers exactly the disputed lines at the billed amounts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gzgl.billing import NANO, to_nano

DAY = 86_400
_PERIOD = 30 * DAY


class LedgerError(ValueError):
    pass


@dataclass(frozen=True)
class EscrowTerms:
    window_s: int = 3 * DAY                      # challenge window after epoch close
    adjudication_s: int = 2 * DAY                # verdict expected within this after a dispute opens
    bond_min_nano: int = 1 * NANO                # max($1, 10% of contested)
    bond_bps: int = 1_000
    fee_bps: dict = field(default_factory=lambda: {"provider": 100, "reserve": 1_000})
    open_providers: frozenset = frozenset()      # accept clawbacks, paid in arrears
    underwritten_models: frozenset = frozenset() # lab models Gatewayz underwrites
    refund_cap_nano: int = 50 * NANO             # per user per 30-day period
    allowed_policies: frozenset = frozenset()


@dataclass
class Line:
    cost: int
    fee: int
    provider: str
    clawback: str      # "provider" | "reserve" | "" (not escrowed)
    state: str         # pending | held | paid | settled


@dataclass
class Epoch:
    user: str
    lines: list = field(default_factory=list)
    usage_root: str = ""
    closed_at: int | None = None
    finalized: bool = False


@dataclass
class Dispute:
    user: str
    epoch_id: str
    indexes: tuple
    bond: int
    opened_at: int
    status: str = "open"   # open | settled
    refund: int = 0


class Ledger:
    def __init__(self, terms: EscrowTerms):
        self.terms = terms
        self.journal: list[tuple[str, str, int, str]] = []
        self.epochs: dict[str, Epoch] = {}
        self.disputes: dict[str, Dispute] = {}
        self._refunded: dict[tuple[str, int], int] = {}

    # ---------------------------------------------------------------- books

    def _move(self, debit: str, credit: str, amount: int, memo: str) -> None:
        if amount < 0:
            raise LedgerError("negative amount")
        if amount:
            self.journal.append((debit, credit, amount, memo))

    def balance(self, account: str) -> int:
        return sum(a for _, c, a, _ in self.journal if c == account) - sum(
            a for d, _, a, _ in self.journal if d == account)

    def balances(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d, c, a, _ in self.journal:
            out[d] = out.get(d, 0) - a
            out[c] = out.get(c, 0) + a
        return {k: v for k, v in sorted(out.items()) if v}

    def _spend(self, user: str, to: str, amount: int, memo: str) -> None:
        if self.balance(f"user:{user}:available") < amount:
            raise LedgerError("insufficient_credit")
        self._move(f"user:{user}:available", to, amount, memo)

    # ---------------------------------------------------------------- flow

    def deposit(self, user: str, usd: str) -> None:
        self._move("external:card", f"user:{user}:available", to_nano(usd), "top-up")

    def clawback_source(self, entry: dict) -> str:
        if entry["provider"] in self.terms.open_providers:
            return "provider"
        if entry["model"] in self.terms.underwritten_models:
            return "reserve"
        return ""

    def charge(self, epoch_id: str, user: str, entry: dict) -> int:
        """Bill one usage entry. Returns its index, which must match gzgl.billing.Epoch."""
        ep = self.epochs.setdefault(epoch_id, Epoch(user))
        if ep.user != user or ep.closed_at is not None:
            raise LedgerError("epoch_not_open")
        cost, source = to_nano(entry["cost_usd"]), self.clawback_source(entry)
        idx = len(ep.lines)
        memo = f"{epoch_id}:{idx}"
        if source:
            fee = cost * self.terms.fee_bps[source] // 10_000
            self._spend(user, f"user:{user}:pending", cost, memo)
            self._spend(user, "gatewayz:reserve", fee, memo + " escrow fee")
            ep.lines.append(Line(cost, fee, entry["provider"], source, "pending"))
        else:
            self._spend(user, self._payee(entry["provider"], ""), cost, memo)
            ep.lines.append(Line(cost, 0, entry["provider"], "", "paid"))
        return idx

    def close_epoch(self, epoch_id: str, usage_root: str, now: int) -> None:
        ep = self._epoch(epoch_id)
        if ep.closed_at is not None:
            raise LedgerError("epoch_closed")
        ep.usage_root, ep.closed_at = usage_root.lower(), now

    def open_dispute(self, dispute_id: str, epoch_id: str, indexes: list[int], now: int) -> int:
        """Hold the contested lines and take the bond. Returns the bond (nano-USD)."""
        ep = self._epoch(epoch_id)
        if dispute_id.lower() in self.disputes:
            raise LedgerError("dispute_exists")
        if ep.closed_at is None or now >= ep.closed_at + self.terms.window_s or ep.finalized:
            raise LedgerError("dispute_window_closed")
        if not indexes or len(set(indexes)) != len(indexes):
            raise LedgerError("invalid_lines")
        for i in indexes:
            if not 0 <= i < len(ep.lines):
                raise LedgerError("invalid_lines")
            if not ep.lines[i].clawback:
                raise LedgerError("line_not_escrowed")
            if ep.lines[i].state != "pending":
                raise LedgerError("line_already_disputed")
        contested = sum(ep.lines[i].cost for i in indexes)
        bond = max(self.terms.bond_min_nano, contested * self.terms.bond_bps // 10_000)
        self._spend(ep.user, f"user:{ep.user}:bond", bond, f"{dispute_id} bond")
        for i in indexes:
            self._move(f"user:{ep.user}:pending", f"user:{ep.user}:held", ep.lines[i].cost, f"{dispute_id} hold {i}")
            ep.lines[i].state = "held"
        self.disputes[dispute_id.lower()] = Dispute(ep.user, epoch_id, tuple(sorted(indexes)), bond, now)
        return bond

    def apply_verdict(self, verdict: dict) -> int:
        """Settle a dispute from a FINALIZED CostDispute verdict. Returns the refund paid."""
        did = str(verdict.get("dispute_id", "")).lower()
        d = self.disputes.get(did)
        if d is None:
            raise LedgerError("unknown_dispute")
        if d.status != "open":
            raise LedgerError("dispute_settled")
        ep = self.epochs[d.epoch_id]
        if str(verdict.get("epoch_id", "")).lower() != d.epoch_id.lower() or \
                str(verdict.get("usage_root", "")).lower() != ep.usage_root:
            raise LedgerError("verdict_mismatch: epoch")
        if str(verdict.get("policy_hash", "")).lower() not in self.terms.allowed_policies:
            raise LedgerError("verdict_mismatch: policy")
        rows = {int(r["line"]): r for r in verdict.get("lines", [])}
        if tuple(sorted(rows)) != d.indexes:
            raise LedgerError("verdict_mismatch: lines")
        refunds = {}
        for i, r in rows.items():
            billed, bps = to_nano(r["billed_usd"]), int(r["refund_bps"])
            if billed != ep.lines[i].cost or not 0 <= bps <= 10_000 or \
                    to_nano(r["refund_usd"]) != billed * bps // 10_000:
                raise LedgerError(f"verdict_mismatch: line {i}")
            refunds[i] = billed * bps // 10_000

        period = (d.user, ep.closed_at // _PERIOD)
        room = max(0, self.terms.refund_cap_nano - self._refunded.get(period, 0))
        total = 0
        for i in d.indexes:
            line, refund = ep.lines[i], min(refunds[i], room - total)
            held = f"user:{d.user}:held"
            self._move(held, f"user:{d.user}:available", refund, f"{did} refund {i}")
            self._move(held, self._payee(line.provider, line.clawback), line.cost - refund, f"{did} release {i}")
            if line.clawback == "reserve":
                self._move("gatewayz:reserve", "gatewayz:upstream", refund, f"{did} underwrite {i}")
            line.state = "settled"
            total += refund
        self._refunded[period] = self._refunded.get(period, 0) + total
        # A dispute that wins anything gets its bond back (even if the cap cut the refund);
        # a dispute that wins nothing pays for adjudication.
        won = any(refunds.values())
        self._move(f"user:{d.user}:bond", f"user:{d.user}:available" if won else "gatewayz:fees", d.bond, f"{did} bond")
        d.status, d.refund = "settled", total
        return total

    def finalize_epoch(self, epoch_id: str, now: int) -> int:
        """After the window: pay out every undisputed line. Returns the amount released."""
        ep = self._epoch(epoch_id)
        if ep.closed_at is None or now < ep.closed_at + self.terms.window_s:
            raise LedgerError("window_open")
        if ep.finalized:
            return 0
        released = 0
        for i, line in enumerate(ep.lines):
            if line.state == "pending":
                self._move(f"user:{ep.user}:pending", self._payee(line.provider, line.clawback), line.cost, f"{epoch_id}:{i} release")
                line.state, released = "paid", released + line.cost
        ep.finalized = True
        return released

    def overdue_disputes(self, now: int) -> list[str]:
        """Open disputes past the adjudication deadline. Held money stays put; a human decides."""
        return sorted(k for k, d in self.disputes.items()
                      if d.status == "open" and now >= d.opened_at + self.terms.adjudication_s)

    # ---------------------------------------------------------------- helpers

    def _epoch(self, epoch_id: str) -> Epoch:
        if epoch_id not in self.epochs:
            raise LedgerError("unknown_epoch")
        return self.epochs[epoch_id]

    @staticmethod
    def _payee(provider: str, clawback: str) -> str:
        return f"provider:{provider}:payable" if clawback == "provider" else "gatewayz:upstream"
