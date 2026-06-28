#pragma version ^0.4.3

"""
@title KingOfTheHillGiveaway
@notice Limited-shot ERC20 king-of-the-hill giveaway where each answer captures the hill.
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

event Shot:
    player: indexed(address)
    previous_king: indexed(address)
    sequence: uint256
    shots_used: uint256
    captured_at: uint256

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
REASON_NO_CORRECT_REIGN: constant(uint256) = 2
REASON_CANCELLED_BEFORE_START: constant(uint256) = 3
BPS: constant(uint256) = 10_000

token: public(address)
creator: public(address)
refund_to: public(address)
prompt: public(String[256])

max_amount: public(uint256)
floor_amount: public(uint256)
deadline: public(uint256)
max_shots: public(uint256)
curve_exponent: public(uint256)
answer_hash: public(bytes32)

funded: public(bool)
started: public(bool)
ended: public(bool)

start_time: public(uint256)
game_duration: public(uint256)
king: public(address)
king_since: public(uint256)
shot_sequence: public(uint256)

winner: public(address)
paid_amount: public(uint256)
clawed_back_amount: public(uint256)

shots_used: public(HashMap[address, uint256])

king_answer_hash: bytes32
candidate_winner: address
candidate_prize_amount: uint256


@deploy
def __init__(
    _token: address,
    _refund_to: address,
    _prompt: String[256],
    _max_amount: uint256,
    _floor_amount: uint256,
    _deadline: uint256,
    _max_shots: uint256,
    _curve_exponent: uint256,
    _answer_hash: bytes32
):
    """
    @notice Sets immutable game rules.
    @param _token ERC20 prize token.
    @param _refund_to Address that receives creator clawbacks.
    @param _prompt Public prompt players answer when shooting.
    @param _max_amount Maximum prize funded into the contract.
    @param _floor_amount Minimum prize for any winning reign.
    @param _deadline Timestamp when shooting expires.
    @param _max_shots Maximum shots each address can take.
    @param _curve_exponent Prize growth exponent: 1 linear, 2 quadratic, 3 cubic.
    @param _answer_hash Hash of the exact winning answer string.
    """
    assert _token != empty(address), "bad token"
    assert _refund_to != empty(address), "bad refund"
    assert len(_prompt) > 0, "bad prompt"
    assert _max_amount > 0, "bad max"
    assert _floor_amount > 0, "bad floor"
    assert _floor_amount <= _max_amount, "floor too high"
    assert _deadline > block.timestamp, "bad deadline"
    assert _max_shots > 0, "bad shots"
    assert _curve_exponent >= 1 and _curve_exponent <= 3, "bad curve"
    assert _answer_hash != empty(bytes32), "bad answer"

    self.token = _token
    self.creator = msg.sender
    self.refund_to = _refund_to
    self.prompt = _prompt
    self.max_amount = _max_amount
    self.floor_amount = _floor_amount
    self.deadline = _deadline
    self.max_shots = _max_shots
    self.curve_exponent = _curve_exponent
    self.answer_hash = _answer_hash


@internal
@view
def _token_balance() -> uint256:
    return staticcall ERC20(self.token).balanceOf(self)


@internal
@view
def _curve_bps(_progress_bps: uint256) -> uint256:
    if self.curve_exponent == 1:
        return _progress_bps

    squared_bps: uint256 = _progress_bps * _progress_bps // BPS
    if self.curve_exponent == 2:
        return squared_bps

    return squared_bps * _progress_bps // BPS


@internal
@view
def _reign_prize(_since: uint256, _until: uint256) -> uint256:
    if _since == 0 or _until < _since:
        return 0

    if self.floor_amount == self.max_amount:
        return self.max_amount

    if self.game_duration == 0:
        return 0

    elapsed: uint256 = _until - _since
    if elapsed >= self.game_duration:
        return self.max_amount

    progress_bps: uint256 = elapsed * BPS // self.game_duration
    curve_bps: uint256 = self._curve_bps(progress_bps)

    return self.floor_amount + (
        (self.max_amount - self.floor_amount) * curve_bps // BPS
    )


@internal
def _record_current_reign(_ended_at: uint256):
    if self.king == empty(address):
        return

    if self.king_answer_hash != self.answer_hash:
        return

    prize_amount: uint256 = self._reign_prize(self.king_since, _ended_at)

    self.candidate_winner = self.king
    self.candidate_prize_amount = prize_amount


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
    @notice Starts the king-of-the-hill timer after funding.
    """
    assert msg.sender == self.creator, "not creator"
    assert self.funded, "not funded"
    assert not self.started, "already started"
    assert not self.ended, "ended"
    assert block.timestamp < self.deadline, "expired"

    self.started = True
    self.start_time = block.timestamp
    self.game_duration = self.deadline - block.timestamp

    log GameStarted(start_time=block.timestamp, deadline=self.deadline)


