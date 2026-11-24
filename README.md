# TradingDesk Desktop Configuration Distribution

This repository hosts the configuration files offered by TradingDesk's optional desktop setup assistant. It does not replace the two source repositories, which continue to support manual downloads:

- [import-data-providers](https://github.com/tradingdesk-win/import-data-providers): trade confirmation templates.
- [market-data-providers](https://github.com/tradingdesk-win/market-data-providers): market-data and stock-directory configuration.

The initial `v1/manifest.json` is empty. No provider configuration is available from this repository yet.

## Publish a Batch

1. Record the source commit and path for each approved file in the release commit description. Copy only approved JSON templates and YAML configurations into `v1/`, alongside `manifest.json`, without rewriting their contents. Do not include credentials, real statements, market-data snapshots, or stock-directory snapshots.
2. Update `release` and add one manifest item per file. Each item has `id`, `name`, `version`, `markets`, `capabilities`, `file`, and `sha256`; templates also have `broker`. Use the configuration's actual ID, version, and markets. Use `template`, `market_data`, or `stock_directory` for capabilities. A YAML file with both market-data and stock-directory capabilities gets one entry. `file` is a plain filename, not a path or URL.
3. Calculate each file's SHA-256 with `shasum -a 256 v1/<filename>` and insert it into the corresponding entry. Commit the files and manifest, then push. Use the full release commit SHA in the raw base URL: `https://raw.githubusercontent.com/tradingdesk-win/desktop-config-distribution/<commit-sha>/v1`.
4. Verify that anonymous HTTPS requests to `<base>/manifest.json` and each `<base>/<filename>` return `200` without redirects. Compare the downloaded file digests with the manifest. Use the digest of the downloaded `manifest.json` as the admin console's **Manifest SHA-256**, and the base URL as **Primary HTTPS address**. Only configure fallbacks hosting identical bytes. Enable distribution only after an isolated desktop acceptance test passes.
