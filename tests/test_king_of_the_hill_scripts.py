from types import SimpleNamespace

import click
import pytest
from eth_utils import keccak

from scripts import (
    deploy_and_fund_king_of_the_hill,
    simulate_king_of_the_hill_gameplay,
    start_king_of_the_hill,
)


AMOUNT = 1_000_000
FLOOR = 100_000
MAX_SHOTS = 3
EXTENSION_WINDOW = 60
MAX_OVERTIME = 300
PROMPT = "What color is the candle?"
ANSWER_HASH = keccak(text="blue candle")
ANSWER_HASH_HEX = f"0x{ANSWER_HASH.hex()}"


def provider(ecosystem_name: str, network_name: str):
    return SimpleNamespace(
        network=SimpleNamespace(
            ecosystem=SimpleNamespace(name=ecosystem_name),
            name=network_name,
        )
    )


def deploy_funded_game(project, accounts, chain):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    game = project.KingOfTheHillGiveawayV51.deploy(
        token.address,
        refund_to.address,
        PROMPT,
        AMOUNT,
        FLOOR,
        chain.pending_timestamp + 3600,
        EXTENSION_WINDOW,
        MAX_OVERTIME,
        MAX_SHOTS,
        2,
        ANSWER_HASH,
        sender=creator,
    )
    token.approve(game.address, AMOUNT, sender=creator)
    game.fund(sender=creator)
    return game


def deployed_address_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("king_of_the_hill="):
            return line.split("=", maxsplit=1)[1]

    raise AssertionError("missing king_of_the_hill output")


def simulated_address_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("scenario_1_king_of_the_hill="):
            return line.split("=", maxsplit=1)[1]

    raise AssertionError("missing scenario game output")


def clear_simulation_env(monkeypatch):
    for name in (
        "KINGOFTHEHILL_PRIVATE_KEY",
        "KINGOFTHEHILL_PLAYER1_PRIVATE_KEY",
        "KINGOFTHEHILL_PLAYER2_PRIVATE_KEY",
        "KINGOFTHEHILL_PLAYER3_PRIVATE_KEY",
        "KINGOFTHEHILL_ACCOUNT_PASSPHRASE",
        "KINGOFTHEHILL_PLAYER1_PASSPHRASE",
        "KINGOFTHEHILL_PLAYER2_PASSPHRASE",
        "KINGOFTHEHILL_PLAYER3_PASSPHRASE",
        "KINGOFTHEHILL_SIM_DEADLINE",
        "KINGOFTHEHILL_SIM_SLEEP_BETWEEN_SHOTS",
        "KINGOFTHEHILL_SIM_LOG_FORMAT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_token_uses_base_sepolia_when_selected(monkeypatch):
    monkeypatch.delenv("KINGOFTHEHILL_TOKEN", raising=False)

    token = deploy_and_fund_king_of_the_hill.default_token(
        provider("base", "sepolia")
    )

    assert token == deploy_and_fund_king_of_the_hill.BASE_SEPOLIA_USDC


def test_default_token_uses_active_provider_when_callback_provider_missing(
    monkeypatch,
):
    monkeypatch.delenv("KINGOFTHEHILL_TOKEN", raising=False)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.networks,
        "active_provider",
        provider("base", "sepolia"),
    )

    token = deploy_and_fund_king_of_the_hill.default_token(None)

    assert token == deploy_and_fund_king_of_the_hill.BASE_SEPOLIA_USDC


def test_explicit_token_env_overrides_network_default(monkeypatch):
    token_override = "0x000000000000000000000000000000000000dEaD"
    monkeypatch.setenv("KINGOFTHEHILL_TOKEN", token_override)

    token = deploy_and_fund_king_of_the_hill.default_token(
        provider("base", "sepolia")
    )

    assert token == token_override


def test_validate_game_values_rejects_bad_curve_exponent(monkeypatch):
    monkeypatch.setattr(deploy_and_fund_king_of_the_hill.time, "time", lambda: 100)

    with pytest.raises(click.BadParameter, match="curve-exponent must be 1, 2, or 3"):
        deploy_and_fund_king_of_the_hill.validate_game_values(
            prompt=PROMPT,
            max_amount=100,
            floor_amount=1,
            deadline=200,
            extension_window=EXTENSION_WINDOW,
            max_overtime=MAX_OVERTIME,
            max_shots=MAX_SHOTS,
            curve_exponent=4,
        )


