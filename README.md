# NeuroDynamic MCP client — 1.0.0

Connect an MCP-compatible agent to NeuroDynamic audio and LLM APIs.

**Free by default.** Discover services, compare seven voices and inspect prices without a wallet. Purchases are optional and explicitly enabled by the wallet owner.

- Storefront: https://x402.neurodynamic.tech/
- Service catalogue: https://api.neurodynamic.tech/.well-known/ai-services.json
- API schema: https://api.neurodynamic.tech/openapi.json
- Terms: https://neurodynamic.tech/terms
- Privacy: https://neurodynamic.tech/privacy
- Support: support@neurodynamic.tech

## What this release supports

| Tool | What it does | Charge |
|---|---|---|
| catalogue | Read services, voices, schema or private-cloning requirements | Free |
| quote | Check the live price and payment details | Free |
| purchase_json | Generate catalogue narration or either LLM's text | Explicit purchase |
| transcribe_file | Upload and transcribe your audio | Explicit purchase |
| payment_status | Inspect an existing purchase; query LLM payment recovery | Free |
| budget_status | See the cumulative client spending cap | Free |

Current purchases use native **USDC on Base**, x402 v2 exact, an EOA wallet. A future merchant network option will not silently change which network this client signs for. SOL-token payments, other chains, smart accounts and automatic bridging are not supported by this client release.

Private cloning is discoverable here; purchase/enrolment stays in the [approved-account workflow](https://api.neurodynamic.tech/cloning). This adapter does not enrol voices, bypass consent review or hold cloning bearer credentials. The [audio starter](https://neurodynamic.tech/integrations/audio-starter-v2-20260910.zip) includes the separate workflow.

This runs **locally on the requesting machine using stdio**. It is not a hosted `/mcp` URL, and it does not open a port. No NeuroDynamic account is needed for catalogue narration, transcription or LLM purchases.

## Install

Python 3.10+ on Linux or macOS. Windows users can use WSL. The budget lock uses POSIX file locking.

Install the published package in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/pip install neurodynamic-mcp==1.0.0
```

Alternatively, from a checkout of this repository, use `.venv/bin/pip install .`.
The included `requirements.lock` records the dependency versions tested for the
original release; the package pins its direct dependencies in `pyproject.toml`.

Add this entry to your MCP application and replace the Python path:

```json
{
  "mcpServers": {
    "neurodynamic": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "neurodynamic_mcp"]
    }
  }
}
```

Package: https://pypi.org/project/neurodynamic-mcp/1.0.0/

Official registry name: `tech.neurodynamic/audio-llm`.

Ask the agent: **“List NeuroDynamic services and voices, then get a narration quote. Do not purchase anything.”**

The adapter checks the live quote against reviewed merchant, native USDC token, network, amount and signing-domain values. Prices are introductory; if they change, the adapter stops for an update rather than accepting a higher price automatically.

## Optional purchases

Use a dedicated low-balance Base wallet. Keep its raw hexadecimal private key in a file owned by the user running the client, with mode `0600`; never paste it into an agent prompt or tool call. Wallet keys stay on your requesting machine.

Create a private state directory and, for transcription, a separate input directory. Both should be owned by that user. Audio input files must be mode `0600`. Only place files intended for upload in the input directory.

Add owner-controlled `env` settings to the server configuration:

```json
{
  "NEURODYNAMIC_BUYER_KEY_FILE": "/private/path/buyer.key",
  "NEURODYNAMIC_STATE": "/private/path/neurodynamic-purchases",
  "NEURODYNAMIC_INPUT_DIR": "/private/path/audio-to-upload",
  "NEURODYNAMIC_TOTAL_CAP_ATOMIC": "50000"
}
```

`50000` is **0.05 USDC total**, not per call or per day. The cap persists across restarts through the state ledger. This initial client limits its configured cap to at most 1 USDC. State files are the budget history: do not delete or replace them to resolve errors. A host with shell access can alter local files, so this is not a sandbox against a malicious local user or agent.

Each purchase also requires `confirm_purchase: true` in its tool arguments. The owner must authorise spending; a quote is not permission to spend.

Narration example:

```json
{
  "service": "narration",
  "body": {"input": "Hello from NeuroDynamic.", "voice": "bf_emma"},
  "purchase_id": "my-first-narration",
  "confirm_purchase": true
}
```

One MP3, up to 1,000 characters: **0.005 USDC**. Available voice IDs: Hazel `af_heart`, Bella `af_bella`, Emma `bf_emma`, Alice `bf_alice`, George `bm_george`, Michael `am_michael`, Ben `am_fenrir`.

Transcription: use `transcribe_file` with a filename inside your input directory, a new purchase ID, `language: "en"` and explicit confirmation. Up to 60 seconds/12 MiB, **0.01 USDC**. An unpaid `quote` never reads or uploads audio.

LLM examples use `service: "abliterated"` (**0.020 USDC**) or `"abliterated-large"` (**0.035 USDC**). The body needs `input`, optionally `max_tokens` (16–512), and explicit `adult: true`, `third_party_processing: true`, `terms_version: "2026-09-11-llm-v1"`. Only acknowledge these with the user's authority after reading https://api.neurodynamic.tech/llm. Input is limited to 2,000 UTF-8 bytes. Adults 18+, lawful use; generated content can be wrong.

## Recovery and privacy

The adapter reserves budget and saves the signed proof **before** sending a paid request. It saves returned output locally with mode `0600` and records the receipt. It does not log prompts or private keys.

- Repeating the same purchase ID returns its saved state; it does not sign or submit another payment.
- The same ID with different input is rejected.
- Failed or uncertain purchases keep their budget reservation. They are not automatically refunded or retried.
- Use `payment_status` after uncertainty. Contact support with the request ID or transaction hash if needed. Do not send private keys, signed proofs or your state database to support.
- LLM outputs are not retained by NeuroDynamic after processing. A lost LLM response cannot be recovered by paying again safely; payment status is available without another charge.
- Transcription/narration recovery follows each API guide. This initial adapter does not automatically resend an uncertain paid request; preserve the state and original input for support-assisted recovery.

Your local state directory contains signed payment proofs, purchase metadata and returned files. Protect it like wallet material. Requests contain your chosen text/audio. Merchant operational metadata and service-specific retention are explained in the API guides. LLM requests go to third-party providers with separate retention policies; local server content-retention statements do not cover those providers or your client files.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/stdio_smoke.py
```

Unit tests use synthetic HTTP responses and an unfunded temporary signing key. The stdio smoke test performs only free live discovery/quotes and confirms purchases are disabled.

Release validation also completed three separately authorised operator purchases (narration, transcription and LLM), total 0.035 USDC, followed by no-charge duplicate and status checks. These are test activity, not customer sales.

<!-- mcp-name: tech.neurodynamic/audio-llm -->
