
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st
from sentence_transformers import SentenceTransformer

from ui import apply_theme, hero, missing_image
from core import make_search_text, search
from catalog_io import load_catalog_file, find_product_image, memory_path, source_link_label

BASE = Path(__file__).resolve().parents[1]
DB_PATH = memory_path(BASE)

st.set_page_config(page_title="Smart Furniture · Іздеу", layout="wide")
apply_theme()
hero("Үйіңізге үйлесетін жиһаз.", "Қалауыңызды жазыңыз. Каталогтан түсіне, стиліне және бюджетіңізге сай жиһаз табамыз.")


def get_hidden():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_products (
                product_id TEXT PRIMARY KEY
            )
        """)
        rows = conn.execute(
            "SELECT product_id FROM hidden_products"
        ).fetchall()

    return {row[0] for row in rows}


def change_hidden(product_id, hide=True):
    with sqlite3.connect(str(DB_PATH)) as conn:
        if hide:
            conn.execute(
                "INSERT OR IGNORE INTO hidden_products VALUES (?)",
                (product_id,)
            )
        else:
            conn.execute(
                "DELETE FROM hidden_products WHERE product_id = ?",
                (product_id,)
            )


@st.cache_data
def load_catalog(file_stamp):
    df = load_catalog_file(BASE)

    df["price_kzt"] = pd.to_numeric(df["price_kzt"], errors="coerce")

    if df["price_kzt"].isna().any() or (df["price_kzt"] <= 0).any():
        raise ValueError("Каталогта бос немесе қате бағалар бар.")

    df["search_text"] = df.apply(make_search_text, axis=1)
    return df


@st.cache_resource
def load_model():
    return SentenceTransformer(
        "intfloat/multilingual-e5-small", device="cpu"
    )


@st.cache_data
def build_vectors(texts):
    return load_model().encode(
        ["passage: " + text for text in texts],
        normalize_embeddings=True,
        convert_to_numpy=True
    )


catalog = load_catalog((BASE / "catalog.xlsx").stat().st_mtime_ns)

with st.spinner("Іздеу моделін дайындап жатырмыз..."):
    model = load_model()
    vectors = build_vectors(tuple(catalog["search_text"]))

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

hidden = get_hidden()


st.caption(f"Каталогта {len(catalog)} тауар · {catalog.category.nunique()} категория. Бағалар каталогтан алынады.")
with st.expander("Каталог туралы"):
    st.write("Каталогта болжамды сипаттамалар бар. Карточкадағы ескертпелерді тексеріңіз. Суреттер кейін қосылады.")

with st.sidebar:
    st.header("Демо пайдаланушы")
    st.caption("Бұл прототипте бір ортақ демо профиль бар.")

    st.subheader("Жасырылған тауарлар")
    for product_id in sorted(hidden):
        name = catalog.loc[
            catalog["product_id"] == product_id, "name"
        ]
        label = name.iloc[0] if not name.empty else product_id

        if st.button(f"Қайтару: {label}", key=f"restore_{product_id}"):
            change_hidden(product_id, hide=False)
            st.rerun()

    if not hidden:
        st.write("Жасырылған тауар жоқ.")

with st.form("search_form"):
    query = st.text_input(
        "Қандай жиһаз іздеп жүрсің?",
        value=st.session_state.last_query,
        placeholder="Ақ шкаф керек, бюджет 50 мың, ені 100 см-ден аспайтын"
    )
    submitted = st.form_submit_button("Іздеу")

if submitted:
    if query.strip():
        st.session_state.last_query = query.strip()
    else:
        st.warning("Сұрауды жаз.")

if st.session_state.last_query:
    active_query = st.session_state.last_query
    results, audit, filters = search(
        catalog, vectors, model, active_query, hidden
    )

    st.caption(f"Соңғы сұрау: {active_query}")
    if "max_price_kzt" in filters:
        st.caption(f"Қолданылған баға шегі: {filters['max_price_kzt']:,.0f} ₸")

    if results.empty:
        st.info("Осы шарттарға сәйкес тауар табылмады.")
    else:
        st.write(f"Көрсетілген тауар саны: {len(results)}")

        for _, row in results.iterrows():
            product_id = row["product_id"]

            with st.container(border=True):
                image_col, info_col = st.columns([1, 2])

                with image_col:
                    image = find_product_image(BASE, row)
                    if image:
                        st.image(str(image), width=280)
                    else:
                        missing_image()

                with info_col:
                    st.subheader(row["name"])
                    st.write(f"**{row['price_kzt']:,.0f} ₸**")
                    st.write(
                        f"Түс: {row['color']} · Ені: {row['width_cm']} см"
                    )
                    if row["product_url"]:
                        st.link_button(source_link_label(row["product_url"]), row["product_url"])
                    if row.get("data_notes"):
                        st.caption(row["data_notes"])

                    if st.button("Жасыру", key=f"hide_{product_id}"):
                        change_hidden(product_id)
                        st.rerun()

                    with st.expander("Неге таңдалды?"):
                        st.write(row["explanation"])
                        st.write(
                            f"Мағыналық ұқсастық: {row['similarity']:.4f}"
                        )

    with st.expander("Демонстрация: жүйенің шешімі"):
        st.write("Сұраудан алынған шарттар:", filters)
        st.write("Ұзақ жадтан оқылған:", sorted(hidden))
        st.write("Қысқа жад:", st.session_state.last_query)

        st.dataframe(
            audit[
                ["product_id", "name", "similarity",
                 "accepted", "rejected_by"]
            ],
            hide_index=True
        )

