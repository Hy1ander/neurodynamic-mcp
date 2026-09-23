# PyPI Trusted Publishing — next release

Current immutable1.0.0 was uploaded with a scoped API token. This proposal does not republish it, change clients, alter payment settings or publish a new version.

## One-time owner step (PyPI browser login required)

Open https://pypi.org/manage/project/neurodynamic-mcp/settings/publishing/ and add a GitHub Trusted Publisher:

- Owner: `Hy1ander`
- Repository: `neurodynamic-mcp`
- Workflow filename: `publish.yml`
- Environment: `pypi`

Official instructions: https://docs.pypi.org/trusted-publishers/adding-a-publisher/ . The upload API token cannot configure this web-account setting.

The GitHub `pypi` environment is prepared with owner review and main-branch restrictions. A separate build job has no publishing permission; the publish job never executes repository code. Actions are pinned to commit hashes. No wallet/API secrets are passed into these jobs. The workflow only runs manually from main, builds an existing stable tag contained in main, checks package/version agreement and refuses a version already on PyPI. Dependencies of the client still need normal supply-chain review; a valid attestation is not a code-safety guarantee.

## Release acceptance

1. Register the PyPI publisher and review/merge this workflow PR.
2. Review the next package changes and dependency advisories, increment the version, merge and tag that commit (e.g. `v1.0.1`). Do not create a release just to claim this setup works.
3. Manually run Publish reviewed release to PyPI from main with that tag. Inspect build/test artifacts, then approve the protected pypi environment.
4. Confirm the new PyPI file hashes and its PEP740 provenance identify this repository/workflow/ref. Test installation and an unfunded MCP handshake.
5. Only after successful OIDC publication, revoke the old long-lived upload token in PyPI and remove the corresponding local credential. No old token has been revoked by this proposal.

Attestations are produced by the publishing action when the trusted publisher is configured, not merely by adding an OIDC workflow.1.0.0 cannot acquire retroactive publishing provenance. Existing mirrored artifact checksums remain useful integrity checks, not an independent trust root.
