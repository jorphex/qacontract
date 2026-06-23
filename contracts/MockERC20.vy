#pragma version ^0.4.3

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256


name: public(String[32])
symbol: public(String[8])
decimals: public(uint8)
totalSupply: public(uint256)

balanceOf: public(HashMap[address, uint256])
allowance: public(HashMap[address, HashMap[address, uint256]])


@deploy
def __init__(_name: String[32], _symbol: String[8], _decimals: uint8):
    self.name = _name
    self.symbol = _symbol
    self.decimals = _decimals


@external
def mint(_to: address, _amount: uint256):
    assert _to != empty(address), "bad recipient"

    self.balanceOf[_to] += _amount
    self.totalSupply += _amount

    log Transfer(empty(address), _to, _amount)


@external
def approve(_spender: address, _amount: uint256) -> bool:
    self.allowance[msg.sender][_spender] = _amount

    log Approval(msg.sender, _spender, _amount)

    return True


@external
def transfer(_to: address, _amount: uint256) -> bool:
    assert _to != empty(address), "bad recipient"
    assert self.balanceOf[msg.sender] >= _amount, "insufficient balance"

    self.balanceOf[msg.sender] -= _amount
    self.balanceOf[_to] += _amount

    log Transfer(msg.sender, _to, _amount)

    return True


@external
def transferFrom(_from: address, _to: address, _amount: uint256) -> bool:
    assert _to != empty(address), "bad recipient"
    assert self.balanceOf[_from] >= _amount, "insufficient balance"
    assert self.allowance[_from][msg.sender] >= _amount, "insufficient allowance"

    self.allowance[_from][msg.sender] -= _amount
    self.balanceOf[_from] -= _amount
    self.balanceOf[_to] += _amount

    log Transfer(_from, _to, _amount)

    return True

