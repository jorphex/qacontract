import ape
import pytest
from eth_utils import keccak


AMOUNT = 100_000_000
ANSWER = b"blue candle"
WRONG_ANSWER = b"red candle"


@pytest.fixture
def creator(accounts):
    return accounts[0]


@pytest.fixture
def solver(accounts):
    return accounts[1]


@pytest.fixture
def refund_to(accounts):
    return accounts[2]


@pytest.fixture
def stranger(accounts):
    return accounts[3]


@pytest.fixture
def token(project, creator):
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    return token


@pytest.fixture
def deadline(chain):
    return chain.pending_timestamp + 3600


@pytest.fixture
def prompt_claim(project, token, creator, refund_to, deadline):
    return project.PromptClaim.deploy(
        token.address,
        refund_to.address,
        AMOUNT,
        deadline,
        keccak(ANSWER),
        sender=creator,
    )


@pytest.fixture
def funded_prompt_claim(token, prompt_claim, creator):
    token.approve(prompt_claim.address, AMOUNT, sender=creator)
    prompt_claim.fund(sender=creator)
    return prompt_claim


def test_creator_can_fund_once(token, prompt_claim, creator):
    token.approve(prompt_claim.address, AMOUNT, sender=creator)

    prompt_claim.fund(sender=creator)

    assert prompt_claim.funded()
    assert token.balanceOf(prompt_claim.address) == AMOUNT

    with ape.reverts("already funded"):
        prompt_claim.fund(sender=creator)


def test_non_creator_cannot_fund(token, prompt_claim, solver):
    token.approve(prompt_claim.address, AMOUNT, sender=solver)

    with ape.reverts("not creator"):
        prompt_claim.fund(sender=solver)


def test_anyone_can_claim_with_correct_answer(token, funded_prompt_claim, solver):
    funded_prompt_claim.claim(ANSWER, sender=solver)

    assert funded_prompt_claim.settled()
    assert funded_prompt_claim.winner() == solver.address
    assert token.balanceOf(solver) == AMOUNT
    assert token.balanceOf(funded_prompt_claim.address) == 0


def test_wrong_answer_cannot_claim(funded_prompt_claim, solver):
    with ape.reverts("wrong answer"):
        funded_prompt_claim.claim(WRONG_ANSWER, sender=solver)

    assert not funded_prompt_claim.settled()


def test_claim_expires(chain, funded_prompt_claim, solver, deadline):
    chain.pending_timestamp = deadline + 1
    chain.mine()

    with ape.reverts("expired"):
        funded_prompt_claim.claim(ANSWER, sender=solver)


def test_creator_cannot_clawback_before_deadline(funded_prompt_claim, creator):
    with ape.reverts("not expired"):
        funded_prompt_claim.clawback(sender=creator)


def test_creator_can_clawback_after_deadline(
    token, chain, funded_prompt_claim, creator, refund_to, deadline
):
    chain.pending_timestamp = deadline + 1
    chain.mine()

    funded_prompt_claim.clawback(sender=creator)

    assert funded_prompt_claim.settled()
    assert token.balanceOf(refund_to) == AMOUNT
    assert token.balanceOf(funded_prompt_claim.address) == 0


def test_non_creator_cannot_clawback_after_deadline(
    chain, funded_prompt_claim, stranger, deadline
):
    chain.pending_timestamp = deadline + 1
    chain.mine()

    with ape.reverts("not creator"):
        funded_prompt_claim.clawback(sender=stranger)


def test_claim_prevents_later_clawback(funded_prompt_claim, chain, solver, creator, deadline):
    funded_prompt_claim.claim(ANSWER, sender=solver)

    chain.pending_timestamp = deadline + 1
    chain.mine()

    with ape.reverts("settled"):
        funded_prompt_claim.clawback(sender=creator)


def test_clawback_prevents_later_claim(funded_prompt_claim, chain, solver, creator, deadline):
    chain.pending_timestamp = deadline + 1
    chain.mine()
    funded_prompt_claim.clawback(sender=creator)

    with ape.reverts("settled"):
        funded_prompt_claim.claim(ANSWER, sender=solver)

