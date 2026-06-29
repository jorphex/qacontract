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
    click.echo(f"original_deadline={game.original_deadline()}")
    click.echo(f"deadline={game.deadline()}")
    click.echo(f"max_deadline={game.max_deadline()}")
    click.echo(f"extension_window={game.extension_window()}")
    click.echo(f"max_overtime={game.max_overtime()}")
    click.echo(f"max_shots={game.max_shots()}")
    click.echo(f"curve_exponent={game.curve_exponent()}")
    click.echo(f"funded={game.funded()}")
    click.echo(f"started={game.started()}")
    click.echo(f"ended={game.ended()}")
    click.echo(f"start_time={game.start_time()}")
    click.echo(f"game_duration={game.game_duration()}")
    click.echo(f"king={game.king()}")
    click.echo(f"king_since={game.king_since()}")
    click.echo(f"king_prize={game.king_prize()}")
    click.echo(f"remaining_amount={game.remaining_amount()}")


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--account",
    envvar="KINGOFTHEHILL_ACCOUNT",
    required=True,
    help="Ape account alias that created the KingOfTheHillGiveawayV52.",
)
@click.option(
    "--king-of-the-hill",
    envvar="KINGOFTHEHILL_ADDRESS",
    required=True,
    help="Deployed KingOfTheHillGiveawayV52 address.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the target without loading an account or sending a transaction.",
)
def cli(account: str, king_of_the_hill: str, dry_run: bool):
    king_of_the_hill = parse_address(king_of_the_hill, "king-of-the-hill")

    click.echo("KingOfTheHillGiveawayV52 start")
    click.echo(f"account={account}")
    click.echo(f"king_of_the_hill={king_of_the_hill}")

    if dry_run:
        return

    creator = accounts.load(account)
    game = project.KingOfTheHillGiveawayV52.at(king_of_the_hill)
    contract_creator = game.creator()
    funded = game.funded()
    started = game.started()
    ended = game.ended()
    deadline = game.deadline()

    echo_game_state(game)

    if contract_creator != creator.address:
        raise click.ClickException(
            "loaded account is not the KingOfTheHillGiveawayV52 creator"
        )

    if not funded:
        raise click.ClickException("KingOfTheHillGiveawayV52 is not funded")

    if started:
        raise click.ClickException("KingOfTheHillGiveawayV52 is already started")

    if ended:
        raise click.ClickException("KingOfTheHillGiveawayV52 is already ended")

    now = int(time.time())
    if now >= deadline:
        raise click.ClickException(f"KingOfTheHillGiveawayV52 is expired; now is {now}")

    start_receipt = game.start_game(sender=creator)
    click.echo(f"start_game_tx={tx_hash(start_receipt)}")
    echo_game_state(game)
