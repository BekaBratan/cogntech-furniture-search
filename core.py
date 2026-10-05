import re
import pandas as pd

category_names = {
    "sofa": "диван",
    "wardrobe": "шкаф",
    "dresser": "комод"
}


def text_value(row, column):
    value = row.get(column)

    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value.lower() in {"не указан", "не определен", "unknown"}:
        return ""

    return value

def make_search_text(row):
    parts = [
        text_value(row, "name"),
        category_names.get(row["category"], str(row["category"])),
        text_value(row, "color"),
        text_value(row, "material"),
        text_value(row, "description")
    ]

    return " ".join(" ".join(parts).split())

def parse_query(query):
    text = query.casefold()
    filters = {}

    category_patterns = {
        "sofa": r"\b(?:диван\w*|sofa)\b",
        "wardrobe": r"\b(?:шкаф\w*|wardrobe)\b",
        "dresser": r"\b(?:комод\w*|dresser)\b",
    }

    color_patterns = {
        "белый": r"\b(?:ақ|белый|белая|белое|белую|белого)\b",
        "зеленый": r"\b(?:жасыл|зел[её]ный|зел[её]ная|зел[её]ную)\b",
    }

    for category, pattern in category_patterns.items():
        if re.search(pattern, text):
            filters["category"] = category
            break

    for color, pattern in color_patterns.items():
        if re.search(pattern, text):
            filters["color"] = color
            break

    return filters

def parse_limits(query):
    text = query.casefold().replace("\u00a0", " ")
    limits = {}

    # Қолдайтын мысалдар:
    # "бюджет 50000", "бюджет 50 000 теңге", "бюджет 50 мың"
    budget_match = re.search(
        r"\bбюджет(?:і)?\s*[:=]?\s*"
        r"(\d+(?:[.,]\d+)?(?:[ ]\d{3})*)"
        r"\s*(мың|тыс\.?)?",
        text
    )

    if budget_match:
        value = float(
            budget_match.group(1).replace(" ", "").replace(",", ".")
        )
        if budget_match.group(2):
            value *= 1000

        limits["max_price_kzt"] = value

    # Қолдайтын мысалдар:
    # "ені 100 см-ден аспайтын", "ені 100 см дейін"
    width_match = re.search(
        r"\bені\s*[:=]?\s*(\d+(?:[.,]\d+)?)"
        r"\s*см(?:\s*-\s*(?:ден|дан|тен|тан))?"
        r"\s*(?:аспайтын|дейін)\b",
        text
    )

    if width_match:
        limits["max_width_cm"] = float(
            width_match.group(1).replace(",", ".")
        )

    return limits

def evaluate_rules(row, filters, hidden):
    checks = {}

    if "category" in filters:
        checks["R1: категория сәйкес"] = (
            str(row["category"]).strip().casefold()
            == filters["category"]
        )

    if "color" in filters:
        colors = {
            part.strip().casefold()
            for part in str(row["color"]).split(";")
        }
        checks["R2: түс сәйкес"] = filters["color"] in colors

    if "max_price_kzt" in filters:
        price = pd.to_numeric(row["price_kzt"], errors="coerce")
        checks["R3: бюджеттен аспайды"] = (
            pd.notna(price) and price <= filters["max_price_kzt"]
        )

    if "max_width_cm" in filters:
        width = pd.to_numeric(row["width_cm"], errors="coerce")
        checks["R4: ен шектеуіне сәйкес"] = (
            pd.notna(width) and width <= filters["max_width_cm"]
        )

    available = str(row.get("available", "")).strip().casefold()
    checks["R5: қолжетімді"] = available in {
        "true", "1", "1.0", "да", "yes"
    }

    checks["R6: пайдаланушы жасырмаған"] = (
        row["product_id"] not in hidden
    )

    return checks


def search(catalog, vectors, model, query, hidden, top_k=5):
    query = " ".join(query.split())
    if not query:
        raise ValueError("Сұрау бос болмауы керек.")

    filters = {**parse_query(query), **parse_limits(query)}

    query_vector = model.encode(
        ["query: " + query],
        normalize_embeddings=True,
        convert_to_numpy=True
    )[0]

    ranked = catalog.copy()
    ranked["similarity"] = vectors @ query_vector
    ranked = ranked.sort_values("similarity", ascending=False)

    decisions = []

    for _, row in ranked.iterrows():
        checks = evaluate_rules(row, filters, hidden)
        failed = [rule for rule, passed in checks.items() if not passed]

        decisions.append({
            "accepted": not failed,
            "explanation": "; ".join(checks) if not failed else "",
            "rejected_by": "; ".join(failed)
        })

    audit = pd.concat([
        ranked.reset_index(drop=True),
        pd.DataFrame(decisions)
    ], axis=1)

    results = audit[audit["accepted"]].head(top_k).copy()
    return results, audit, filters
