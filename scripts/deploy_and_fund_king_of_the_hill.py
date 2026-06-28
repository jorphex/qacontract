import os
import time

import click
from ape import accounts, networks, project
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
    if token := os.environ.get("KINGOFTHEHILL_TOKEN"):
        return token

    provider = provider or networks.active_provider
    if provider is None:
        return BASE_USDC

    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    return BASE_USDC_BY_NETWORK.get((ecosystem_name, network_name), BASE_USDC)


def tx_hash(receipt) -> str:
    value = getattr(receipt, "txn_hash", None)
    if value is None:
        value = getattr(receipt, "tx_hash", None)

    return str(value)


def parse_address(value: str, label: str) -> str:
    if not is_address(value):
        raise click.BadParameter(f"{label} must be an EVM address")

    return to_checksum_address(value)


def parse_answer_hash(value: str) -> str:
    if not value.startswith("0x") or len(value) != 66:
        raise click.BadParameter("answer hash must be 32 bytes hex, like 0x...")

    try:
        int(value, 16)
    except ValueError as exc:
        raise click.BadParameter("answer hash must be hex") from exc

    return value


def validate_game_values(
    prompt: str,
    max_amount: int,
    floor_amount: int,
    deadline: int,
    max_shots: int,
    curve_exponent: int,
):
    if not prompt:
        raise click.BadParameter("prompt must not be empty")

    if len(prompt.encode()) > 256:
        raise click.BadParameter("prompt must fit in 256 bytes")

    if max_amount <= 0:
        raise click.BadParameter("max-amount must be greater than zero")

    if floor_amount <= 0:
        raise click.BadParameter("floor-amount must be greater than zero")

    if floor_amount > max_amount:
        raise click.BadParameter("floor-amount cannot exceed max-amount")

    if max_shots <= 0:
        raise click.BadParameter("max-shots must be greater than zero")

    if curve_exponent not in (1, 2, 3):
        raise click.BadParameter("curve-exponent must be 1, 2, or 3")

    now = int(time.time())
    if deadline <= now:
        raise click.BadParameter(
            f"deadline must be in the future; now is {now}"
        )


