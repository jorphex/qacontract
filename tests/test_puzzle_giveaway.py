import ape
from eth_utils import keccak


AMOUNT = 1_000_000
FLOOR = 250_000
CLIFF = 300
ANSWER = "blue candle"
WRONG_ANSWER = "red candle"
REASON_WON = 1
REASON_EXPIRED = 2
REASON_CANCELLED_BEFORE_START = 3


def deploy_game(project, accounts, chain, floor=FLOOR, cliff=CLIFF, deadline_offset=3600):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    game = project.PuzzleGiveaway.deploy(
        token.address,
        refund_to.address,
        AMOUNT,
        floor,
        chain.pending_timestamp + deadline_offset,
        cliff,
        keccak(text=ANSWER),
        sender=creator,
    )
    return token, game


def fund_game(token, game, creator):
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)


def test_main_flow_records_wrong_answer_pays_winner_and_claws_back_leftover(
    project, accounts, chain
):
    creator = accounts[0]
    solver = accounts[1]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)

    assert game.claimable_amount() == 0
    assert not game.is_active()

    fund_game(token, game, creator)

    with ape.reverts("not started"):
        game.submit_answer(ANSWER, sender=solver)

    game.start_game(sender=creator)

    assert game.is_active()
    assert game.claimable_amount() == FLOOR

    wrong_receipt = game.submit_answer(WRONG_ANSWER, sender=solver)
    wrong_attempts = list(wrong_receipt.decode_logs(game.AnswerSubmitted))

    assert not game.ended()
    assert token.balanceOf(solver) == 0
    assert len(wrong_attempts) == 1
    assert wrong_attempts[0].player == solver.address
    assert wrong_attempts[0].answer_hash == keccak(text=WRONG_ANSWER)
    assert not bool(wrong_attempts[0].success)
    assert wrong_attempts[0].prize_amount == 0

    chain.pending_timestamp = game.start_time() + 1800
    chain.mine()

    prize_before_submit = game.claimable_amount()
    assert FLOOR < prize_before_submit < AMOUNT

    claim_receipt = game.submit_answer(ANSWER, sender=solver)
    paid_events = list(claim_receipt.decode_logs(game.PrizePaid))
    ended_events = list(claim_receipt.decode_logs(game.GameEnded))
    paid_amount = game.paid_amount()

    assert game.ended()
    assert game.winner() == solver.address
    assert prize_before_submit <= paid_amount < AMOUNT
    assert token.balanceOf(solver) == paid_amount
    assert len(paid_events) == 1
    assert paid_events[0].paid_amount == paid_amount
    assert paid_events[0].remaining_amount == AMOUNT - paid_amount
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_WON

    game.clawback(sender=creator)

    assert token.balanceOf(refund_to) == AMOUNT - paid_amount
    assert game.remaining_amount() == 0


def test_creator_can_cancel_and_claw_back_before_start(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)

    receipt = game.clawback(sender=creator)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert token.balanceOf(refund_to) == AMOUNT
    assert game.remaining_amount() == 0
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_CANCELLED_BEFORE_START


def test_expiry_blocks_answers_then_allows_clawback(project, accounts, chain):
    creator = accounts[0]
    solver = accounts[1]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()

    assert game.claimable_amount() == 0
    assert game.is_expired()

    with ape.reverts("expired"):
        game.submit_answer(ANSWER, sender=solver)

    receipt = game.clawback(sender=creator)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert token.balanceOf(refund_to) == AMOUNT
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_EXPIRED


def test_correct_answer_can_win_at_exact_deadline(project, accounts, chain):
    creator = accounts[0]
    solver = accounts[1]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    chain.pending_timestamp = game.deadline()

    game.submit_answer(ANSWER, sender=solver)

    assert game.ended()
    assert game.winner() == solver.address
    assert token.balanceOf(solver) == AMOUNT


def test_creator_can_recover_direct_transfer_before_funding(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    token.transfer(game.address, 123, sender=creator)

    game.clawback(sender=creator)

    assert not game.ended()
    assert token.balanceOf(refund_to) == 123
    assert game.remaining_amount() == 0


def test_fixed_prize_can_start_with_long_cliff(project, accounts, chain):
    creator = accounts[0]
    token, game = deploy_game(
        project,
        accounts,
        chain,
        floor=AMOUNT,
        cliff=10_000,
        deadline_offset=3600,
    )
    fund_game(token, game, creator)

    game.start_game(sender=creator)

    assert game.claimable_amount() == AMOUNT
