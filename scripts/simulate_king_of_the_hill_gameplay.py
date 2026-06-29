import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import click
from ape import accounts, networks, project
from ape.cli import ConnectedProviderCommand
from ape_accounts.accounts import ApeSigner
from dotenv import load_dotenv
from eth_utils import is_address, to_checksum_address


load_dotenv()

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

BASE_USDC_BY_NETWORK = {
    ("base", "mainnet"): BASE_USDC,
    ("base", "sepolia"): BASE_SEPOLIA_USDC,
}

DEFAULT_SCENARIOS = (
    (
        "p1:N,p1:Y,"
        "p2:Y,p2:N,"
        "p3:N,p3:N,"
        "p1:N@late,p2:N@overtime,p3:Y@overtime"
    ),
)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
TIMING_LATE = "late"
TIMING_OVERTIME = "overtime"


@dataclass(frozen=True)
class ScenarioStep:
    player_name: str
    is_correct: bool
    timing: str | None = None


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
    extension_window: int,
    max_overtime: int,
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

    if extension_window <= 0:
        raise click.BadParameter("extension-window must be greater than zero")

    if max_overtime < extension_window:
        raise click.BadParameter("max-overtime must be at least extension-window")


class NonceTracker:
    def __init__(self):
        self.next_by_address = {}

    def next_nonce(self, sender) -> int:
        address = sender.address
        if address not in self.next_by_address:
            self.next_by_address[address] = pending_nonce(address)

        nonce = self.next_by_address[address]
        self.next_by_address[address] = nonce + 1
        return nonce


def pending_nonce(address: str) -> int:
    provider = networks.active_provider
    try:
        return provider.get_nonce(address, block_id="pending")
    except TypeError:
        return provider.get_nonce(address)


def hex_value(value) -> str:
    if isinstance(value, str):
        return value if value.startswith("0x") else f"0x{value}"

    return f"0x{bytes(value).hex()}"


