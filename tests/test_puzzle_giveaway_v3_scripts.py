from types import SimpleNamespace

import click
import pytest
from eth_utils import keccak

from scripts import deploy_and_fund_puzzle_giveaway_v3, start_puzzle_giveaway_v3


AMOUNT = 1_000_000
FLOOR = 100_000
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
    game = project.PuzzleGiveawayV3.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        FLOOR,
        chain.pending_timestamp + 3600,
        60,
        2,
        ANSWER_HASH,
        sender=creator,
    )
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)
    return game


def deployed_address_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("puzzle_giveaway_v3="):
            return line.split("=", maxsplit=1)[1]

    raise AssertionError("missing puzzle_giveaway_v3 output")


def test_default_token_uses_base_sepolia_when_selected(monkeypatch):
    monkeypatch.delenv("PUZZLEGIVEAWAY_V3_TOKEN", raising=False)

    token = deploy_and_fund_puzzle_giveaway_v3.default_token(
        provider("base", "sepolia")
    )

    assert token == deploy_and_fund_puzzle_giveaway_v3.BASE_SEPOLIA_USDC


def test_explicit_token_env_overrides_network_default(monkeypatch):
    token_override = "0x000000000000000000000000000000000000dEaD"
    monkeypatch.setenv("PUZZLEGIVEAWAY_V3_TOKEN", token_override)

    token = deploy_and_fund_puzzle_giveaway_v3.default_token(
        provider("base", "sepolia")
    )

    assert token == token_override


def test_validate_game_values_rejects_bad_curve_exponent(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_puzzle_giveaway_v3.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="curve-exponent must be 2 or 3"):
        deploy_and_fund_puzzle_giveaway_v3.validate_game_values(
            prompt=PROMPT,
            max_amount=100,
            floor_amount=1,
            deadline=200,
            cliff_seconds=0,
            curve_exponent=4,
        )


def test_deploy_and_fund_script_deploys_quadratic_game(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_puzzle_giveaway_v3.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_puzzle_giveaway_v3.cli.main(
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
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.PuzzleGiveawayV3.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.prompt() == PROMPT
    assert game.curve_exponent() == 2
    assert game.funded()
    assert not game.started()
    assert token.balanceOf(game.address) == AMOUNT


def test_deploy_and_fund_script_can_start_cubic_game(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_puzzle_giveaway_v3.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_puzzle_giveaway_v3.cli.main(
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
            "--curve-exponent",
            "3",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--start-now",
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.PuzzleGiveawayV3.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.curve_exponent() == 3
    assert game.funded()
    assert game.started()
    assert game.claimable_amount() == FLOOR


def test_start_script_starts_funded_v3_game(project, accounts, chain, monkeypatch):
    creator = accounts[0]
    game = deploy_funded_game(project, accounts, chain)
    monkeypatch.setattr(
        start_puzzle_giveaway_v3.accounts,
        "load",
        lambda _alias: creator,
    )

    result = start_puzzle_giveaway_v3.cli.main(
        args=[
            "--account",
            "creator",
            "--puzzle-giveaway-v3",
            game.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert game.started()
    assert game.start_time() > 0
