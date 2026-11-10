"""Replay a PayPal webhook fixture against a local API (demo only).

Real PayPal sandbox disputes are opened by a sandbox buyer in the browser, which is slow to do on
camera. This posts a fixture instead. The API only accepts it when DEMO_TOOLS=1 and
PAYPAL_VERIFY_WEBHOOKS=0, so it can never be used against a real deployment by accident.
"""

import sys
import urllib.request

path = sys.argv[1]
url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000/core/webhooks/paypal"
req = urllib.request.Request(
    url, data=open(path, "rb").read(), headers={"Content-Type": "application/json"}
)
print(urllib.request.urlopen(req).read().decode())