def normalize_private_key(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    return value if value.startswith("0x") else f"0x{value}"


def load_sender(alias: str, private_key: str | None, passphrase: str | None):
    normalized_key = normalize_private_key(private_key)
    if normalized_key:
        return ApeSigner(private_key=normalized_key)

    account = accounts.load(alias)
    if hasattr(account, "set_autosign"):
        account.set_autosign(True, passphrase=passphrase)

    return account


def parse_scenario(value: str) -> list[ScenarioStep]:
    steps = []
    for raw_step in value.split(","):
        raw_step = raw_step.strip()
        if not raw_step:
            continue

        parts = raw_step.split(":", maxsplit=1)
        if len(parts) != 2:
            raise click.BadParameter(
                "scenario steps must look like p1:Y,p2:N,p3:Y or p1:Y@late"
            )

        player_name = parts[0].strip().lower()
        answer_part = parts[1].strip()
        answer_flag = answer_part
        timing = None
        if "@" in answer_part:
            answer_flag, timing = answer_part.split("@", maxsplit=1)
            timing = timing.strip().lower()

        answer_flag = answer_flag.strip().upper()
        if player_name not in {"p1", "p2", "p3"}:
            raise click.BadParameter("scenario player must be p1, p2, or p3")
        if answer_flag not in {"Y", "N"}:
            raise click.BadParameter("scenario answer flag must be Y or N")
        if timing not in {None, TIMING_LATE, TIMING_OVERTIME}:
            raise click.BadParameter("scenario timing must be late or overtime")

        steps.append(
            ScenarioStep(
                player_name=player_name,
                is_correct=answer_flag == "Y",
                timing=timing,
            )
        )

    if not steps:
        raise click.BadParameter("scenario must include at least one shot")

    return steps


def write_log(log_path: Path, log_format: str, event: str, **values):
    entry = {"event": event, "logged_at": int(time.time()), **values}
    with log_path.open("a", encoding="utf-8") as log_file:
        if log_format == "jsonl":
            log_file.write(json.dumps(entry, sort_keys=True) + "\n")
            return

        summary = [f"event: {event}"]
        if "scenario_index" in values:
            summary.append(f"scenario: {values['scenario_index']}")
        if "shot_index" in values:
            summary.append(f"shot: {values['shot_index']}")
        if "player" in values:
            summary.append(f"player: {values['player']}")
        if "is_correct" in values:
            summary.append(f"correct: {values['is_correct']}")

        log_file.write("=" * 88 + "\n")
        log_file.write(" | ".join(summary) + "\n")
        log_file.write("-" * 88 + "\n")
        log_file.write(json.dumps(entry, indent=2, sort_keys=True) + "\n\n")


def player_reads(game, players) -> dict:
    reads = {}
    for name, account in players.items():
        reads[name] = {
            "address": account.address,
            "shots_used": game.shots_used(account.address),
            "shots_remaining": game.shots_remaining(account.address),
        }
    return reads


def snapshot(game, token_contract, players) -> dict:
    king = game.king()
    king_since = game.king_since()
    current_reign_floor_prize = 0
    current_reign_deadline_prize = 0
    if king != ZERO_ADDRESS and king_since > 0:
        current_reign_floor_prize = game.prize_at(king_since, king_since)
        current_reign_deadline_prize = game.prize_at(king_since, game.deadline())

    return {
        "address": game.address,
        "creator": game.creator(),
        "token": game.token(),
        "refund_to": game.refund_to(),
        "prompt": game.prompt(),
        "max_amount": game.max_amount(),
        "floor_amount": game.floor_amount(),
        "original_deadline": game.original_deadline(),
        "deadline": game.deadline(),
        "max_deadline": game.max_deadline(),
        "extension_window": game.extension_window(),
        "max_overtime": game.max_overtime(),
        "max_shots": game.max_shots(),
        "curve_exponent": game.curve_exponent(),
        "answer_hash": hex_value(game.answer_hash()),
        "funded": game.funded(),
        "started": game.started(),
        "ended": game.ended(),
        "start_time": game.start_time(),
        "game_duration": game.game_duration(),
        "king": king,
        "king_since": king_since,
        "shot_sequence": game.shot_sequence(),
        "king_prize": game.king_prize(),
        "current_reign_floor_prize": current_reign_floor_prize,
        "current_reign_deadline_prize": current_reign_deadline_prize,
        "prize_for_hold_time_0": game.prize_for_hold_time(0),
        "winner": game.winner(),
        "paid_amount": game.paid_amount(),
        "clawed_back_amount": game.clawed_back_amount(),
        "remaining_amount": game.remaining_amount(),
        "contract_token_balance": token_contract.balanceOf(game.address),
        "is_active": game.is_active(),
        "is_expired": game.is_expired(),
        "is_ended": game.is_ended(),
        "players": player_reads(game, players),
    }


def deploy_and_fund(
    nonce_tracker: NonceTracker,
    deployer,
    token: str,
    refund_to: str,
    prompt: str,
    max_amount: int,
    floor_amount: int,
    deadline: int,
    extension_window: int,
    max_overtime: int,
    max_shots: int,
    curve_exponent: int,
    answer_hash: str,
) -> tuple[object, object, str, str | None]:
    game = deployer.deploy(
        project.KingOfTheHillGiveawayV5,
        token,
        refund_to,
        prompt,
        max_amount,
        floor_amount,
        deadline,
        extension_window,
        max_overtime,
        max_shots,
        curve_exponent,
        answer_hash,
        nonce=nonce_tracker.next_nonce(deployer),
    )

    token_contract = project.MockERC20.at(token)
    allowance = token_contract.allowance(deployer.address, game.address)
    approve_tx = None
    if allowance < max_amount:
        approve_receipt = token_contract.approve(
            game.address,
            max_amount,
            sender=deployer,
            nonce=nonce_tracker.next_nonce(deployer),
        )
        approve_tx = tx_hash(approve_receipt)

    fund_receipt = game.fund(
        sender=deployer,
        nonce=nonce_tracker.next_nonce(deployer),
    )

    return game, token_contract, tx_hash(fund_receipt), approve_tx


def start_game(nonce_tracker: NonceTracker, deployer, game) -> str:
    start_receipt = game.start_game(
        sender=deployer,
        nonce=nonce_tracker.next_nonce(deployer),
    )

    return tx_hash(start_receipt)


def wait_until_expired(game):
    while not game.is_expired():
        deadline = game.deadline()
        now = int(time.time())
        if deadline > now:
            sleep_for = min(deadline - now + 2, 30)
        else:
            sleep_for = 5

        click.echo(f"waiting_for_expiry=deadline:{deadline},sleep:{sleep_for}")
        time.sleep(sleep_for)


def wait_until_at_or_after(timestamp: int):
    sleep_for = timestamp - int(time.time())
    if sleep_for > 0:
        time.sleep(sleep_for)


def timing_target(game, timing: str) -> int:
    if timing == TIMING_LATE:
        offset = max(1, game.extension_window() // 2)
        return game.deadline() - offset

    if timing == TIMING_OVERTIME:
        target = game.original_deadline() + 1
        if game.deadline() <= target:
            raise click.ClickException(
                "overtime timing requires an earlier late shot to extend deadline"
            )
        return target

    raise click.ClickException(f"unknown scenario timing: {timing}")


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--account",
    envvar="KINGOFTHEHILL_ACCOUNT",
    default="koth-deployer",
    show_default=True,
    help="Ape account alias to deploy/fund/start each scenario.",
)
@click.option(
    "--account-private-key",
    envvar="KINGOFTHEHILL_PRIVATE_KEY",
    default=None,
    help="Disposable testnet private key for deployer; avoids Ape prompts.",
)
@click.option(
    "--account-passphrase",
    envvar="KINGOFTHEHILL_ACCOUNT_PASSPHRASE",
    default=None,
    help="Passphrase for imported deployer alias autosigning.",
)
@click.option(
    "--player1",
    envvar="KINGOFTHEHILL_PLAYER1_ACCOUNT",
    default="koth-player-1",
    show_default=True,
    help="Ape account alias for player 1.",
)
@click.option(
    "--player1-private-key",
    envvar="KINGOFTHEHILL_PLAYER1_PRIVATE_KEY",
    default=None,
    help="Disposable testnet private key for player 1; avoids Ape prompts.",
)
@click.option(
    "--player1-passphrase",
    envvar="KINGOFTHEHILL_PLAYER1_PASSPHRASE",
    default=None,
    help="Passphrase for imported player 1 alias autosigning.",
)
@click.option(
    "--player2",
    envvar="KINGOFTHEHILL_PLAYER2_ACCOUNT",
    default="koth-player-2",
    show_default=True,
    help="Ape account alias for player 2.",
)
@click.option(
    "--player2-private-key",
    envvar="KINGOFTHEHILL_PLAYER2_PRIVATE_KEY",
    default=None,
    help="Disposable testnet private key for player 2; avoids Ape prompts.",
)
@click.option(
    "--player2-passphrase",
    envvar="KINGOFTHEHILL_PLAYER2_PASSPHRASE",
    default=None,
    help="Passphrase for imported player 2 alias autosigning.",
)
@click.option(
    "--player3",
    envvar="KINGOFTHEHILL_PLAYER3_ACCOUNT",
    default="koth-player-3",
    show_default=True,
    help="Ape account alias for player 3.",
)
@click.option(
    "--player3-private-key",
    envvar="KINGOFTHEHILL_PLAYER3_PRIVATE_KEY",
    default=None,
    help="Disposable testnet private key for player 3; avoids Ape prompts.",
)
@click.option(
    "--player3-passphrase",
    envvar="KINGOFTHEHILL_PLAYER3_PASSPHRASE",
    default=None,
    help="Passphrase for imported player 3 alias autosigning.",
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
    help="Maximum prize in token base units.",
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
    envvar="KINGOFTHEHILL_SIM_DEADLINE",
    default=None,
    type=int,
    help="Optional fixed Unix timestamp for each scenario.",
)
@click.option(
    "--game-seconds",
    envvar="KINGOFTHEHILL_SIM_GAME_SECONDS",
    default=180,
    show_default=True,
    type=int,
    help="Scenario duration when --deadline is omitted.",
)
@click.option(
    "--extension-window",
    envvar="KINGOFTHEHILL_EXTENSION_WINDOW",
    default=60,
    show_default=True,
    type=int,
    help="Minimum response window after late shots, in seconds.",
)
@click.option(
    "--max-overtime",
    envvar="KINGOFTHEHILL_MAX_OVERTIME",
    default=300,
    show_default=True,
    type=int,
    help="Maximum total deadline extension after the original deadline.",
)
@click.option(
    "--max-shots",
    envvar="KINGOFTHEHILL_MAX_SHOTS",
    default=3,
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
    "--correct-answer",
    envvar="KINGOFTHEHILL_CORRECT_ANSWER",
    required=True,
    help="Plaintext correct answer to submit for Y shots.",
)
@click.option(
    "--wrong-answer",
    envvar="KINGOFTHEHILL_WRONG_ANSWER",
    default="definitely wrong",
    show_default=True,
    help="Plaintext wrong answer to submit for N shots.",
)
@click.option(
    "--scenario",
    "scenarios",
    multiple=True,
    help=(
        "Shot sequence like p1:Y,p2:N,p3:Y. Add @late or @overtime for timed "
        "steps, e.g. p1:Y@late,p2:Y@overtime. Repeat for multiple fresh games."
    ),
)
@click.option(
    "--sleep-between-shots",
    envvar="KINGOFTHEHILL_SIM_SLEEP_BETWEEN_SHOTS",
    default=0,
    show_default=True,
    type=int,
    help="Seconds to wait between shots.",
)
@click.option(
    "--finalize/--no-finalize",
    default=False,
    show_default=True,
    help="Wait until expiry, call finalize, and log final state.",
)
@click.option(
    "--clawback/--no-clawback",
    default=False,
    show_default=True,
    help="After finalize, claw back leftovers and log final state.",
)
@click.option(
    "--yes-start",
    envvar="KINGOFTHEHILL_SIM_YES_START",
    is_flag=True,
    help="Start each freshly funded game without prompting.",
)
@click.option(
    "--log-file",
    envvar="KINGOFTHEHILL_SIM_LOG_FILE",
    default="logs/king_of_the_hill_simulation.log",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Simulation log output path.",
)
@click.option(
    "--log-format",
    envvar="KINGOFTHEHILL_SIM_LOG_FORMAT",
    default="pretty",
    show_default=True,
    type=click.Choice(["pretty", "jsonl"]),
    help="Readable pretty log blocks or newline-delimited JSON.",
)
@click.option(
    "--append-log",
    is_flag=True,
    help="Append to the existing log file instead of replacing it.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate inputs and print parsed scenarios without sending transactions.",
)
def cli(
    provider,
    account: str,
    account_private_key: str | None,
    account_passphrase: str | None,
    player1: str,
    player1_private_key: str | None,
    player1_passphrase: str | None,
    player2: str,
    player2_private_key: str | None,
    player2_passphrase: str | None,
    player3: str,
    player3_private_key: str | None,
    player3_passphrase: str | None,
    token: str | None,
    refund_to: str,
    prompt: str,
    max_amount: int,
    floor_amount: int,
    deadline: int | None,
    game_seconds: int,
    extension_window: int,
    max_overtime: int,
    max_shots: int,
    curve_exponent: int,
    answer_hash: str,
    correct_answer: str,
    wrong_answer: str,
    scenarios: tuple[str, ...],
    sleep_between_shots: int,
    finalize: bool,
    clawback: bool,
    yes_start: bool,
    log_file: Path,
    log_format: str,
    append_log: bool,
    dry_run: bool,
):
    token = parse_address(token or default_token(provider), "token")
    refund_to = parse_address(refund_to, "refund-to")
    raw_scenarios = scenarios or DEFAULT_SCENARIOS
    parsed_scenarios = [parse_scenario(scenario) for scenario in raw_scenarios]
    now = int(time.time())
    first_deadline = deadline or now + game_seconds

    validate_game_values(
        prompt,
        max_amount,
        floor_amount,
        first_deadline,
        extension_window,
        max_overtime,
        max_shots,
        curve_exponent,
    )
    if game_seconds <= 0:
        raise click.BadParameter("game-seconds must be greater than zero")
    if sleep_between_shots < 0:
        raise click.BadParameter("sleep-between-shots cannot be negative")
    if clawback and not finalize:
        raise click.BadParameter("clawback requires finalize")

    click.echo("KingOfTheHillGiveawayV5 live gameplay simulation")
    click.echo(f"account={account}")
    click.echo(f"players={player1},{player2},{player3}")
    click.echo(f"account_private_key={'set' if account_private_key else 'unset'}")
    click.echo(f"player_private_keys_set={sum(bool(k) for k in [player1_private_key, player2_private_key, player3_private_key])}/3")
    click.echo(f"token={token}")
    click.echo(f"refund_to={refund_to}")
    click.echo(f"extension_window={extension_window}")
    click.echo(f"max_overtime={max_overtime}")
    click.echo(f"yes_start={yes_start}")
    click.echo(f"log_file={log_file}")
    click.echo(f"log_format={log_format}")
    click.echo(f"append_log={append_log}")
    for index, scenario in enumerate(raw_scenarios, start=1):
        click.echo(f"scenario_{index}={scenario}")

    if dry_run:
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not append_log:
        log_file.write_text("", encoding="utf-8")

    nonce_tracker = NonceTracker()
    deployer = load_sender(account, account_private_key, account_passphrase)
    players = {
        "p1": load_sender(player1, player1_private_key, player1_passphrase),
        "p2": load_sender(player2, player2_private_key, player2_passphrase),
        "p3": load_sender(player3, player3_private_key, player3_passphrase),
    }

    for scenario_index, scenario in enumerate(parsed_scenarios, start=1):
        scenario_deadline = deadline or int(time.time()) + game_seconds
        game, token_contract, fund_tx, approve_tx = deploy_and_fund(
            nonce_tracker,
            deployer,
            token,
            refund_to,
            prompt,
            max_amount,
            floor_amount,
            scenario_deadline,
            extension_window,
            max_overtime,
            max_shots,
            curve_exponent,
            answer_hash,
        )
        click.echo(f"scenario_{scenario_index}_king_of_the_hill={game.address}")
        write_log(
            log_file,
            log_format,
            "scenario_deployed_funded",
            scenario_index=scenario_index,
            scenario=raw_scenarios[scenario_index - 1],
            game=game.address,
            approve_tx=approve_tx,
            fund_tx=fund_tx,
            state=snapshot(game, token_contract, players),
        )

        should_start = yes_start or click.confirm(
            f"Start scenario {scenario_index} now?",
            default=True,
        )
        if not should_start:
            click.echo(f"scenario_{scenario_index}_start=skipped")
            write_log(
                log_file,
                log_format,
                "scenario_start_skipped",
                scenario_index=scenario_index,
                scenario=raw_scenarios[scenario_index - 1],
                game=game.address,
                state=snapshot(game, token_contract, players),
            )
            continue

        start_tx = start_game(nonce_tracker, deployer, game)
        click.echo(f"start_game=scenario:{scenario_index},tx:{start_tx}")
        write_log(
            log_file,
            log_format,
            "scenario_started",
            scenario_index=scenario_index,
            scenario=raw_scenarios[scenario_index - 1],
            game=game.address,
            start_tx=start_tx,
            state=snapshot(game, token_contract, players),
        )

        for shot_index, step in enumerate(scenario, start=1):
            if step.timing is not None:
                target = timing_target(game, step.timing)
                write_log(
                    log_file,
                    log_format,
                    "before_timing_wait",
                    scenario_index=scenario_index,
                    shot_index=shot_index,
                    timing=step.timing,
                    timing_target=target,
                    state=snapshot(game, token_contract, players),
                )
                wait_until_at_or_after(target)
                write_log(
                    log_file,
                    log_format,
                    "after_timing_wait",
                    scenario_index=scenario_index,
                    shot_index=shot_index,
                    timing=step.timing,
                    timing_target=target,
                    state=snapshot(game, token_contract, players),
                )

            player_name = step.player_name
            is_correct = step.is_correct
            answer = correct_answer if is_correct else wrong_answer
            player = players[player_name]
            write_log(
                log_file,
                log_format,
                "before_shot",
                scenario_index=scenario_index,
                shot_index=shot_index,
                player=player_name,
                player_address=player.address,
                is_correct=is_correct,
                timing=step.timing,
                state=snapshot(game, token_contract, players),
            )
            receipt = game.shoot(
                answer,
                sender=player,
                nonce=nonce_tracker.next_nonce(player),
            )
            click.echo(
                "shot="
                f"scenario:{scenario_index},index:{shot_index},"
                f"player:{player_name},correct:{is_correct},"
                f"timing:{step.timing or 'now'},tx:{tx_hash(receipt)}"
            )
            write_log(
                log_file,
                log_format,
                "after_shot",
                scenario_index=scenario_index,
                shot_index=shot_index,
                player=player_name,
                player_address=player.address,
                is_correct=is_correct,
                timing=step.timing,
                tx=tx_hash(receipt),
                state=snapshot(game, token_contract, players),
            )
            if sleep_between_shots > 0:
                time.sleep(sleep_between_shots)

        if finalize:
            write_log(
                log_file,
                log_format,
                "before_finalize_wait",
                scenario_index=scenario_index,
                state=snapshot(game, token_contract, players),
            )
            wait_until_expired(game)
            finalize_receipt = game.finalize(
                sender=deployer,
                nonce=nonce_tracker.next_nonce(deployer),
            )
            click.echo(
                f"finalize=scenario:{scenario_index},tx:{tx_hash(finalize_receipt)}"
            )
            write_log(
                log_file,
                log_format,
                "after_finalize",
                scenario_index=scenario_index,
                tx=tx_hash(finalize_receipt),
                state=snapshot(game, token_contract, players),
            )

            if clawback and game.remaining_amount() > 0:
                clawback_receipt = game.clawback(
                    sender=deployer,
                    nonce=nonce_tracker.next_nonce(deployer),
                )
                click.echo(
                    f"clawback=scenario:{scenario_index},tx:{tx_hash(clawback_receipt)}"
                )
                write_log(
                    log_file,
                    log_format,
                    "after_clawback",
                    scenario_index=scenario_index,
                    tx=tx_hash(clawback_receipt),
                    state=snapshot(game, token_contract, players),
                )
