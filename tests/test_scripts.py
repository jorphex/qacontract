from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner
from eth_utils import keccak, to_hex

from scripts import deploy_prompt_claim, hash_answer


def provider(ecosystem_name: str, network_name: str):
    return SimpleNamespace(
        network=SimpleNamespace(
            ecosystem=SimpleNamespace(name=ecosystem_name),
            name=network_name,
        )
    )


def test_default_token_uses_base_mainnet_when_selected(monkeypatch):
    monkeypatch.delenv("PROMPTCLAIM_TOKEN", raising=False)

    token = deploy_prompt_claim.default_token(provider("base", "mainnet"))

    assert token == deploy_prompt_claim.BASE_USDC


def test_default_token_uses_base_sepolia_when_selected(monkeypatch):
    monkeypatch.delenv("PROMPTCLAIM_TOKEN", raising=False)

    token = deploy_prompt_claim.default_token(provider("base", "sepolia"))

    assert token == deploy_prompt_claim.BASE_SEPOLIA_USDC


def test_default_token_uses_active_provider_when_callback_provider_missing(
    monkeypatch,
):
    monkeypatch.delenv("PROMPTCLAIM_TOKEN", raising=False)
    monkeypatch.setattr(
        deploy_prompt_claim.networks,
        "active_provider",
        provider("base", "sepolia"),
    )

    token = deploy_prompt_claim.default_token(None)

    assert token == deploy_prompt_claim.BASE_SEPOLIA_USDC


def test_explicit_token_env_overrides_network_default(monkeypatch):
    token_override = "0x000000000000000000000000000000000000dEaD"
    monkeypatch.setenv("PROMPTCLAIM_TOKEN", token_override)

    token = deploy_prompt_claim.default_token(provider("base", "sepolia"))

    assert token == token_override


def test_validate_deadline_rejects_past_deadline(monkeypatch):
    monkeypatch.setattr(deploy_prompt_claim.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="deadline must be in the future"):
        deploy_prompt_claim.validate_deadline(100)


def test_validate_deadline_accepts_future_deadline(monkeypatch):
    monkeypatch.setattr(deploy_prompt_claim.time, "time", lambda: 100)

    deploy_prompt_claim.validate_deadline(101)


def test_echo_contract_state_outputs_deployed_values(capsys):
    contract = SimpleNamespace(
        creator=lambda: "0xcreator",
        token=lambda: "0xtoken",
        refund_to=lambda: "0xrefund",
        amount=lambda: 100,
        deadline=lambda: 200,
        answer_hash=lambda: "0xhash",
    )

    deploy_prompt_claim.echo_contract_state(contract)

    assert capsys.readouterr().out == (
        "deployed_creator=0xcreator\n"
        "deployed_token=0xtoken\n"
        "deployed_refund_to=0xrefund\n"
        "deployed_amount=100\n"
        "deployed_deadline=200\n"
        "deployed_answer_hash=0xhash\n"
    )


def test_hash_answer_hashes_exact_input_by_default():
    result = CliRunner().invoke(hash_answer.cli, ["Seulgi"])

    assert result.exit_code == 0
    assert result.output == (
        "hashed_answer=Seulgi\n"
        f"answer_hash={to_hex(keccak(text='Seulgi'))}\n"
    )


def test_hash_answer_can_normalize_input_when_requested():
    result = CliRunner().invoke(hash_answer.cli, [" Seulgi ", "--normalize"])

    assert result.exit_code == 0
    assert result.output == (
        "hashed_answer=seulgi\n"
        f"answer_hash={to_hex(keccak(text='seulgi'))}\n"
    )