def test_deploy_and_fund_script_deploys_game(project, accounts, capsys, monkeypatch):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_king_of_the_hill.cli.main(
        args=[
            "--account",
            "creator",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveawayV51.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.prompt() == PROMPT
    assert game.max_shots() == MAX_SHOTS
    assert game.extension_window() == EXTENSION_WINDOW
    assert game.max_overtime() == MAX_OVERTIME
    assert game.curve_exponent() == 2
    assert game.funded()
    assert not game.started()
    assert token.balanceOf(game.address) == AMOUNT


def test_deploy_and_fund_script_can_start_game(
    project, accounts, capsys, monkeypatch
):
    creator = accounts[0]
    refund_to = accounts[2]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        deploy_and_fund_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = deploy_and_fund_king_of_the_hill.cli.main(
        args=[
            "--account",
            "creator",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "3",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--start-now",
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveawayV51.at(
        deployed_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.curve_exponent() == 3
    assert game.funded()
    assert game.started()
    assert game.king_prize() == 0


def test_start_script_starts_funded_game(project, accounts, chain, monkeypatch):
    creator = accounts[0]
    game = deploy_funded_game(project, accounts, chain)
    monkeypatch.setattr(
        start_king_of_the_hill.accounts,
        "load",
        lambda _alias: creator,
    )

    result = start_king_of_the_hill.cli.main(
        args=[
            "--account",
            "creator",
            "--king-of-the-hill",
            game.address,
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
    assert game.started()
    assert game.start_time() > 0


def test_simulation_nonce_tracker_uses_pending_nonce_per_sender(
    accounts, monkeypatch
):
    calls = []
    pending = {
        accounts[0].address: 7,
        accounts[1].address: 11,
    }
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay,
        "pending_nonce",
        lambda address: calls.append(address) or pending[address],
    )
    tracker = simulate_king_of_the_hill_gameplay.NonceTracker()

    assert tracker.next_nonce(accounts[0]) == 7
    assert tracker.next_nonce(accounts[0]) == 8
    assert tracker.next_nonce(accounts[1]) == 11
    assert tracker.next_nonce(accounts[0]) == 9
    assert calls == [accounts[0].address, accounts[1].address]


def test_simulation_wait_until_expired_polls_contract_read(monkeypatch):
    class FakeGame:
        def __init__(self):
            self.expired_reads = [False, False, True]

        def is_expired(self):
            return self.expired_reads.pop(0)

        def deadline(self):
            return 100

    sleeps = []
    monkeypatch.setattr(simulate_king_of_the_hill_gameplay.time, "time", lambda: 200)
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.time,
        "sleep",
        lambda seconds: sleeps.append(seconds),
    )

    simulate_king_of_the_hill_gameplay.wait_until_expired(FakeGame())

    assert sleeps == [5, 5]


def test_simulation_scenario_parses_timed_steps():
    steps = simulate_king_of_the_hill_gameplay.parse_scenario(
        "p1:Y@late,p2:N@overtime,p3:Y"
    )

    assert steps[0].player_name == "p1"
    assert steps[0].is_correct
    assert steps[0].timing == "late"
    assert steps[1].player_name == "p2"
    assert not steps[1].is_correct
    assert steps[1].timing == "overtime"
    assert steps[2].player_name == "p3"
    assert steps[2].is_correct
    assert steps[2].timing is None

    with pytest.raises(click.BadParameter, match="timing must be late or overtime"):
        simulate_king_of_the_hill_gameplay.parse_scenario("p1:Y@soon")


def test_default_simulation_scenario_uses_all_player_shots():
    steps = simulate_king_of_the_hill_gameplay.parse_scenario(
        simulate_king_of_the_hill_gameplay.DEFAULT_SCENARIOS[0]
    )

    assert len(steps) == 9
    assert sum(step.player_name == "p1" for step in steps) == 3
    assert sum(step.player_name == "p2" for step in steps) == 3
    assert sum(step.player_name == "p3" for step in steps) == 3
    assert all(step.timing is None for step in steps[:6])
    assert steps[6].player_name == "p1"
    assert not steps[6].is_correct
    assert steps[6].timing == "late"
    assert steps[7].player_name == "p2"
    assert not steps[7].is_correct
    assert steps[7].timing == "overtime"
    assert steps[8].player_name == "p3"
    assert steps[8].is_correct
    assert steps[8].timing == "overtime"


def test_simulation_script_runs_three_player_scenario(
    project, accounts, capsys, monkeypatch, tmp_path
):
    clear_simulation_env(monkeypatch)
    creator = accounts[0]
    player1 = accounts[1]
    player2 = accounts[2]
    player3 = accounts[3]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    aliases = {
        "creator": creator,
        "player1": player1,
        "player2": player2,
        "player3": player3,
    }
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.accounts,
        "load",
        lambda alias: aliases[alias],
    )
    log_file = tmp_path / "simulation.log"
    log_file.write_text("old noisy log\n")

    result = simulate_king_of_the_hill_gameplay.cli.main(
        args=[
            "--account",
            "creator",
            "--player1",
            "player1",
            "--player2",
            "player2",
            "--player3",
            "player3",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--correct-answer",
            "blue candle",
            "--wrong-answer",
            "red candle",
            "--scenario",
            "p1:Y,p2:N,p3:Y",
            "--yes-start",
            "--log-file",
            str(log_file),
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveawayV51.at(
        simulated_address_from_output(capsys.readouterr().out)
    )
    log_text = log_file.read_text()

    assert result is None
    assert game.started()
    assert game.king() == player3.address
    assert game.shots_used(player1) == 1
    assert game.shots_used(player2) == 1
    assert game.shots_used(player3) == 1
    assert token.balanceOf(game.address) == AMOUNT
    assert "old noisy log" not in log_text
    assert "event: scenario_started | scenario: 1" in log_text
    assert (
        "event: before_shot | scenario: 1 | shot: 1 | player: p1 | correct: True"
        in log_text
    )
    assert (
        "event: after_shot | scenario: 1 | shot: 3 | player: p3 | correct: True"
        in log_text
    )
    assert '"state": {' in log_text


def test_simulation_script_can_run_timed_overtime_scenario(
    project, accounts, capsys, monkeypatch, tmp_path, chain
):
    clear_simulation_env(monkeypatch)
    creator = accounts[0]
    player1 = accounts[1]
    player2 = accounts[2]
    player3 = accounts[3]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    aliases = {
        "creator": creator,
        "player1": player1,
        "player2": player2,
        "player3": player3,
    }
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.accounts,
        "load",
        lambda alias: aliases[alias],
    )
    waits = []

    def fake_wait(timestamp):
        waits.append(timestamp)
        chain.pending_timestamp = timestamp
        chain.mine()

    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay,
        "wait_until_at_or_after",
        fake_wait,
    )
    log_file = tmp_path / "simulation.log"
    deadline = chain.pending_timestamp + 120

    result = simulate_king_of_the_hill_gameplay.cli.main(
        args=[
            "--account",
            "creator",
            "--player1",
            "player1",
            "--player2",
            "player2",
            "--player3",
            "player3",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            str(deadline),
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--correct-answer",
            "blue candle",
            "--wrong-answer",
            "red candle",
            "--scenario",
            "p1:Y@late,p2:Y@overtime,p3:N",
            "--yes-start",
            "--log-file",
            str(log_file),
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveawayV51.at(
        simulated_address_from_output(capsys.readouterr().out)
    )
    log_text = log_file.read_text()

    assert result is None
    assert len(waits) == 2
    assert waits[0] < game.original_deadline()
    assert waits[1] > game.original_deadline()
    assert game.deadline() > game.original_deadline()
    assert game.king() == player3.address
    assert game.shots_used(player1) == 1
    assert game.shots_used(player2) == 1
    assert game.shots_used(player3) == 1
    assert "event: before_timing_wait | scenario: 1 | shot: 1" in log_text
    assert "event: after_timing_wait | scenario: 1 | shot: 2" in log_text
    assert '"timing": "overtime"' in log_text


def test_simulation_script_can_pause_before_start(
    project, accounts, capsys, monkeypatch, tmp_path
):
    clear_simulation_env(monkeypatch)
    creator = accounts[0]
    player1 = accounts[1]
    player2 = accounts[2]
    player3 = accounts[3]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    aliases = {
        "creator": creator,
        "player1": player1,
        "player2": player2,
        "player3": player3,
    }
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.accounts,
        "load",
        lambda alias: aliases[alias],
    )
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.click,
        "confirm",
        lambda *_args, **_kwargs: False,
    )
    log_file = tmp_path / "simulation.log"

    result = simulate_king_of_the_hill_gameplay.cli.main(
        args=[
            "--account",
            "creator",
            "--player1",
            "player1",
            "--player2",
            "player2",
            "--player3",
            "player3",
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--correct-answer",
            "blue candle",
            "--wrong-answer",
            "red candle",
            "--scenario",
            "p1:Y",
            "--log-file",
            str(log_file),
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    output = capsys.readouterr().out
    game = project.KingOfTheHillGiveawayV51.at(
        simulated_address_from_output(output)
    )
    log_text = log_file.read_text()

    assert result is None
    assert game.funded()
    assert not game.started()
    assert game.shot_sequence() == 0
    assert "scenario_1_start=skipped" in output
    assert "event: scenario_deployed_funded | scenario: 1" in log_text
    assert "event: scenario_start_skipped | scenario: 1" in log_text


def test_simulation_script_can_use_raw_private_keys_without_loading_aliases(
    project, accounts, capsys, monkeypatch, tmp_path
):
    clear_simulation_env(monkeypatch)
    creator = accounts[0]
    player1 = accounts[1]
    player2 = accounts[2]
    player3 = accounts[3]
    refund_to = accounts[4]
    token = project.MockERC20.deploy("USD Coin", "USDC", 6, sender=creator)
    token.mint(creator, AMOUNT, sender=creator)
    monkeypatch.setattr(
        simulate_king_of_the_hill_gameplay.accounts,
        "load",
        lambda _alias: pytest.fail("accounts.load should not be called"),
    )
    log_file = tmp_path / "simulation.jsonl"

    result = simulate_king_of_the_hill_gameplay.cli.main(
        args=[
            "--account",
            "creator",
            "--account-private-key",
            str(creator.private_key),
            "--player1",
            "player1",
            "--player1-private-key",
            str(player1.private_key),
            "--player2",
            "player2",
            "--player2-private-key",
            str(player2.private_key),
            "--player3",
            "player3",
            "--player3-private-key",
            str(player3.private_key),
            "--token",
            token.address,
            "--refund-to",
            refund_to.address,
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--deadline",
            "4102444800",
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--max-shots",
            str(MAX_SHOTS),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--correct-answer",
            "blue candle",
            "--wrong-answer",
            "red candle",
            "--scenario",
            "p1:Y,p2:N,p3:Y",
            "--yes-start",
            "--log-file",
            str(log_file),
            "--log-format",
            "jsonl",
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    game = project.KingOfTheHillGiveawayV51.at(
        simulated_address_from_output(capsys.readouterr().out)
    )

    assert result is None
    assert game.started()
    assert game.king() == player3.address
    assert len(log_file.read_text().splitlines()) == 8


def test_simulation_script_ignores_deploy_deadline_env(monkeypatch, tmp_path):
    clear_simulation_env(monkeypatch)
    monkeypatch.setenv("KINGOFTHEHILL_DEADLINE", "1")
    monkeypatch.setattr(simulate_king_of_the_hill_gameplay.time, "time", lambda: 100)

    result = simulate_king_of_the_hill_gameplay.cli.main(
        args=[
            "--token",
            "0x000000000000000000000000000000000000dEaD",
            "--refund-to",
            "0x000000000000000000000000000000000000bEEF",
            "--prompt",
            PROMPT,
            "--max-amount",
            str(AMOUNT),
            "--floor-amount",
            str(FLOOR),
            "--max-shots",
            str(MAX_SHOTS),
            "--extension-window",
            str(EXTENSION_WINDOW),
            "--max-overtime",
            str(MAX_OVERTIME),
            "--curve-exponent",
            "2",
            "--answer-hash",
            ANSWER_HASH_HEX,
            "--correct-answer",
            "blue candle",
            "--log-file",
            str(tmp_path / "simulation.jsonl"),
            "--dry-run",
            "--network",
            "ethereum:local:test",
        ],
        standalone_mode=False,
    )

    assert result is None
