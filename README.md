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

## PromptClaim Flow

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

3. Deploy on Base:

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

4. Fund the deployed claim:

```sh
uv run ape run fund_prompt_claim \
  --network base:mainnet:node \
  --account your-alias \
  --prompt-claim 0xYourDeployedPromptClaim
```

This sends two transactions:

- approve USDC spend
- call `fund()`

5. Post the prompt publicly.

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

## Safety

Never commit private keys, seed phrases, RPC keys, or real `.env` files.

Circle lists native Base USDC at:

```text
0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```
