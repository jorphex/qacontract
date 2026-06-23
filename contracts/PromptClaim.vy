#pragma version ^0.4.3

interface ERC20:
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: nonpayable
    def transfer(_to: address, _value: uint256) -> bool: nonpayable


event Funded:
    creator: indexed(address)
    amount: uint256

event Claimed:
    winner: indexed(address)
    amount: uint256

event ClawedBack:
    refund_to: indexed(address)
    amount: uint256


token: public(address)
creator: public(address)
refund_to: public(address)

amount: public(uint256)
deadline: public(uint256)
answer_hash: public(bytes32)

funded: public(bool)
settled: public(bool)
winner: public(address)


@deploy
def __init__(
    _token: address,
    _refund_to: address,
    _amount: uint256,
    _deadline: uint256,
    _answer_hash: bytes32
):
    assert _token != empty(address), "bad token"
    assert _refund_to != empty(address), "bad refund"
    assert _amount > 0, "bad amount"
    assert _deadline > block.timestamp, "bad deadline"
    assert _answer_hash != empty(bytes32), "bad answer"

    self.token = _token
    self.creator = msg.sender
    self.refund_to = _refund_to
    self.amount = _amount
    self.deadline = _deadline
    self.answer_hash = _answer_hash


@external
def fund():
    assert msg.sender == self.creator, "not creator"
    assert not self.funded, "already funded"
    assert not self.settled, "settled"

    self.funded = True

    ok: bool = extcall ERC20(self.token).transferFrom(
        msg.sender,
        self,
        self.amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    log Funded(msg.sender, self.amount)


@external
def claim(_answer: Bytes[128]):
    assert self.funded, "not funded"
    assert not self.settled, "settled"
    assert block.timestamp <= self.deadline, "expired"
    assert keccak256(_answer) == self.answer_hash, "wrong answer"

    self.settled = True
    self.winner = msg.sender

    ok: bool = extcall ERC20(self.token).transfer(
        msg.sender,
        self.amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    log Claimed(msg.sender, self.amount)


@external
def clawback():
    assert msg.sender == self.creator, "not creator"
    assert self.funded, "not funded"
    assert not self.settled, "settled"
    assert block.timestamp > self.deadline, "not expired"

    self.settled = True

    ok: bool = extcall ERC20(self.token).transfer(
        self.refund_to,
        self.amount,
        default_return_value=True
    )
    assert ok, "transfer failed"

    log ClawedBack(self.refund_to, self.amount)

