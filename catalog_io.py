"""Shared catalog normalization, image lookup and catalog-scoped memory."""
import hashlib
import json
from pathlib import Path
import pandas as pd

def catalog_key(base):
    return hashlib.sha256((Path(base)/"catalog.xlsx").read_bytes()).hexdigest()[:12]

def memory_path(base, kind="memory"):
    return Path(base)/f"{kind}_{catalog_key(base)}.sqlite"

def load_catalog_file(base):
    df = pd.read_excel(Path(base)/"catalog.xlsx",dtype={"product_id":str,"model":str})
    required = {"product_id","name","category","price_kzt","width_cm","depth_cm","available","color"}
    missing = required-set(df.columns)
    if missing:
        raise ValueError("Бағандар жетіспейді: "+", ".join(sorted(missing)))
    for col in ("product_id","category"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["category"] = df["category"].str.casefold()
    if df.product_id.eq("").any() or not df.product_id.is_unique:
        raise ValueError("product_id бос немесе қайталанған.")
    for col in ("price_kzt","width_cm","depth_cm","height_cm"):
        if col in df:
            values = df[col].astype(str).str.replace("\u00a0","",regex=False).str.replace(" ","",regex=False).str.replace(",",".",regex=False)
            df[col] = pd.to_numeric(values,errors="coerce")
    for col in ("style","description","material","product_url","image_file","data_notes"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")
    return df

def find_product_image(base, row):
    base = Path(base).resolve()
    folder = base/"images"
    candidates = []
    supplied = str(row.get("image_file","")).strip().replace("\\","/")
    if supplied and supplied.casefold() != "nan":
        path = (base/supplied if supplied.startswith("images/") else folder/supplied).resolve()
        if path.is_relative_to(folder.resolve()):
            candidates.append(path)
    if folder.exists():
        candidates.extend(p for p in folder.iterdir() if p.stem.casefold()==str(row["product_id"]).casefold())
    manifest = base/"legacy_image_hashes.json"
    legacy = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    for path in candidates:
        if not path.is_file() or path.suffix.casefold() not in {".jpg",".jpeg",".png",".webp"}:
            continue
        content = path.read_bytes()
        blob = hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()
        if blob == legacy.get(path.relative_to(base).as_posix()):
            continue
        return path
    return None

def source_link_label(url):
    return "Kaspi-де тауарды ашу" if "/shop/p/" in str(url) else "Kaspi категориясын ашу"
