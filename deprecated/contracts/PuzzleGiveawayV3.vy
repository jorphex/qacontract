#pragma version ^0.4.3

"""
@title PuzzleGiveawayV3
@notice One-shot puzzle giveaway with a convex time-ramped ERC20 prize.
"""

interface ERC20:
    def balanceOf(_owner: address) -> uint256: view
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: nonpayable
    def transfer(_to: address, _value: uint256) -> bool: nonpayable


event Funded:
    creator: indexed(address)
    amount: uint256

event GameStarted:
    start_time: uint256
    deadline: uint256

event AnswerSubmitted:
    player: indexed(address)
    answer_hash: indexed(bytes32)
    success: bool
    prize_amount: uint256

event PrizePaid:
    winner: indexed(address)
    paid_amount: uint256
    remaining_amount: uint256

event ClawedBack:
    refund_to: indexed(address)
    amount: uint256

event GameEnded:
    reason: uint256
    winner: indexed(address)
    paid_amount: uint256
    clawed_back_amount: uint256


REASON_WON: constant(uint256) = 1
REASON_EXPIRED: constant(uint256) = 2
REASON_CANCELLED_BEFORE_START: constant(uint256) = 3
BPS: constant(uint256) = 10_000

token: public(address)
creator: public(address)
refund_to: public(address)
prompt: public(String[256])

max_amount: public(uint256)
floor_amount: public(uint256)
deadline: public(uint256)
cliff_seconds: public(uint256)
curve_exponent: public(uint256)
answer_hash: public(bytes32)

funded: public(bool)
started: public(bool)
ended: public(bool)

start_time: public(uint256)
winner: public(address)
paid_amount: public(uint256)
clawed_back_amount: public(uint256)


@deploy
def __init__(
    _token: address,
    _refund_to: address,
    _prompt: String[256],
    _max_amount: uint256,
    _floor_amount: uint256,
    _deadline: uint256,
    _cliff_seconds: uint256,
    _curve_exponent: uint256,
    _answer_hash: bytes32
):
    """
    @notice Sets immutable giveaway rules.
    @param _token ERC20 prize token.
    @param _refund_to Address that receives creator clawbacks.
    @param _prompt Public prompt players solve.
    @param _max_amount Maximum prize funded into the contract.
    @param _floor_amount Starting prize after the game begins.
    @param _deadline Last timestamp where a correct answer can win.
    @param _cliff_seconds Seconds after start where prize stays at floor.
    @param _curve_exponent Convex ramp exponent: 2 for quadratic, 3 for cubic.
    @param _answer_hash Hash of the exact winning answer string.
    """
    assert _token != empty(address), "bad token"
    assert _refund_to != empty(address), "bad refund"
    assert len(_prompt) > 0, "bad prompt"
    assert _max_amount > 0, "bad max"
    assert _floor_amount > 0, "bad floor"
    assert _floor_amount <= _max_amount, "floor too high"
    assert _deadline > block.timestamp, "bad deadline"
    assert _curve_exponent == 2 or _curve_exponent == 3, "bad curve"
    assert _answer_hash != empty(bytes32), "bad answer"

    self.token = _token
    self.creator = msg.sender
    self.refund_to = _refund_to
    self.prompt = _prompt
    self.max_amount = _max_amount
    self.floor_amount = _floor_amount
    self.deadline = _deadline
    self.cliff_seconds = _cliff_seconds
    self.curve_exponent = _curve_exponent
    self.answer_hash = _answer_hash


@internal
@view
def _token_balance() -> uint256:
    return staticcall ERC20(self.token).balanceOf(self)


@internal
@view
def _curve_bps(_progress_bps: uint256) -> uint256:
    squared_bps: uint256 = _progress_bps * _progress_bps // BPS
    if self.curve_exponent == 2:
        return squared_bps

    return squared_bps * _progress_bps // BPS


@internal
@view
def _claimable_amount() -> uint256:
    if not self.started or self.ended:
        return 0

    if block.timestamp > self.deadline:
        return 0

    if block.timestamp == self.deadline:
        return self.max_amount

    ramp_start: uint256 = self.start_time + self.cliff_seconds
    if block.timestamp <= ramp_start:
        return self.floor_amount

    if self.floor_amount == self.max_amount:
        return self.max_amount

    elapsed: uint256 = block.timestamp - ramp_start
    duration: uint256 = self.deadline - ramp_start
    progress_bps: uint256 = elapsed * BPS // duration
    curve_bps: uint256 = self._curve_bps(progress_bps)

    return self.floor_amount + (
        (self.max_amount - self.floor_amount) * curve_bps // BPS
    )


