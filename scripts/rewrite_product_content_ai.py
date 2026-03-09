import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()


def load_review_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Review file must contain a JSON object")

    products = data.get("products")
    if not isinstance(products, list):
        raise ValueError("Review file must contain a 'products' list")

    return data


def should_process_row(row: Dict[str, Any], only_pending: bool) -> bool:
    if not isinstance(row, dict):
        return False

    generated = row.get("generated")
    if not isinstance(generated, dict):
        return False

    if only_pending:
        review = row.get("review", {})
        if not isinstance(review, dict):
            return False
        if review.get("status") != "pending":
            return False

    return True


def build_ai_input(row: Dict[str, Any]) -> Dict[str, Any]:
    generated = row["generated"]
    source_title = str(row.get("source_title") or "").strip()
    brand = str(row.get("brand") or "").strip()
    size = str(row.get("size") or "").strip()
    title_da = str(generated.get("title_da") or "").strip()
    description_da = str(generated.get("description_da") or "").strip()
    bullets_da = generated.get("bullets_da") or []

    return {
        "source_title": source_title,
        "brand": brand,
        "size": size,
        "title_da": title_da,
        "description_da": description_da,
        "bullets_da": bullets_da if isinstance(bullets_da, list) else [],
    }


def rewrite_with_ai(client: OpenAI, model: str, ai_input: Dict[str, Any]) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {
            "description_da": {"type": "string"},
        },
        "required": ["description_da"],
        "additionalProperties": False,
    }

    instructions = (
        "Omskriv kun description_da meget forsigtigt til mere naturligt dansk webshop-sprog. "
        "Bevar struktur, betydning og fakta så tæt på input som muligt. "
        "Lav kun små sproglige forbedringer. "
        "Du må ikke tilføje nye oplysninger eller nye produktdetaljer. "
        "Du må ikke ændre brand, produkttype eller størrelse. "
        "Størrelsen skal bevares eksplicit i beskrivelsen. "
        "Undgå store omskrivninger. "
        "Returnér kun gyldig JSON."
    )

    last_error: Optional[Exception] = None

    for attempt in range(6):
        try:
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=json.dumps(ai_input, ensure_ascii=False),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "product_rewrite",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )

            output_text = response.output_text
            result = json.loads(output_text)

            if not isinstance(result, dict):
                raise ValueError("AI output was not a JSON object")

            description_da = str(result.get("description_da") or "").strip()

            if not description_da:
                raise ValueError("AI output missing description_da")

            source_text = " ".join(
                [
                    str(ai_input.get("source_title") or ""),
                    str(ai_input.get("title_da") or ""),
                    str(ai_input.get("description_da") or ""),
                ]
            ).lower()

            banned_words = ["sprayflaske", "ingredienser", "duftnoter", "topnoter", "hjertenoter", "basenoter"]
            lowered_description = description_da.lower()

            for word in banned_words:
                if word in lowered_description and word not in source_text:
                    raise ValueError(f"AI output introduced forbidden word: {word}")

            return {
                "description_da": description_da,
            }

        except RateLimitError as e:
            last_error = e
            wait_seconds = max(22.0, 5.0 * (attempt + 1))
            print(f"RATE LIMIT: waiting {wait_seconds:.0f}s before retry")
            time.sleep(wait_seconds)

        except Exception as e:
            last_error = e
            break

    raise RuntimeError(f"AI rewrite failed after retries: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-file", default="data/content_review_existing.json")
    parser.add_argument("--out", default="data/content_review_existing_ai.json")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    parser.add_argument("--only-pending", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=22.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment")

    model = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()
    client = OpenAI(api_key=api_key)

    doc = load_review_file(args.review_file)
    products = doc["products"]

    processed = 0

    for row in products:
        if not should_process_row(row, only_pending=args.only_pending):
            continue

        ai_input = build_ai_input(row)

        print(f"Rewriting: {row.get('ean')} | {ai_input['title_da']}")

        try:
            ai_result = rewrite_with_ai(client, model, ai_input)
        except Exception as e:
            print(f"SKIP AI ERROR for EAN {row.get('ean')}: {e}")
            continue

        row["ai_rewrite"] = {
            "title_da": ai_input["title_da"],
            "description_da": ai_result["description_da"],
            "bullets_da": ai_input["bullets_da"],
        }

        processed += 1

        if args.limit > 0 and processed >= args.limit:
            break

        time.sleep(args.sleep_seconds)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"Wrote AI-rewritten content for {processed} products to {args.out}")


if __name__ == "__main__":
    main()