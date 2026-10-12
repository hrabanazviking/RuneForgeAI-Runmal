# Rúnmál Quickstart (S112)

Install and run Rúnmál on a fresh Linux machine in minutes. Rúnmál is a
plain Python app — no systemd, Docker, or root required.

## Prerequisites

- Python 3.12 or newer (`python3 --version`)
- `pip` and `venv` (`python3 -m pip --version`)
- git

## Install

```sh
git clone https://github.com/hrabanazviking/RuneForgeAI-Runmal.git
cd RuneForgeAI-Runmal
python3 -m venv .venv
.venv/bin/pip install -e .
```

(`pip install .` works too; `-e` keeps the checkout editable for hacking.)

## Run

```sh
.venv/bin/python -m runmal serve
```

The server binds **127.0.0.1:8098** — loopback only, by design
(see `docs/adr/0003-local-auth-boundary.md`). Override if you know why:

```sh
.venv/bin/python -m runmal serve --host 127.0.0.1 --port 9000
```

## First run: unlock the UI

1. Open <http://127.0.0.1:8098/chat>
2. The page asks for a token. Read it from the credential file:

   ```sh
   cat ~/.local/share/runmal/local_credential
   ```

   (or `$RUNMAL_DATA_DIR/local_credential` if you overrode the data dir)
3. Paste it in — the browser keeps it in localStorage. The token never
   leaves your machine.

## API

Bearer-authenticated at `http://127.0.0.1:8098/api/v1`:

```sh
TOKEN=$(cat ~/.local/share/runmal/local_credential)
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8098/api/v1/chats
```

Public, no auth: `GET /healthz`.

## Data

Everything lives in `~/.local/share/runmal` (`runmal.db` +
`local_credential`). Point elsewhere with `RUNMAL_DATA_DIR`:

```sh
RUNMAL_DATA_DIR=/srv/runmal/data .venv/bin/python -m runmal serve
```

## Run at login (optional)

A reference systemd **user** unit lives at `docs/systemd/runmal.service`.
It is documentation only — Rúnmál itself does not depend on systemd:

```sh
mkdir -p ~/.config/systemd/user
cp docs/systemd/runmal.service ~/.config/systemd/user/
# edit ExecStart if your checkout/venv lives elsewhere
systemctl --user daemon-reload
systemctl --user enable --now runmal
```

## Verify the install

```sh
.venv/bin/python -m pytest -q   # full suite, should be green
.venv/bin/ruff check src tests scripts
```

## Next steps

- `docs/ROADMAP.md` — where the project is going
- `docs/SECURITY_MODEL.md` — the local-trust model
- `docs/TESTING.md` — how acceptance evidence is produced
