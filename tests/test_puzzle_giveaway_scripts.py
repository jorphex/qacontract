from types import SimpleNamespace

import click
import pytest
from eth_utils import keccak

from scripts import deploy_and_fund_puzzle_giveaway, start_puzzle_giveaway


AMOUNT = 1_000_000
FLOOR = 250_000
PROMPT = "What color is the candle?"
ANSWER_HASH = keccak(text="blue candle")
ANSWER_HASH_HEX = f"0x{ANSWER_HASH.hex()}"


def provider(ecosystem_name: str, network_name: str):
    return SimpleNamespace(
        network=SimpleNamespace(
            ecosystem=SimpleNamespace(name=ecosystem_name),
            name=network_name,
        )
    )


def deploy_funded_game(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    game = project.PuzzleGiveaway.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        FLOOR,
        chain.pending_timestamp + 3600,
        60,
        ANSWER_HASH,
        sender=creator,
    )
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)
    return game


def deployed_address_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("puzzle_giveaway="):
            return line.split("=", maxsplit=1)[1]

    raise AssertionError("missing puzzle_giveaway output")


def test_default_token_uses_base_mainnet_when_selected(monkeypatch):
    monkeypatch.delenv("PUZZLEGIVEAWAY_TOKEN", raising=False)

    token = deploy_and_fund_puzzle_giveaway.default_token(
        provider("base", "mainnet")
    )

    assert token == deploy_and_fund_puzzle_giveaway.BASE_USDC


def test_validate_game_values_rejects_bad_floor(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="floor-amount cannot exceed"):
        deploy_and_fund_puzzle_giveaway.validate_game_values(
            prompt=PROMPT,
            max_amount=100,
            floor_amount=101,
            deadline=200,
            cliff_seconds=0,
        )


def test_validate_game_values_rejects_cliff_that_reaches_deadline(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="deadline must be after"):
        deploy_and_fund_puzzle_giveaway.validate_game_values(
            prompt=PROMPT,
            max_amount=100,
            floor_amount=1,
            deadline=200,
            cliff_seconds=100,
        )


def test_validate_game_values_allows_long_cliff_for_fixed_prize(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway.time, "time", lambda: 100)

    deploy_and_fund_puzzle_giveaway.validate_game_values(
        prompt=PROMPT,
        max_amount=100,
        floor_amount=100,
        deadline=200,
        cliff_seconds=100,
    )


def test_validate_game_values_rejects_empty_prompt(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="prompt must not be empty"):
        deploy_and_fund_puzzle_giveaway.validate_game_values(
            prompt="",
            max_amount=100,
            floor_amount=1,
            deadline=200,
            cliff_seconds=0,
        )


def test_validate_game_values_rejects_prompt_over_256_bytes(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="prompt must fit"):
        deploy_and_fund_puzzle_giveaway.validate_game_values(
            prompt="x" * 257,
            max_amount=100,
            floor_amount=1,
            deadline=200,
            cliff_seconds=0,
        )


def test_deploy_and_fund_script_deploys_funds_without_starting(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_puzzle_giveaway.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_puzzle_giveaway.cli.main(
        args=[
            "--account",
            "creator",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--cliff-seconds",
            "60",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.PuzzleGiveaway.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.prompt() == PROMPT
    assert game.funded()
    assert not game.started()
    assert token.balanceOf(game.address) == AMOUNT


def test_deploy_and_fund_script_can_start_immediately(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_puzzle_giveaway.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_puzzle_giveaway.cli.main(
        args=[
            "--account",
            "creator",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--cliff-seconds",
            "60",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--start-now",
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.PuzzleGiveaway.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.prompt() == PROMPT
    assert game.funded()
    assert game.started()
    assert game.claimable_amount() == FLOOR


def test_start_script_starts_funded_game(project, accounts, chain, monkeypatch):
    creator = accounts[0]
    game = deploy_funded_game(project, accounts, chain)
    monkeypatch.setattr(start_puzzle_giveaway.accounts, "load", lambda _alias: creator)

    result = start_puzzle_giveaway.cli.main(
        args=[
            "--account",
            "creator",
            "--puzzle-giveaway",
            game.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert game.started()
    assert game.start_time() > 0
