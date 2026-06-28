from types import SimpleNamespace

import click
import pytest
from eth_utils import keccak

from scripts import deploy_and_fund_king_of_the_hill, start_king_of_the_hill


AMOUNT = 1_000_000
FLOOR = 100_000
MAX_SHOTS = 5
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
    game = project.KingOfTheHillGiveaway.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        FLOOR,
        chain.pending_timestamp + 3600,
        MAX_SHOTS,
        2,
        ANSWER_HASH,
        sender=creator,
    )
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)
    return game


def deployed_address_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("king_of_the_hill="):
            return line.split("=", maxsplit=1)[1]

    raise AssertionError("missing king_of_the_hill output")


def test_default_token_uses_base_sepolia_when_selected(monkeypatch):
    monkeypatch.delenv("KINGOFTHEHILL_TOKEN", raising=False)

    token = deploy_and_fund_king_of_the_hill.default_token(
        provider("base", "sepolia")
    )

    assert token == deploy_and_fund_king_of_the_hill.BASE_SEPOLIA_USDC


def test_default_token_uses_active_provider_when_callback_provider_missing(
    monkeypatch,
):
    monkeypatch.delenv("KINGOFTHEHILL_TOKEN", raising=False)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.networks,
        "active_provider",
        provider("base", "sepolia"),
    )

    token = deploy_and_fund_king_of_the_hill.default_token(None)

    assert token == deploy_and_fund_king_of_the_hill.BASE_SEPOLIA_USDC


def test_explicit_token_env_overrides_network_default(monkeypatch):
    token_override = "0x000000000000000000000000000000000000dEaD"
    monkeypatch.setenv("KINGOFTHEHILL_TOKEN", token_override)

    token = deploy_and_fund_king_of_the_hill.default_token(
        provider("base", "sepolia")
    )

    assert token == token_override


def test_validate_game_values_rejects_bad_curve_exponent(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_king_of_the_hill.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="curve-exponent must be 1, 2, or 3"):
        deploy_and_fund_king_of_the_hill.validate_game_values(
            prompt=PROMPT,
            max_amount=100,
            floor_amount=1,
            deadline=200,
            max_shots=MAX_SHOTS,
            curve_exponent=4,
        )


def test_deploy_and_fund_script_deploys_game(project, accounts, capsys, monkeypatch):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_king_of_the_hill.cli.main(
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
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveaway.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.prompt() == PROMPT
    assert game.max_shots() == MAX_SHOTS
    assert game.curve_exponent() == 2
    assert game.funded()
    assert not game.started()
    assert token.balanceOf(game.address) == AMOUNT


def test_deploy_and_fund_script_can_start_game(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_king_of_the_hill.cli.main(
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
            "--max-shots",
            str(MAX_SHOTS),
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

    game = project.KingOfTheHillGiveaway.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.curve_exponent() == 3
    assert game.funded()
    assert game.started()
    assert game.king_prize() == 0


def test_start_script_starts_funded_game(project, accounts, chain, monkeypatch):
    creator = accounts[0]
    game = deploy_funded_game(project, accounts, chain)
    monkeypatch.setattr(
        start_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = start_king_of_the_hill.cli.main(
        args=[
            "--account",
            "creator",
            "--king-of-the-hill",
            game.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert game.started()
    assert game.start_time() > 0
