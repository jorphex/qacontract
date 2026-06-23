import click
from ape import accounts, project
from dotenv import load_dotenv
from eth_utils import is_address, to_checksum_address


load_dotenv()


def tx_hash(receipt) -> str:
    value = getattr(receipt, "txn_hash", None)
    if value is None:
        value = getattr(receipt, "tx_hash", None)

    return str(value)


def parse_address(value: str, label: str) -> str:
    if not is_address(value):
        raise click.BadParameter(f"{label} must be an EVM address")

    return to_checksum_address(value)


@click.command()
@click.option(
    "--account",
    envvar="PROMPTCLAIM_ACCOUNT",
    required=True,
    help="Ape account alias that created the PromptClaim.",
)
@click.option(
    "--prompt-claim",
    envvar="PROMPTCLAIM_ADDRESS",
    required=True,
    help="Deployed PromptClaim address.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the target without loading an account or sending transactions.",
)
def cli(account: str, prompt_claim: str, dry_run: bool):
    prompt_claim = parse_address(prompt_claim, "prompt-claim")

    click.echo("PromptClaim funding")
    click.echo(f"account={account}")
    click.echo(f"prompt_claim={prompt_claim}")

    if dry_run:
        return

    creator = accounts.load(account)
    claim = project.PromptClaim.at(prompt_claim)
    token = project.MockERC20.at(claim.token())
    amount = claim.amount()
    contract_creator = claim.creator()
    deadline = claim.deadline()
    funded = claim.funded()
    settled = claim.settled()

    click.echo(f"creator={contract_creator}")
    click.echo(f"token={token.address}")
    click.echo(f"amount={amount}")
    click.echo(f"deadline={deadline}")
    click.echo(f"funded={funded}")
    click.echo(f"settled={settled}")

    if contract_creator != creator.address:
        raise click.ClickException("loaded account is not the PromptClaim creator")

    if funded:
        raise click.ClickException("PromptClaim is already funded")

    if settled:
        raise click.ClickException("PromptClaim is already settled")

    if amount <= 0:
        raise click.ClickException("PromptClaim amount must be greater than zero")

    approve_receipt = token.approve(prompt_claim, amount, sender=creator)
    click.echo(f"approve_tx={tx_hash(approve_receipt)}")

    fund_receipt = claim.fund(sender=creator)
    click.echo(f"fund_tx={tx_hash(fund_receipt)}")

    click.echo(f"funded_amount={amount}")
