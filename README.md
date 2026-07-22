# tweety-ns (patched)

Installable fork of [tweety-ns](https://github.com/mahrtayyab/tweety) with local patches:

- **rnet** HTTP transport (TLS / HTTP2 fingerprinting) instead of plain httpx
- Fixed **x-client-transaction-id** generation when X serves the new x-web client  
  (`Couldn't get animation key indices` — prefers `https://x.com/home` and robust `ondemand.s` hash lookup)

Import name stays **`tweety`**.

## Install (Google Colab / pip)

```python
# Colab cell
!pip install -U "git+https://github.com/rajeshbca2020/tweety-ns.git"
```

Or with pip locally:

```bash
pip install -U "git+https://github.com/rajeshbca2020/tweety-ns.git"
```

Private repo? Use a token:

```bash
pip install -U "git+https://<TOKEN>@github.com/rajeshbca2020/tweety-ns.git"
```

## Usage

```python
from tweety import Twitter, TwitterAsync

# sync
app = Twitter("session")
app.load_auth_token("YOUR_AUTH_TOKEN")

# async
# app = TwitterAsync("session")
# await app.load_auth_token("YOUR_AUTH_TOKEN")
```

## Version

- Base: tweety `2.4.1`
- Package: `2.4.1.post1` (patch release)

## License

MIT (same as upstream tweety where applicable).
