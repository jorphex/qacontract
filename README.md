# QA Contract

Vyper contract workspace for onchain ERC20 giveaway games.

The active contract is:

- `KingOfTheHillGiveaway`: v4 king-of-the-hill giveaway where players call
  `shoot(answer)`, each wallet has limited shots, the visible king can be
  stolen until expiry, and the latest correct holder wins a prize based on
  their cumulative correct hold time.

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

## Live Gameplay Simulation

For fully automated testnet runs, put disposable testnet private keys in `.env`.
This avoids Ape passphrase and per-transaction signing prompts:

```sh
KINGOFTHEHILL_PRIVATE_KEY=0xDeployerTestnetPrivateKey
KINGOFTHEHILL_PLAYER1_PRIVATE_KEY=0xPlayer1TestnetPrivateKey
KINGOFTHEHILL_PLAYER2_PRIVATE_KEY=0xPlayer2TestnetPrivateKey
KINGOFTHEHILL_PLAYER3_PRIVATE_KEY=0xPlayer3TestnetPrivateKey
```

The alias fields become labels when raw private keys are present. The script has
defaults, so you can omit them unless you want different labels:

```sh
KINGOFTHEHILL_ACCOUNT=koth-deployer
KINGOFTHEHILL_PLAYER1_ACCOUNT=koth-player-1
KINGOFTHEHILL_PLAYER2_ACCOUNT=koth-player-2
KINGOFTHEHILL_PLAYER3_ACCOUNT=koth-player-3
```

Alternatively, import the three disposable player accounts into Ape, then set
their aliases and passphrases in `.env`:

```sh
uv run ape accounts import koth-player-1
uv run ape accounts import koth-player-2
uv run ape accounts import koth-player-3
```

```sh
KINGOFTHEHILL_PLAYER1_PASSPHRASE=player1-passphrase
KINGOFTHEHILL_PLAYER2_PASSPHRASE=player2-passphrase
KINGOFTHEHILL_PLAYER3_PASSPHRASE=player3-passphrase
```

Run fresh funded games through scripted player sequences:

```sh
uv run ape run simulate_king_of_the_hill_gameplay \
  --network base:sepolia:node \
  --scenario "p1:Y,p2:Y,p3:N" \
  --scenario "p1:Y,p2:N,p3:Y" \
  --scenario "p1:N,p2:N,p3:N,p1:Y,p2:N" \
  --finalize \
  --clawback
```

`Y` submits `KINGOFTHEHILL_CORRECT_ANSWER`; `N` submits
`KINGOFTHEHILL_WRONG_ANSWER`. The script deploys, funds, and starts a fresh
contract for each scenario, logs every read-state snapshot before and after
each shot, and writes readable event blocks to `KINGOFTHEHILL_SIM_LOG_FILE`.
Use `KINGOFTHEHILL_SIM_LOG_FORMAT=jsonl` or `--log-format jsonl` if you need
newline-delimited JSON. Logs are replaced at the start of each run; pass
`--append-log` only when you intentionally want cumulative logs.

By default, each scenario uses `KINGOFTHEHILL_SIM_GAME_SECONDS` for its fresh
deadline. The normal `KINGOFTHEHILL_DEADLINE` deploy setting is ignored by the
simulator so `--finalize` does not accidentally wait for a production-style
deadline. Use `KINGOFTHEHILL_SIM_DEADLINE` or `--deadline` only when you
intentionally want a fixed simulator deadline.

Player write function:

```text
shoot(answer)
```

Every shot captures the hill, even if the answer is wrong. Wrong kings can be
visible holders during the live game, but only correct hold time can win after
expiry.

Prize rule:

- correct hold time is banked internally per address without a public getter
- if a previous correct holder recaptures with the correct answer, their
  previous correct hold time resumes
- wrong-answer hold time never banks
- `king_prize()` is a neutral live display value for the current reign only; it
  excludes banked correct hold time so the ABI/UI does not reveal correctness
- this is not cryptographic secrecy; determined users can still inspect raw
  chain data, so commit-reveal is needed if correctness must be hidden strongly

At expiry, anyone can call:

```text
finalize()
```

`finalize()` closes the current reign, pays the latest correct holder using
their cumulative correct hold time, and leaves leftover funds in the contract
for creator clawback.

Creator clawback:

```text
clawback()
```

Clawback is allowed before start after funding, or after finalization.

## Live Site

The read-only frontend in `site/` can show real contract state. It talks to a
local RPC proxy so the Alchemy key never reaches the browser.

Set in `.env`:

```text
ALCHEMY_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
CHAIN_ID=8453
```

The site reuses the existing `KINGOFTHEHILL_ADDRESS` as the contract address.

Serve it:

```sh
uv run python scripts/serve_site.py
```

Then open `http://localhost:8080`.

For production, `scripts/cloudflare_worker.js` serves `/api/config` and
`/api/rpc` from Cloudflare so the key stays server-side.

## Player-Facing Reads

Useful read functions for Basescan or the live UI:

```text
prompt()
king()
king_since()
king_prize()
prize_for_hold_time(uint256)
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
