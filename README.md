# QA Contract

Vyper contract workspace for prompt-gated ERC20 giveaways:

- creator funds an ERC20 prize
- anyone can submit the correct answer before the deadline
- creator can claw back when the game rules allow it

Three contract versions are kept in this repo:

- `PromptClaim`: v1 fixed-prize giveaway.
- `PuzzleGiveaway`: v2 giveaway with manual start and a time-ramped prize.
- `PuzzleGiveawayV3`: v3 giveaway with manual start and a convex prize ramp.

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

Deploy and fund v2 on Base mainnet:

```sh
uv run ape run deploy_and_fund_puzzle_giveaway \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --prompt "What is the answer?" \
  --max-amount 1000000 \
  --floor-amount 250000 \
  --deadline 1893456000 \
  --cliff-seconds 60 \
  --answer-hash 0xYourAnswerHash
```

The script deploys `PuzzleGiveaway`, stores the public `prompt`, approves token
spend, and calls `fund()`. It does not start the game unless `--start-now` is
passed. The default token is native USDC for the selected Base network when
`PUZZLEGIVEAWAY_TOKEN` and `--token` are omitted.

For a Base Sepolia test deployment, use the same command with:

```sh
--network base:sepolia:node
```

The script defaults to Circle's Base Sepolia USDC when that network is selected:

```text
0x036CbD53842c5426634e7929541eC2318f3dCF7e
```

An explicit `PUZZLEGIVEAWAY_TOKEN` in `.env` or a `--token` flag always
overrides the network default, so remove or update it before testnet runs.

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

`prompt()` shows the public puzzle prompt. `claimable_amount()` shows the
current prize. It starts at `floor_amount`, stays there for `cliff_seconds`,
then ramps linearly to `max_amount` at `deadline`. Wrong answers emit an event
but do not settle the game. A correct answer pays the current claimable amount
and ends the game. The creator can call `clawback()` to recover funds before
start, after expiry, or after a winner leaves leftover funds.

## PuzzleGiveawayV3 Flow

Deploy and fund v3 on Base mainnet:

```sh
uv run ape run deploy_and_fund_puzzle_giveaway_v3 \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --prompt "What is the answer?" \
  --max-amount 1000000 \
  --floor-amount 10000 \
  --deadline 1893456000 \
  --cliff-seconds 60 \
  --curve-exponent 2 \
  --answer-hash 0xYourAnswerHash
```

`--curve-exponent 2` creates a quadratic ramp. `--curve-exponent 3` creates a
cubic ramp. Both keep the prize flat at `floor_amount` through the cliff, then
back-load the increase toward expiry. The script defaults to quadratic when the
flag and `PUZZLEGIVEAWAY_V3_CURVE_EXPONENT` are omitted.

For a Base Sepolia test deployment, use the same command with:

```sh
--network base:sepolia:node
```

The v3 script defaults to Circle's Base Sepolia USDC when that network is
selected, unless `PUZZLEGIVEAWAY_V3_TOKEN` or `--token` is set:

```text
0x036CbD53842c5426634e7929541eC2318f3dCF7e
```

Start the v3 game when ready:

```sh
uv run ape run start_puzzle_giveaway_v3 \
  --network base:mainnet:node \
  --account your-alias \
  --puzzle-giveaway-v3 0xYourDeployedPuzzleGiveawayV3
```

## Safety

Never commit private keys, seed phrases, RPC keys, or real `.env` files.

Circle lists native Base USDC at:

```text
0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```

Circle lists native Base Sepolia USDC at:

```text
0x036CbD53842c5426634e7929541eC2318f3dCF7e
```
