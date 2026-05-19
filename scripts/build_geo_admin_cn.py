"""Build local Chinese admin-division geocode table from pfinal/city region.sql."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path


URL = "https://raw.githubusercontent.com/pfinal/city/master/region.sql"
OUT = Path(__file__).resolve().parent.parent / "data" / "geo_admin_cn.json"


def main() -> None:
    text = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8", "ignore")
    rows = re.findall(r"\('([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'", text)
    items = {}
    for code, name, parent, lng, lat in rows:
        items[code] = {
            "name": name,
            "parent": parent,
            "lng": round(float(lng), 8),
            "lat": round(float(lat), 8),
        }
    payload = {
        "_meta": {
            "source": "pfinal/city region.sql",
            "url": URL,
            "rows": len(items),
            "note": "Chinese administrative division center points used for birth-place geocoding.",
        },
        "items": items,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(items)} rows to {OUT}")


if __name__ == "__main__":
    main()
