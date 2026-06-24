import click
from eth_utils import keccak, to_hex


def answer_to_hash(answer: str, normalize: bool) -> str:
    if normalize:
        return answer.strip().lower()

    return answer


@click.command()
@click.argument("answer")
@click.option(
    "--normalize",
    is_flag=True,
    help="Strip and lowercase before hashing.",
)
def cli(answer: str, normalize: bool):
    hashed_answer = answer_to_hash(answer, normalize)
    answer_hash = to_hex(keccak(text=hashed_answer))

    click.echo(f"hashed_answer={hashed_answer}")
    click.echo(f"answer_hash={answer_hash}")
