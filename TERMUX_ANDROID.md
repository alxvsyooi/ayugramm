# Termux: upload + run Actions

This archive is meant to be copied over an existing repo or pushed to a new repo.

Required packages:
`pkg install -y git gh unzip`

The workflows require repository secrets:
- TG_API_ID
- TG_API_HASH

Recommended flow:
1. unzip
2. git init / set remote
3. git add -A
4. commit + push
5. run Verify Ayu Patch
6. if green, run Build Telegram Ayu IPA v0.2.5
