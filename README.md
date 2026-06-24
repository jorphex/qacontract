# QA Contract

Vyper contract workspace for prompt-gated ERC20 giveaways:

- creator funds an ERC20 prize
- anyone can submit the correct answer before the deadline
- creator can claw back when the game rules allow it

Two contract versions are kept in this repo:

- `PromptClaim`: v1 fixed-prize giveaway.
- `PuzzleGiveaway`: v2 giveaway with manual start and a time-ramped prize.

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

## Answer Hashes

1. Import or create an Ape account:

```sh
uv run ape accounts import your-alias
```

2. Compute the answer hash:

```sh
uv run ape run hash_answer "Blue Candle"
```

The helper hashes the answer exactly as typed, because the contract verifies the
exact submitted string. In this example, the winning answer is:

```text
Blue Candle
```

Use `--normalize` only if you intentionally want a stripped, lowercase answer.
For example, `uv run ape run hash_answer "Blue Candle" --normalize` hashes:

```text
blue candle
```

## PromptClaim Flow

Deploy v1 on Base:

```sh
uv run ape run deploy_prompt_claim \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --amount 1000000 \
  --deadline 1893456000 \
  --answer-hash 0xYourAnswerHash
```

The deploy and funding scripts also read `.env` automatically, so you can omit
flags that are already defined there.

`1000000` is `1 USDC` because USDC has 6 decimals.

The deploy script defaults to native USDC for the selected Base network when
`PROMPTCLAIM_TOKEN` and `--token` are omitted. Base mainnet USDC is:

```text
0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```

Fund the deployed claim:

```sh
uv run ape run fund_prompt_claim \
  --network base:mainnet:node \
  --account your-alias \
  --prompt-claim 0xYourDeployedPromptClaim
```

This sends two transactions:

- approve USDC spend
- call `fund()`

Post the prompt publicly.

Anyone can claim before the deadline with:

```text
claim(answer)
```

`answer` is a text string, such as `blue candle`.
Case, spaces, and spelling must match the hashed answer exactly unless you
created the hash from a normalized answer and told players that normalized form.
Wrong answers are accepted onchain as attempts, but they do not settle the claim
or transfer the prize.

If nobody claims before the deadline, the creator calls:

```text
clawback()
```

## PuzzleGiveaway Flow

Deploy and fund v2 on Base:

```sh
uv run ape run deploy_and_fund_puzzle_giveaway \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --max-amount 1000000 \
  --floor-amount 250000 \
  --deadline 1893456000 \
  --cliff-seconds 60 \
  --answer-hash 0xYourAnswerHash
```

The script deploys `PuzzleGiveaway`, approves token spend, and calls `fund()`.
It does not start the game unless `--start-now` is passed. The default token is
native USDC for the selected Base network when `PUZZLEGIVEAWAY_TOKEN` and
`--token` are omitted.

Start the game when ready:

```sh
uv run ape run start_puzzle_giveaway \
  --network base:mainnet:node \
  --account your-alias \
  --puzzle-giveaway 0xYourDeployedPuzzleGiveaway
```

The player-facing write function is:

```text
submit_answer(answer)
```

`claimable_amount()` shows the current prize. It starts at `floor_amount`, stays
there for `cliff_seconds`, then ramps linearly to `max_amount` at `deadline`.
Wrong answers emit an event but do not settle the game. A correct answer pays
the current claimable amount and ends the game. The creator can call
`clawback()` to recover funds before start, after expiry, or after a winner
leaves leftover funds.

## Safety

Never commit private keys, seed phrases, RPC keys, or real `.env` files.

Circle lists native Base USDC at:

```text
0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```
