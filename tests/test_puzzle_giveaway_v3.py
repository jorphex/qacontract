import ape
from eth_utils import keccak


AMOUNT = 1_000_000
FLOOR = 100_000
CLIFF = 100
PROMPT = "What color is the candle?"
ANSWER = "blue candle"
WRONG_ANSWER = "red candle"
REASON_WON = 1
REASON_EXPIRED = 2
REASON_CANCELLED_BEFORE_START = 3
BPS = 10_000


def deploy_game(
    project,
    accounts,
    chain,
    floor=FLOOR,
    cliff=CLIFF,
    deadline_offset=1_100,
    curve_exponent=2,
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    game = project.PuzzleGiveawayV3.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        floor,
        chain.pending_timestamp + deadline_offset,
        cliff,
        curve_exponent,
        keccak(text=ANSWER),
        sender=creator,
    )
    return token, game


def fund_game(token, game, creator):
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)


def expected_claimable(game, timestamp):
    if timestamp <= game.start_time() + game.cliff_seconds():
        return game.floor_amount()

    if timestamp == game.deadline():
        return game.max_amount()

    elapsed = timestamp - game.start_time() - game.cliff_seconds()
    duration = game.deadline() - game.start_time() - game.cliff_seconds()
    progress_bps = elapsed * BPS // duration
    curve_bps = progress_bps * progress_bps // BPS
    if game.curve_exponent() == 3:
        curve_bps = curve_bps * progress_bps // BPS

    return game.floor_amount() + (
        (game.max_amount() - game.floor_amount()) * curve_bps // BPS
    )


def test_quadratic_claimable_amount_is_back_loaded(project, accounts, chain):
    creator = accounts[0]
    token, game = deploy_game(project, accounts, chain, curve_exponent=2)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    ramp_midpoint = (
        game.start_time()
        + game.cliff_seconds()
        + (game.deadline() - game.start_time() - game.cliff_seconds()) // 2
    )
    chain.pending_timestamp = ramp_midpoint
    chain.mine()

    expected = expected_claimable(game, ramp_midpoint)

    assert game.curve_exponent() == 2
    assert game.claimable_amount() == expected
    assert game.claimable_amount() < FLOOR + (AMOUNT - FLOOR) // 2


def test_read_booleans_track_started_active_expired_and_ended(
    project, accounts, chain
):
    creator = accounts[0]
    solver = accounts[1]
    token, game = deploy_game(project, accounts, chain, curve_exponent=2)

    assert not game.is_active()
    assert not game.is_expired()
    assert not game.is_ended()

    fund_game(token, game, creator)

    assert not game.is_active()
    assert not game.is_expired()
    assert not game.is_ended()

    game.start_game(sender=creator)

    assert game.funded()
    assert game.started()
    assert not game.ended()
    assert game.is_active()
    assert not game.is_expired()
    assert not game.is_ended()

    game.submit_answer(ANSWER, sender=solver)

    assert not game.is_active()
    assert not game.is_expired()
    assert game.is_ended()


def test_read_booleans_track_expired_unended_game(project, accounts, chain):
    creator = accounts[0]
    token, game = deploy_game(project, accounts, chain, curve_exponent=2)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()

    assert not game.is_active()
    assert game.is_expired()
    assert not game.is_ended()


def test_cubic_claimable_amount_is_more_back_loaded_than_quadratic(
    project, accounts, chain
):
    creator = accounts[0]
    token, quadratic_game = deploy_game(project, accounts, chain, curve_exponent=2)
    cubic_token, cubic_game = deploy_game(project, accounts, chain, curve_exponent=3)
    fund_game(token, quadratic_game, creator)
    fund_game(cubic_token, cubic_game, creator)
    quadratic_game.start_game(sender=creator)
    cubic_game.start_game(sender=creator)

    ramp_midpoint = (
        quadratic_game.start_time()
        + quadratic_game.cliff_seconds()
        + (
            quadratic_game.deadline()
            - quadratic_game.start_time()
            - quadratic_game.cliff_seconds()
        )
        // 2
    )
    chain.pending_timestamp = ramp_midpoint
    chain.mine()

    assert cubic_game.curve_exponent() == 3
    assert cubic_game.claimable_amount() == expected_claimable(cubic_game, ramp_midpoint)
    assert cubic_game.claimable_amount() < quadratic_game.claimable_amount()


def test_correct_answer_can_win_at_exact_deadline(project, accounts, chain):
    creator = accounts[0]
    solver = accounts[1]
    token, game = deploy_game(project, accounts, chain, curve_exponent=3)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    chain.pending_timestamp = game.deadline()

    game.submit_answer(ANSWER, sender=solver)

    assert game.ended()
    assert game.winner() == solver.address
    assert token.balanceOf(solver) == AMOUNT


def test_wrong_answer_does_not_settle_then_correct_answer_pays(
    project, accounts, chain
):
    creator = accounts[0]
    solver = accounts[1]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    wrong_receipt = game.submit_answer(WRONG_ANSWER, sender=solver)
    wrong_attempts = list(wrong_receipt.decode_logs(game.AnswerSubmitted))

    assert not game.ended()
    assert len(wrong_attempts) == 1
    assert not bool(wrong_attempts[0].success)

    chain.pending_timestamp = game.start_time() + 600
    chain.mine()
    paid_before_submit = game.claimable_amount()

    receipt = game.submit_answer(ANSWER, sender=solver)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert game.winner() == solver.address
    assert game.paid_amount() >= paid_before_submit
    assert token.balanceOf(solver) == game.paid_amount()
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_WON

    game.clawback(sender=creator)

    assert token.balanceOf(refund_to) == AMOUNT - game.paid_amount()


def test_expiry_allows_clawback(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)
    game.start_game(sender=creator)

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()

    receipt = game.clawback(sender=creator)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert token.balanceOf(refund_to) == AMOUNT
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_EXPIRED


def test_creator_can_cancel_and_claw_back_before_start(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_game(token, game, creator)

    receipt = game.clawback(sender=creator)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert token.balanceOf(refund_to) == AMOUNT
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_CANCELLED_BEFORE_START


def test_invalid_curve_exponent_reverts(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)

    with ape.reverts("bad curve"):
        project.PuzzleGiveawayV3.deploy(
            token.address,
            refund_to.address,
            PROMPT,
            AMOUNT,
            FLOOR,
            chain.pending_timestamp + 1_100,
            CLIFF,
            4,
            keccak(text=ANSWER),
            sender=creator,
        )