def echo_contract_state(contract):
    click.echo(f"deployed_creator={contract.creator()}")
    click.echo(f"deployed_token={contract.token()}")
    click.echo(f"deployed_refund_to={contract.refund_to()}")
    click.echo(f"deployed_prompt={contract.prompt()}")
    click.echo(f"deployed_max_amount={contract.max_amount()}")
    click.echo(f"deployed_floor_amount={contract.floor_amount()}")
    click.echo(f"deployed_deadline={contract.deadline()}")
    click.echo(f"deployed_max_shots={contract.max_shots()}")
    click.echo(f"deployed_curve_exponent={contract.curve_exponent()}")
    click.echo(f"deployed_answer_hash={contract.answer_hash()}")
    click.echo(f"deployed_funded={contract.funded()}")
    click.echo(f"deployed_started={contract.started()}")
    click.echo(f"deployed_ended={contract.ended()}")
    click.echo(f"deployed_start_time={contract.start_time()}")
    click.echo(f"deployed_game_duration={contract.game_duration()}")
    click.echo(f"deployed_king={contract.king()}")
    click.echo(f"deployed_king_since={contract.king_since()}")
    click.echo(f"deployed_king_prize={contract.king_prize()}")
    click.echo(f"deployed_remaining_amount={contract.remaining_amount()}")


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--account",
    envvar="KINGOFTHEHILL_ACCOUNT",
    required=True,
    help="Ape account alias to deploy and fund from.",
)
@click.option(
    "--token",
    envvar="KINGOFTHEHILL_TOKEN",
    default=None,
    help="ERC20 prize token address.",
)
@click.option(
    "--refund-to",
    envvar="KINGOFTHEHILL_REFUND_TO",
    required=True,
    help="Address that receives clawback funds.",
)
@click.option(
    "--prompt",
    envvar="KINGOFTHEHILL_PROMPT",
    required=True,
    help="Public prompt shown by the contract.",
)
@click.option(
    "--max-amount",
    envvar="KINGOFTHEHILL_MAX_AMOUNT",
    required=True,
    type=int,
    help="Maximum prize in token base units. For USDC, 1 USDC = 1000000.",
)
@click.option(
    "--floor-amount",
    envvar="KINGOFTHEHILL_FLOOR_AMOUNT",
    required=True,
    type=int,
    help="Minimum winning prize in token base units.",
)
@click.option(
    "--deadline",
    envvar="KINGOFTHEHILL_DEADLINE",
    required=True,
    type=int,
    help="Unix timestamp when shooting expires.",
)
@click.option(
    "--max-shots",
    envvar="KINGOFTHEHILL_MAX_SHOTS",
    default=5,
    show_default=True,
    type=int,
    help="Maximum shots each address can take.",
)
@click.option(
    "--curve-exponent",
    envvar="KINGOFTHEHILL_CURVE_EXPONENT",
    default=2,
    show_default=True,
    type=int,
    help="Prize growth exponent: 1 linear, 2 quadratic, 3 cubic.",
)
@click.option(
    "--answer-hash",
    envvar="KINGOFTHEHILL_ANSWER_HASH",
    required=True,
    callback=lambda _ctx, _param, value: parse_answer_hash(value),
    help="Hash from `ape run hash_answer`.",
)
@click.option(
    "--start-now",
    is_flag=True,
    help="Start the game immediately after funding.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print deployment values without loading an account or sending transactions.",
)
def cli(
    provider,
    account: str,
    token: str | None,
    refund_to: str,
    prompt: str,
    max_amount: int,
    floor_amount: int,
    deadline: int,
    max_shots: int,
    curve_exponent: int,
    answer_hash: str,
    start_now: bool,
    dry_run: bool,
):
    token = token or default_token(provider)
    token = parse_address(token, "token")
    refund_to = parse_address(refund_to, "refund-to")
    validate_game_values(
        prompt,
        max_amount,
        floor_amount,
        deadline,
        max_shots,
        curve_exponent,
    )

    click.echo("KingOfTheHillGiveaway deployment and funding")
    click.echo(f"account={account}")
    click.echo(f"token={token}")
    click.echo(f"refund_to={refund_to}")
    click.echo(f"prompt={prompt}")
    click.echo(f"max_amount={max_amount}")
    click.echo(f"floor_amount={floor_amount}")
    click.echo(f"deadline={deadline}")
    click.echo(f"max_shots={max_shots}")
    click.echo(f"curve_exponent={curve_exponent}")
    click.echo(f"answer_hash={answer_hash}")
    click.echo(f"start_now={start_now}")

    if dry_run:
        return

    deployer = accounts.load(account)
    contract = deployer.deploy(
        project.KingOfTheHillGiveaway,
        token,
        refund_to,
        prompt,
        max_amount,
        floor_amount,
        deadline,
        max_shots,
        curve_exponent,
        answer_hash,
    )
    click.echo(f"king_of_the_hill={contract.address}")

    token_contract = project.MockERC20.at(token)
    allowance = token_contract.allowance(deployer.address, contract.address)
    click.echo(f"allowance={allowance}")

    if allowance < max_amount:
        approve_receipt = token_contract.approve(
            contract.address,
            max_amount,
            sender=deployer,
        )
        click.echo(f"approve_tx={tx_hash(approve_receipt)}")
    else:
        click.echo("approve_tx=skipped")

    fund_receipt = contract.fund(sender=deployer)
    click.echo(f"fund_tx={tx_hash(fund_receipt)}")

    if start_now:
        start_receipt = contract.start_game(sender=deployer)
        click.echo(f"start_game_tx={tx_hash(start_receipt)}")

    echo_contract_state(contract)
