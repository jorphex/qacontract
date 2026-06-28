import ape
from eth_utils import keccak


AMOUNT = 1_000_000
FLOOR = 100_000
MAX_SHOTS = 5
PROMPT = "What color is the candle?"
ANSWER = "blue candle"
WRONG_ANSWER = "red candle"
REASON_WON = 1
REASON_NO_CORRECT_REIGN = 2
REASON_CANCELLED_BEFORE_START = 3
BPS = 10_000


def deploy_game(
    project,
    accounts,
    chain,
    floor=FLOOR,
    deadline_offset=1_000,
    max_shots=MAX_SHOTS,
    curve_exponent=2,
):
    creator = accounts[0]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    game = project.KingOfTheHillGiveaway.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        floor,
        chain.pending_timestamp + deadline_offset,
        max_shots,
        curve_exponent,
        keccak(text=ANSWER),
        sender=creator,
    )
    return token, game


def fund_and_start(token, game, creator):
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)
    game.start_game(sender=creator)


def expected_prize(game, since, until):
    if until < since:
        return 0

    if game.floor_amount() == game.max_amount():
        return game.max_amount()

    elapsed = until - since
    game_duration = game.game_duration()
    if elapsed >= game_duration:
        return game.max_amount()

    progress_bps = elapsed * BPS // game_duration
    curve_bps = progress_bps
    if game.curve_exponent() >= 2:
        curve_bps = progress_bps * progress_bps // BPS
    if game.curve_exponent() == 3:
        curve_bps = curve_bps * progress_bps // BPS

    return game.floor_amount() + (
        (game.max_amount() - game.floor_amount()) * curve_bps // BPS
    )


def test_shoot_captures_hill_and_uses_ammo(project, accounts, chain):
    creator = accounts[0]
    player = accounts[1]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    receipt = game.shoot(WRONG_ANSWER, sender=player)
    shots = list(receipt.decode_logs(game.Shot))

    assert game.king() == player.address
    assert game.king_since() == chain.blocks[-1].timestamp
    assert game.shots_used(player) == 1
    assert game.shots_remaining(player) == MAX_SHOTS - 1
    assert game.king_prize() == FLOOR
    assert len(shots) == 1
    assert shots[0].player == player.address


def test_later_correct_reign_wins_even_if_final_king_is_wrong(
    project, accounts, chain
):
    creator = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    carol = accounts[3]
    refund_to = accounts[4]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    game.shoot(ANSWER, sender=alice)
    alice_since = game.king_since()

    chain.pending_timestamp = alice_since + 200
    chain.mine()
    game.shoot(WRONG_ANSWER, sender=bob)

    chain.pending_timestamp = game.king_since() + 100
    chain.mine()
    game.shoot(ANSWER, sender=carol)
    carol_since = game.king_since()

    chain.pending_timestamp = carol_since + 150
    chain.mine()
    game.shoot(WRONG_ANSWER, sender=bob)

    carol_reign_ended_at = game.king_since()
    carol_prize = expected_prize(game, carol_since, carol_reign_ended_at)
    assert game.king() == bob.address
    assert carol_prize < AMOUNT

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()
    receipt = game.finalize(sender=alice)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert game.winner() == carol.address
    assert token.balanceOf(carol) == carol_prize
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_WON

    game.clawback(sender=creator)

    assert token.balanceOf(refund_to) == AMOUNT - carol_prize


def test_current_correct_king_wins_reign_through_deadline(project, accounts, chain):
    creator = accounts[0]
    alice = accounts[1]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    chain.pending_timestamp = game.start_time() + 250
    chain.mine()
    game.shoot(ANSWER, sender=alice)
    since = game.king_since()

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()
    game.finalize(sender=alice)

    expected = expected_prize(game, since, game.deadline())
    assert game.winner() == alice.address
    assert game.paid_amount() == expected
    assert token.balanceOf(alice) == expected


def test_correct_shot_at_exact_deadline_wins_floor(project, accounts, chain):
    creator = accounts[0]
    alice = accounts[1]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    chain.pending_timestamp = game.deadline()
    game.shoot(ANSWER, sender=alice)

    chain.pending_timestamp = game.deadline() + 1
    game.finalize(sender=creator)

    assert game.winner() == alice.address
    assert game.paid_amount() == FLOOR
    assert token.balanceOf(alice) == FLOOR


