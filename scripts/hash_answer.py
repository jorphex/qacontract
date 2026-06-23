import click
from eth_utils import keccak, to_hex


def normalize_answer(answer: str, raw: bool) -> str:
    if raw:
        return answer

    return answer.strip().lower()


@click.command()
@click.argument("answer")
@click.option(
    "--raw",
    is_flag=True,
    help="Hash the answer exactly as provided, without lowercasing or trimming.",
)
def cli(answer: str, raw: bool):
    normalized = normalize_answer(answer, raw)
    answer_hash = to_hex(keccak(text=normalized))

    click.echo(f"normalized_answer={normalized}")
    click.echo(f"answer_hash={answer_hash}")

