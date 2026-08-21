# Telegram Project Intake

Send a short text to your private Telegram bot and this repository's scheduled
workflow creates a draft item in GitHub Project `pavelmetalarm/8`.

## Delivery guarantee

The poller uses at-least-once delivery with a committed Telegram update cursor
and a recent-ID deduplication list. It does not advance the cursor until after a
draft item exists, so a failed run retries the update rather than silently
skipping it. The confirmation reply is sent after the cursor is persisted, so a
Telegram outage can cost you a missing checkmark but never a missing item. The
cursor is committed even when the run fails, so progress already made is not
replayed. The daily watchdog alerts
the owner when the oldest pending update exceeds six hours; in normal operation
this catches any condition that could approach 24 hours without a successful
run. Message text is sent only to Telegram and GitHub's APIs, never to the
repository or workflow logs.

## Configure Actions

In **Settings → Secrets and variables → Actions**, add these three repository
secrets:

- `TELEGRAM_INTAKE_BOT_TOKEN`
- `OWNER_TELEGRAM_ID`
- `PROJECT_TOKEN`

The workflow also uses GitHub's built-in `GITHUB_TOKEN` solely to commit the
numeric cursor. `PROJECT_OWNER` defaults to `pavelmetalarm` and `PROJECT_NUMBER`
defaults to `8`; set them as environment variables only if changing the target.

The bot accepts text only. Prefix text with `/bug`, `/idea`, or `/note` to set
the Type field; plain text is a note. Bot-addressed commands such as
`/bug@my_bot` work too.

## Run manually

Provide the three required environment variables and run:

```sh
python intake/poll.py
```

Use the **Run workflow** button in the Actions tab for the same operation in
GitHub.
