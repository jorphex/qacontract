from eth_utils import keccak

from scripts import fund_prompt_claim


AMOUNT = 1_000_000
ANSWER_HASH = keccak(text="test")


def deploy_unfunded_claim(project, creator):
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    claim = project.PromptClaim.deploy(
        token.address,
        creator.address,
        AMOUNT,
        4_102_444_800,
        ANSWER_HASH,
        sender=creator,
    )
    return token, claim


def test_fund_script_approves_when_allowance_is_insufficient(
    project, accounts, monkeypatch
):
    creator = accounts[0]
    token, claim = deploy_unfunded_claim(project, creator)

    monkeypatch.setattr(fund_prompt_claim.accounts, "load", lambda _alias: creator)
    result = fund_prompt_claim.cli.main(
        args=[
            "--account",
            "creator",
            "--prompt-claim",
            claim.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert claim.funded()
    assert token.balanceOf(claim.address) == AMOUNT
    assert token.allowance(creator.address, claim.address) == 0


def test_fund_script_skips_approve_when_allowance_is_sufficient(
    project, accounts, monkeypatch, capsys
):
    creator = accounts[0]
    token, claim = deploy_unfunded_claim(project, creator)
    token.approve(claim.address, AMOUNT, sender=creator)

    monkeypatch.setattr(fund_prompt_claim.accounts, "load", lambda _alias: creator)
    result = fund_prompt_claim.cli.main(
        args=[
            "--account",
            "creator",
            "--prompt-claim",
            claim.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert "approve_tx=skipped" in capsys.readouterr().out
    assert claim.funded()
    assert token.balanceOf(claim.address) == AMOUNT
    assert token.allowance(creator.address, claim.address) == 0

