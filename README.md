# TradingDesk Desktop Configuration Distribution

This repository hosts the configuration files offered by TradingDesk's optional desktop setup assistant. It does not replace the two source repositories, which continue to support manual downloads:

- [import-data-providers](https://github.com/tradingdesk-win/import-data-providers): trade confirmation templates.
- [market-data-providers](https://github.com/tradingdesk-win/market-data-providers): market-data and stock-directory configuration.

The catalog takes files from `providers/*/template.json` and `providers/*/config.yaml`. The exclusion list covers the local-only 选股宝 (`xuangubao`) configuration. Upstream maintainers review configurations for redistribution and credentials before adding them to `providers/`. The included market provider license comes from its source repository.

## Automatic Synchronization

The **Sync provider configurations** GitHub Actions workflow checks both public `main` branches on a 15-minute schedule, or on demand via **Run workflow**. GitHub may delay scheduled runs. It validates the release, keeps files byte-for-byte, and commits only if generated files or handoff state change. No cross-repository token is needed; only the distribution repository is written.

The first release uses the local source directories. `upstream-pending.json` tracks locally published files awaiting the same content upstream. The workflow preserves those files individually and syncs the rest on schedule. If a pending file changes locally again before its first upstream push, refresh the snapshot with the command below.

```sh
python -m pip install -r requirements.txt
python -B scripts/sync.py --import-repo ../import-data-providers --market-repo ../market-data-providers
python -B -m unittest discover -s scripts
```

## Desktop Policy

The workflow summary prints the verified **Primary HTTPS address** and **Manifest SHA-256**. The URL pins the full release commit and ends in `/v1`, not `/manifest.json`. Only configure fallback mirrors that serve identical bytes. Repository sync does not change the admin policy; promote each approved release with the new address and digest together. Enable distribution only after an isolated desktop acceptance test passes.
