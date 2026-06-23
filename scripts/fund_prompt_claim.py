import click
from ape import accounts, project
from eth_utils import is_address, to_checksum_address


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

    token.approve(prompt_claim, amount, sender=creator)
    claim.fund(sender=creator)

    click.echo(f"funded_amount={amount}")

