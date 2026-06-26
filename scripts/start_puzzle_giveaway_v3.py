import time

import click
from ape import accounts, project
from ape.cli import ConnectedProviderCommand
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


def echo_game_state(game):
    click.echo(f"creator={game.creator()}")
    click.echo(f"token={game.token()}")
    click.echo(f"refund_to={game.refund_to()}")
    click.echo(f"prompt={game.prompt()}")
    click.echo(f"max_amount={game.max_amount()}")
    click.echo(f"floor_amount={game.floor_amount()}")
    click.echo(f"deadline={game.deadline()}")
    click.echo(f"cliff_seconds={game.cliff_seconds()}")
    click.echo(f"curve_exponent={game.curve_exponent()}")
    click.echo(f"funded={game.funded()}")
    click.echo(f"started={game.started()}")
    click.echo(f"ended={game.ended()}")
    click.echo(f"start_time={game.start_time()}")
    click.echo(f"claimable_amount={game.claimable_amount()}")
    click.echo(f"remaining_amount={game.remaining_amount()}")


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--account",
    envvar="PUZZLEGIVEAWAY_V3_ACCOUNT",
    required=True,
    help="Ape account alias that created the PuzzleGiveawayV3.",
)
@click.option(
    "--puzzle-giveaway-v3",
    envvar="PUZZLEGIVEAWAY_V3_ADDRESS",
    required=True,
    help="Deployed PuzzleGiveawayV3 address.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the target without loading an account or sending a transaction.",
)
def cli(account: str, puzzle_giveaway_v3: str, dry_run: bool):
    puzzle_giveaway_v3 = parse_address(puzzle_giveaway_v3, "puzzle-giveaway-v3")

    click.echo("PuzzleGiveawayV3 start")
    click.echo(f"account={account}")
    click.echo(f"puzzle_giveaway_v3={puzzle_giveaway_v3}")

    if dry_run:
        return

    creator = accounts.load(account)
    game = project.PuzzleGiveawayV3.at(puzzle_giveaway_v3)
    contract_creator = game.creator()
    funded = game.funded()
    started = game.started()
    ended = game.ended()
    deadline = game.deadline()
    floor_amount = game.floor_amount()
    max_amount = game.max_amount()
    cliff_seconds = game.cliff_seconds()

    echo_game_state(game)

    if contract_creator != creator.address:
        raise click.ClickException("loaded account is not the PuzzleGiveawayV3 creator")

    if not funded:
        raise click.ClickException("PuzzleGiveawayV3 is not funded")

    if started:
        raise click.ClickException("PuzzleGiveawayV3 is already started")

    if ended:
        raise click.ClickException("PuzzleGiveawayV3 is already ended")

    now = int(time.time())
    if now >= deadline:
        raise click.ClickException(f"PuzzleGiveawayV3 is expired; now is {now}")

    if floor_amount < max_amount and now + cliff_seconds >= deadline:
        raise click.ClickException("PuzzleGiveawayV3 cliff reaches or passes deadline")

    start_receipt = game.start_game(sender=creator)
    click.echo(f"start_game_tx={tx_hash(start_receipt)}")
    echo_game_state(game)
