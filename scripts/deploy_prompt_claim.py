import os
import time

import click
from ape import accounts, project
from ape.cli import ConnectedProviderCommand
from dotenv import load_dotenv
from eth_utils import is_address, to_checksum_address


load_dotenv()

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

BASE_USDC_BY_NETWORK = {
    ("base", "mainnet"): BASE_USDC,
    ("base", "sepolia"): BASE_SEPOLIA_USDC,
}


def default_token(provider) -> str:
    if token := os.environ.get("PROMPTCLAIM_TOKEN"):
        return token

    if provider is None:
        return BASE_USDC

    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    return BASE_USDC_BY_NETWORK.get((ecosystem_name, network_name), BASE_USDC)


def parse_address(value: str, label: str) -> str:
    if not is_address(value):
        raise click.BadParameter(f"{label} must be an EVM address")

    return to_checksum_address(value)


def parse_answer_hash(value: str) -> str:
    if not value.startswith("0x") or len(value) != 66:
        raise click.BadParameter("answer hash must be 32 bytes hex, like 0x...")

    int(value, 16)
    return value


def validate_deadline(deadline: int):
    now = int(time.time())
    if deadline <= now:
        raise click.BadParameter(
            f"deadline must be in the future; now is {now}"
        )


def echo_contract_state(contract):
    click.echo(f"deployed_creator={contract.creator()}")
    click.echo(f"deployed_token={contract.token()}")
    click.echo(f"deployed_refund_to={contract.refund_to()}")
    click.echo(f"deployed_amount={contract.amount()}")
    click.echo(f"deployed_deadline={contract.deadline()}")
    click.echo(f"deployed_answer_hash={contract.answer_hash()}")


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--account",
    envvar="PROMPTCLAIM_ACCOUNT",
    required=True,
    help="Ape account alias to deploy from.",
)
@click.option(
    "--token",
    envvar="PROMPTCLAIM_TOKEN",
    default=None,
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
    provider,
    account: str,
    token: str | None,
    refund_to: str,
    amount: int,
    deadline: int,
    answer_hash: str,
    dry_run: bool,
):
    token = token or default_token(provider)
    token = parse_address(token, "token")
    refund_to = parse_address(refund_to, "refund-to")

    if amount <= 0:
        raise click.BadParameter("amount must be greater than zero")

    validate_deadline(deadline)

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
    echo_contract_state(contract)