@external
def shoot(_answer: String[128]):
    """
    @notice Uses one shot to capture the hill with an answer.
    @param _answer Exact answer string for this reign.
    """
    assert self.funded, "not funded"
    assert self.started, "not started"
    assert not self.ended, "ended"
    assert block.timestamp <= self.deadline, "expired"
    assert self.shots_used[msg.sender] < self.max_shots, "out of shots"

    self._record_current_reign(block.timestamp)

    previous_king: address = self.king
    next_shots_used: uint256 = self.shots_used[msg.sender] + 1
    next_sequence: uint256 = self.shot_sequence + 1

    self.shots_used[msg.sender] = next_shots_used
    self.shot_sequence = next_sequence
    self.king = msg.sender
    self.king_since = block.timestamp
    self.king_answer_hash = keccak256(convert(_answer, Bytes[128]))

    log Shot(
        player=msg.sender,
        previous_king=previous_king,
        sequence=next_sequence,
        shots_used=next_shots_used,
        captured_at=block.timestamp,
    )


@external
def finalize():
    """
    @notice Ends the game after expiry and pays the latest correct reign.
    """
    assert self.funded, "not funded"
    assert self.started, "not started"
    assert not self.ended, "ended"
    assert block.timestamp > self.deadline, "not expired"

    self._record_current_reign(self.deadline)
    self.ended = True

    if self.candidate_winner == empty(address):
        log GameEnded(
            reason=REASON_NO_CORRECT_REIGN,
            winner=empty(address),
            paid_amount=0,
            clawed_back_amount=0,
        )
        return

    prize_amount: uint256 = self.candidate_prize_amount
    self.winner = self.candidate_winner
    self.paid_amount = prize_amount

    ok: bool = extcall ERC20(self.token).transfer(
        self.candidate_winner,
        prize_amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    remaining: uint256 = self._token_balance()

    log PrizePaid(
        winner=self.candidate_winner,
        paid_amount=prize_amount,
        remaining_amount=remaining,
    )
    log GameEnded(
        reason=REASON_WON,
        winner=self.candidate_winner,
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
    if not self.started:
        if self.funded and not self.ended:
            self.ended = True
            ended_now = True
    else:
        assert self.ended, "not ended"

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
            reason=REASON_CANCELLED_BEFORE_START,
            winner=empty(address),
            paid_amount=0,
            clawed_back_amount=amount,
        )


@external
@view
def king_prize() -> uint256:
    """
    @notice Returns the current hill prize if the visible king held until now.
    """
    if self.king == empty(address):
        return 0

    until: uint256 = block.timestamp
    if until > self.deadline:
        until = self.deadline

    return self._reign_prize(self.king_since, until)


@external
@view
def prize_at(_since: uint256, _until: uint256) -> uint256:
    """
    @notice Returns the prize for a hypothetical reign window.
    """
    return self._reign_prize(_since, _until)


@external
@view
def shots_remaining(_player: address) -> uint256:
    """
    @notice Returns shots left for a player address.
    """
    used: uint256 = self.shots_used[_player]
    if used >= self.max_shots:
        return 0

    return self.max_shots - used


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
    @notice Returns true while shots can currently capture the hill.
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
    @notice Returns true after the shooting deadline has passed.
    """
    return self.started and block.timestamp > self.deadline


@external
@view
def is_ended() -> bool:
    """
    @notice Returns true after cancellation or finalization.
    """
    return self.ended
