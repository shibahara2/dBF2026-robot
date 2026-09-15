import json

import requests


def iter_sse_events(base_url, timeout=None):
    resp = requests.get(f"{base_url}/api/events", stream=True, timeout=timeout)
    resp.raise_for_status()
    for raw_line in resp.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            # A truncated/malformed frame can happen when the connection is
            # dropping mid-stream. Skip this line and keep consuming the
            # rest of the stream rather than killing the whole generator.
            continue
