# QA Contract

Vyper contract workspace for onchain ERC20 giveaway games.

The active contract is:

- `KingOfTheHillGiveawayV52`: v5.2 king-of-the-hill giveaway where players call
  `shoot(answer)`, each wallet has limited shots, the visible king can be
  stolen until the live deadline, late shots extend the live deadline within a
  capped overtime window, and the correct holder with the highest banked prize
  wins using cumulative correct hold time capped at the original deadline.
  V5.2 also supports an optional hidden sidequest answer that grants a one-time
  capped hold-time boost through the same `shoot(answer)` function.

Older v1-v5 prompt-claim, puzzle-ramp, and KOTH experiments are preserved under
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

## KingOfTheHillGiveawayV52 Flow

Deploy and fund v5.2 on Base mainnet:

```sh
uv run ape run deploy_and_fund_king_of_the_hill \
  --network base:mainnet:node \
  --account your-alias \
  --refund-to 0xYourRefundAddress \
  --prompt "What is the answer?" \
  --side-quest "" \
  --max-amount 1000000 \
  --floor-amount 10000 \
  --deadline 1893456000 \
  --extension-window 60 \
  --max-overtime 300 \
  --max-shots 3 \
  --curve-exponent 2 \
  --answer-hash 0xYourAnswerHash \
  --side-quest-hash 0x0000000000000000000000000000000000000000000000000000000000000000 \
  --side-quest-boost-bps 0
```

The script deploys `KingOfTheHillGiveawayV52`, stores the public `prompt` and
optional public `side_quest` clue, approves token spend, and calls `fund()`. It
does not start the game unless `--start-now` is passed.

`1000000` is `1 USDC` because USDC has 6 decimals.

`--deadline` is the original prize-growth deadline. `--extension-window`
prevents final-second snipes by extending the live shooting deadline when a
shot lands with less than that much time remaining. `--max-overtime` caps total
extension. Prize growth never continues past the original deadline, so overtime
shots can still win but cannot push the prize above the original cap.

`--side-quest` is an optional public clue exposed by the `side_quest()` read
function. `--side-quest-hash` is the hidden second answer hash. If it is
nonzero, that answer also counts as correct when submitted through
`shoot(answer)`.
`--side-quest-boost-bps` is a one-time boost per address in basis points of the
game duration. `1000` means 10%; `10000` means 100%. The boost adds hold time,
not tokens, and the result is capped to the elapsed hold time possible from
game start to that shot/reign record time. This means the sidequest can help a
player catch up to the global release trajectory, but cannot exceed it.

Leave `--side-quest` empty and both sidequest numeric/hash values at zero to
disable the feature. If `--side-quest`, `--side-quest-hash`, or
`--side-quest-boost-bps` is set, the public clue and hidden hash must both be
configured, and the sidequest hash must differ from `--answer-hash`.

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

The simulator deploys and funds a fresh game, prints
`scenario_N_king_of_the_hill=...`, then asks before calling `start_game()`.
Use that pause to set `KINGOFTHEHILL_ADDRESS` for the live UI and confirm the
contract is visible before the game clock starts. Pass `--yes-start` only when
you want unattended runs.

With no `--scenario`, the default run exercises v5.2 overtime in one game and
assumes the default `--max-shots 3`:

```text
p1:N,p1:Y,
p2:Y,p2:N,
p3:N,p3:N,
p1:N@late,p2:N@overtime,p3:Y@overtime
```

That means player 1 spends all shots before the original deadline, player 2's
last shot is wrong in overtime, and player 3's last shot is correct in
overtime.

To test a different v5.2 overtime path, add timed shot suffixes:

```sh
uv run ape run simulate_king_of_the_hill_gameplay \
  --network base:sepolia:node \
  --game-seconds 90 \
  --extension-window 30 \
  --max-overtime 90 \
  --scenario "p1:Y@late,p2:Y@overtime,p3:N" \
  --yes-start \
  --finalize \
  --clawback
```

`@late` waits until the shot is inside the current extension window, so it
should extend the live deadline. `@overtime` waits until after
`original_deadline()` and requires an earlier late shot to have extended the
live deadline first. Ordinary steps like `p3:N` still execute immediately.

`Y` submits `KINGOFTHEHILL_CORRECT_ANSWER`; `N` submits
`KINGOFTHEHILL_WRONG_ANSWER`; `S` submits
`KINGOFTHEHILL_SIDE_QUEST_ANSWER`. `S` scenarios require
`KINGOFTHEHILL_SIDE_QUEST` and `KINGOFTHEHILL_SIDE_QUEST_HASH` to be set. The
script deploys, funds, and starts a fresh contract for each scenario, logs
every read-state snapshot before and after each shot, and writes readable event
blocks to `KINGOFTHEHILL_SIM_LOG_FILE`. Use `KINGOFTHEHILL_SIM_LOG_FORMAT=jsonl` or
`--log-format jsonl` if you need newline-delimited JSON. Logs are replaced at
the start of each run; pass `--append-log` only when you intentionally want
cumulative logs.

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
- a hidden sidequest answer can count as correct and apply a one-time
  hold-time boost, capped by elapsed time since game start
- wrong-answer hold time never banks
- `deadline()` is the live shooting/finalization deadline and can extend
- `original_deadline()` is the fixed prize-growth cap
- overtime does not refill shots or increase prize growth past the original
  deadline
- `king_prize()` is a neutral live display value for the current reign only; it
  excludes banked correct hold time so the ABI/UI does not reveal correctness
- this is not cryptographic secrecy; determined users can still inspect raw
  chain data, so commit-reveal is needed if correctness must be hidden strongly

After the live deadline, anyone can call:

```text
finalize()
```

`finalize()` closes the current reign, pays the correct holder with the
highest banked prize, and leaves leftover funds in the contract for creator
clawback.

Creator clawback:

```text
clawback()
```

Clawback is allowed before start after funding, or after finalization.

## Live Site

The read-only frontend in `site/` renders the full game lifecycle: no configured
game, funded/not-started, live, overtime, expired/awaiting `finalize()`, and
finalized winner or no-winner outcomes. Public reads, `Shot` events, transaction
links, deadlines, and provider block metadata drive the display. Shot answer
calldata is intentionally omitted from the site but remains inspectable on
Basescan. The frontend talks to a local RPC proxy so the Alchemy key never
reaches the browser.

Set in `.env`:

```text
ALCHEMY_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
CHAIN_ID=8453
```

The site reuses the existing `KINGOFTHEHILL_ADDRESS` as the contract address.
When it is unset or the zero address, the site shows its empty state and does not
poll the RPC proxy.

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
side_quest()
original_deadline()
deadline()
max_deadline()
extension_window()
max_overtime()
king()
king_since()
king_prize()
prize_for_hold_time(uint256)
max_shots()
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
