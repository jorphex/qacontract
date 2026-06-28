# QA Contract

Vyper contract workspace for onchain ERC20 giveaway games.

The active contract is:

- `KingOfTheHillGiveaway`: v4 king-of-the-hill giveaway where players call
  `shoot(answer)`, each wallet has limited shots, the visible king can be
  stolen until expiry, and the latest correct reign wins a prize based on how
  long that reign held.

Older v1-v3 prompt-claim and puzzle-ramp experiments are preserved under
`deprecated/`.

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

Run lint:

```sh
uv run ruff check
```

## Answer Hashes

Import or create an Ape account:

```sh
uv run ape accounts import your-alias
```

Compute the answer hash:

```sh
uv run ape run hash_answer "Blue Candle"
```

The helper hashes the answer exactly as typed, because the contract verifies the
exact submitted string. In this example, the winning answer is:

```text
Blue Candle
```

Use `--normalize` only if you intentionally want a stripped, lowercase answer.

## KingOfTheHillGiveaway Flow

Deploy and fund v4 on Base mainnet:

```sh
uv run ape run deploy_and_fund_king_of_the_hill \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --prompt "What is the answer?" \
  --max-amount 1000000 \
  --floor-amount 10000 \
  --deadline 1893456000 \
  --max-shots 5 \
  --curve-exponent 2 \
  --answer-hash 0xYourAnswerHash
```

The script deploys `KingOfTheHillGiveaway`, stores the public `prompt`,
approves token spend, and calls `fund()`. It does not start the game unless
`--start-now` is passed.

`1000000` is `1 USDC` because USDC has 6 decimals.

The default token is native USDC for the selected Base network when
`KINGOFTHEHILL_TOKEN` and `--token` are omitted.

For a Base Sepolia test deployment, use the same command with:

```sh
--network base:sepolia:node
```

The script defaults to Circle's Base Sepolia USDC when that network is selected:

```text
0x036CbD53842c5426634e7929541eC2318f3dCF7e
```

An explicit `KINGOFTHEHILL_TOKEN` in `.env` or a `--token` flag always
overrides the network default.

Start the game when ready:

```sh
uv run ape run start_king_of_the_hill \
  --network base:mainnet:node \
  --account your-alias \
  --king-of-the-hill 0xYourDeployedKingOfTheHillGiveaway
```

Player write function:

```text
shoot(answer)
```

Every shot captures the hill, even if the answer is wrong. Wrong kings can be
visible holders during the live game, but only correct reigns can win after
expiry.

At expiry, anyone can call:

```text
finalize()
```

`finalize()` closes the current reign, pays the latest correct reign, and leaves
leftover funds in the contract for creator clawback.

Creator clawback:

```text
clawback()
```

Clawback is allowed before start after funding, or after finalization.

## Player-Facing Reads

Useful read functions for Basescan or a future UI:

```text
prompt()
king()
king_since()
king_prize()
shots_used(address)
shots_remaining(address)
winner()
paid_amount()
remaining_amount()
is_active()
is_expired()
is_ended()
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
