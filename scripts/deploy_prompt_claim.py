import os

import click
from ape import accounts, project
from dotenv import load_dotenv
from eth_utils import is_address, to_checksum_address


load_dotenv()

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def env_default(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def parse_address(value: str, label: str) -> str:
    if not is_address(value):
        raise click.BadParameter(f"{label} must be an EVM address")

    return to_checksum_address(value)


def parse_answer_hash(value: str) -> str:
    if not value.startswith("0x") or len(value) != 66:
        raise click.BadParameter("answer hash must be 32 bytes hex, like 0x...")

    int(value, 16)
    return value


@click.command()
@click.option(
    "--account",
    envvar="PROMPTCLAIM_ACCOUNT",
    required=True,
    help="Ape account alias to deploy from.",
)
@click.option(
    "--token",
    envvar="PROMPTCLAIM_TOKEN",
    default=lambda: env_default("PROMPTCLAIM_TOKEN", BASE_USDC),
    show_default="Base USDC",
    help="ERC20 prize token address.",
)
@click.option(
    "--refund-to",
    envvar="PROMPTCLAIM_REFUND_TO",
    required=True,
    help="Address that receives clawback funds.",
)
@click.option(
    "--amount",
    envvar="PROMPTCLAIM_AMOUNT",
    required=True,
    type=int,
    help="Prize amount in token base units. For USDC, 1 USDC = 1000000.",
)
@click.option(
    "--deadline",
    envvar="PROMPTCLAIM_DEADLINE",
    required=True,
    type=int,
    help="Unix timestamp when claiming expires.",
)
@click.option(
    "--answer-hash",
    envvar="PROMPTCLAIM_ANSWER_HASH",
    required=True,
    callback=lambda _ctx, _param, value: parse_answer_hash(value),
    help="Hash from `ape run hash_answer`.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print deployment values without loading an account or sending a transaction.",
)
def cli(
    account: str,
    token: str,
    refund_to: str,
    amount: int,
    deadline: int,
    answer_hash: str,
    dry_run: bool,
):
    token = parse_address(token, "token")
    refund_to = parse_address(refund_to, "refund-to")

    if amount <= 0:
        raise click.BadParameter("amount must be greater than zero")

    click.echo("PromptClaim deployment")
    click.echo(f"account={account}")
    click.echo(f"token={token}")
    click.echo(f"refund_to={refund_to}")
    click.echo(f"amount={amount}")
    click.echo(f"deadline={deadline}")
    click.echo(f"answer_hash={answer_hash}")

    if dry_run:
        return

    deployer = accounts.load(account)
    contract = deployer.deploy(
        project.PromptClaim,
        token,
        refund_to,
        amount,
        deadline,
        answer_hash,
    )
    click.echo(f"prompt_claim={contract.address}")
