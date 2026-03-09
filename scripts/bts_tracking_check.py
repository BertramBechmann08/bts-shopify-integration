import argparse
import json
import logging
from typing import List

from bts.client import BTSClient
from bts.store import JSONStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-path", type=str, default="data/order_map.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    client = BTSClient.from_env()
    store = JSONStore(args.store_path)

    doc = store._load()
    orders = doc.get("orders", {})

    if not orders:
        print("No stored orders found.")
        return

    order_numbers: List[str] = []
    for external_id, row in orders.items():
        bts_order_number = row.get("bts_order_number")
        if bts_order_number:
            order_numbers.append(str(bts_order_number))

    if not order_numbers:
        print("No BTS order numbers found.")
        return

    resp = client.get_trackings(order_numbers)
    print(json.dumps(resp, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()