# QA Contract

Vyper contract workspace for a single-use prompt-gated ERC20 giveaway:

- creator funds an ERC20 prize
- anyone can claim before the deadline with the correct answer
- creator can claw back after the deadline if unclaimed

## Development

Install dependencies:

```sh
uv sync
```

Compile contracts:

```sh
uv run ape compile
```

Run tests:

```sh
uv run ape test
```