@external
def fund():
    """
    @notice Pulls the maximum prize from the creator into this contract.
    """
    assert msg.sender == self.creator, "not creator"
    assert not self.funded, "already funded"
    assert not self.ended, "ended"

    balance_before: uint256 = self._token_balance()

    ok: bool = extcall ERC20(self.token).transferFrom(
        msg.sender,
        self,
        self.max_amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    balance_after: uint256 = self._token_balance()
    assert balance_after >= balance_before + self.max_amount, "underfunded"

    self.funded = True

    log Funded(creator=msg.sender, amount=self.max_amount)


@external
def start_game():
    """
    @notice Starts the giveaway timer after the prize has been funded.
    """
    assert msg.sender == self.creator, "not creator"
    assert self.funded, "not funded"
    assert not self.started, "already started"
    assert not self.ended, "ended"
    assert block.timestamp < self.deadline, "expired"
    if self.floor_amount < self.max_amount:
        assert block.timestamp + self.cliff_seconds < self.deadline, "cliff too long"

    self.started = True
    self.start_time = block.timestamp

    log GameStarted(start_time=block.timestamp, deadline=self.deadline)


@external
def submit_answer(_answer: String[128]):
    """
    @notice Submits an answer and pays the current prize if correct.
    @param _answer Exact answer string.
    """
    assert self.funded, "not funded"
    assert self.started, "not started"
    assert not self.ended, "ended"
    assert block.timestamp <= self.deadline, "expired"

    submitted_answer_hash: bytes32 = keccak256(convert(_answer, Bytes[128]))
    if submitted_answer_hash != self.answer_hash:
        log AnswerSubmitted(
            player=msg.sender,
            answer_hash=submitted_answer_hash,
            success=False,
            prize_amount=0,
        )
        return

    prize_amount: uint256 = self._claimable_amount()

    self.ended = True
    self.winner = msg.sender
    self.paid_amount = prize_amount

    ok: bool = extcall ERC20(self.token).transfer(
        msg.sender,
        prize_amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    remaining: uint256 = self._token_balance()

    log AnswerSubmitted(
        player=msg.sender,
        answer_hash=submitted_answer_hash,
        success=True,
        prize_amount=prize_amount,
    )
    log PrizePaid(
        winner=msg.sender,
        paid_amount=prize_amount,
        remaining_amount=remaining,
    )
    log GameEnded(
        reason=REASON_WON,
        winner=msg.sender,
        paid_amount=prize_amount,
        clawed_back_amount=0,
    )


@external
def clawback():
    """
    @notice Returns available contract funds to the refund address when allowed.
    """
    assert msg.sender == self.creator, "not creator"

    ended_now: bool = False
    reason: uint256 = 0

    if not self.started:
        if self.funded and not self.ended:
            self.ended = True
            ended_now = True
            reason = REASON_CANCELLED_BEFORE_START
    elif not self.ended:
        assert block.timestamp > self.deadline, "not expired"
        self.ended = True
        ended_now = True
        reason = REASON_EXPIRED

    amount: uint256 = self._token_balance()
    assert amount > 0, "nothing to claw back"

    self.clawed_back_amount += amount

    ok: bool = extcall ERC20(self.token).transfer(
        self.refund_to,
        amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    log ClawedBack(refund_to=self.refund_to, amount=amount)

    if ended_now:
        log GameEnded(
            reason=reason,
            winner=empty(address),
            paid_amount=0,
            clawed_back_amount=amount,
        )


@external
@view
def claimable_amount() -> uint256:
    """
    @notice Returns the prize amount currently available to a correct answer.
    """
    return self._claimable_amount()


@external
@view
def remaining_amount() -> uint256:
    """
    @notice Returns this contract's current prize token balance.
    """
    return self._token_balance()


@external
@view
def is_active() -> bool:
    """
    @notice Returns true while answers can currently win.
    """
    return (
        self.funded
        and self.started
        and not self.ended
        and block.timestamp <= self.deadline
    )


@external
@view
def is_expired() -> bool:
    """
    @notice Returns true after the answer deadline has passed.
    """
    return self.started and block.timestamp > self.deadline


@external
@view
def is_ended() -> bool:
    """
    @notice Returns true after a win, cancellation, or expired clawback.
    """
    return self.ended