def test_wrong_shot_at_exact_deadline_does_not_erase_latest_correct_reign(
    project, accounts, chain
):
    creator = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    game.shoot(ANSWER, sender=alice)
    alice_since = game.king_since()

    chain.pending_timestamp = game.deadline()
    game.shoot(WRONG_ANSWER, sender=bob)

    expected = expected_prize(game, alice_since, game.deadline())

    chain.pending_timestamp = game.deadline() + 1
    game.finalize(sender=creator)

    assert game.king() == bob.address
    assert game.winner() == alice.address
    assert game.paid_amount() == expected
    assert token.balanceOf(alice) == expected


def test_late_correct_steal_resets_prize_growth(project, accounts, chain):
    creator = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    game.shoot(ANSWER, sender=alice)
    chain.pending_timestamp = game.start_time() + game.game_duration() // 2
    chain.mine()
    alice_current_prize = game.king_prize()

    chain.pending_timestamp = game.start_time() + game.game_duration() * 3 // 4
    chain.mine()
    game.shoot(ANSWER, sender=bob)

    assert game.king() == bob.address
    assert game.king_prize() == FLOOR
    assert alice_current_prize > game.king_prize()

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()
    game.finalize(sender=bob)

    assert game.winner() == bob.address
    assert game.paid_amount() < alice_current_prize


def test_no_correct_reign_pays_no_one_and_allows_clawback(
    project, accounts, chain
):
    creator = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    refund_to = accounts[4]
    token, game = deploy_game(project, accounts, chain)
    fund_and_start(token, game, creator)

    game.shoot(WRONG_ANSWER, sender=alice)
    game.shoot("green candle", sender=bob)

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()
    receipt = game.finalize(sender=alice)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert game.winner() == "0x0000000000000000000000000000000000000000"
    assert game.paid_amount() == 0
    assert token.balanceOf(alice) == 0
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_NO_CORRECT_REIGN

    game.clawback(sender=creator)

    assert token.balanceOf(refund_to) == AMOUNT


def test_shots_are_limited_per_address(project, accounts, chain):
    creator = accounts[0]
    player = accounts[1]
    token, game = deploy_game(project, accounts, chain, max_shots=2)
    fund_and_start(token, game, creator)

    game.shoot(WRONG_ANSWER, sender=player)
    game.shoot("still wrong", sender=player)

    assert game.shots_remaining(player) == 0
    with ape.reverts("out of shots"):
        game.shoot(ANSWER, sender=player)


def test_creator_can_cancel_and_claw_back_before_start(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[4]
    token, game = deploy_game(project, accounts, chain)
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)

    receipt = game.clawback(sender=creator)
    ended_events = list(receipt.decode_logs(game.GameEnded))

    assert game.ended()
    assert token.balanceOf(refund_to) == AMOUNT
    assert len(ended_events) == 1
    assert ended_events[0].reason == REASON_CANCELLED_BEFORE_START


def test_active_expired_and_ended_reads(project, accounts, chain):
    creator = accounts[0]
    token, game = deploy_game(project, accounts, chain)

    assert not game.is_active()
    assert not game.is_expired()
    assert not game.is_ended()

    fund_and_start(token, game, creator)

    assert game.is_active()
    assert not game.is_expired()
    assert not game.is_ended()

    chain.pending_timestamp = game.deadline() + 1
    chain.mine()

    assert not game.is_active()
    assert game.is_expired()
    assert not game.is_ended()

    game.finalize(sender=creator)

    assert game.is_ended()


def test_invalid_curve_exponent_reverts(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)

    with ape.reverts("bad curve"):
        project.KingOfTheHillGiveaway.deploy(
            token.address,
            refund_to.address,
            PROMPT,
            AMOUNT,
            FLOOR,
            chain.pending_timestamp + 1_000,
            MAX_SHOTS,
            4,
            keccak(text=ANSWER),
            sender=creator,
        )
