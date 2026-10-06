"""Streamlit multipage room planner; run from the existing app.py."""
import io
import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from catalog_io import load_catalog_file, find_product_image, memory_path, source_link_label, catalog_key
from ui import apply_theme, hero, missing_image
from core import make_search_text
from room_engine import (ROOMS, parse_room_request, candidate_sets, algorithm_layout,
                         qwen_layout, cloud_layout, validate_layout, draw_layout,
                         PLACEHOLDERS, placeholder_item, catalog_cost, CloudServiceError, LayoutValidationError, expand_item)

st.set_page_config(page_title="Бөлме дизайны",layout="wide")
apply_theme()
hero("Кеңістігіңізді жоспарлаңыз.", "Бөлме өлшемін және қалауыңызды көрсетіңіз. Жиһазды таңдап, 2D схемада орналастырамыз.")

@st.cache_data
def catalog_data(stamp):
    return load_catalog_file(BASE)

@st.cache_resource
def e5():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("intfloat/multilingual-e5-small",device="cpu")

@st.cache_data
def embeddings(texts):
    return e5().encode(["passage: "+t for t in texts],normalize_embeddings=True,convert_to_numpy=True)

catalog = catalog_data((BASE/"catalog.xlsx").stat().st_mtime_ns)
st.caption(f"Каталогта {len(catalog)} тауар · {catalog.category.nunique()} категория. Төсек өлшемі — толық сыртқы өлшем.")
with st.expander("Каталог және схема туралы"):
    st.write("Кей өлшемдер, стиль және қолжетімділік каталогта болжамды. Бұл — алдын ала схема; сатып аларда нақты сипаттамаларды тексеріңіз. Теледидарды қабырғаға не тумбаға орналастыру әзірге қолдау таппайды.")
query = st.text_input("Сұрау", value="Мне нужен дизайн спальни 4 на 4 метра, белая мебель, бюджет примерно 500К")
if st.button("Сұраудан параметрлерді алу"):
    parsed = parse_room_request(query)
    st.session_state["use_budget"] = "budget_kzt" in parsed
    for source,key in [("room_type","room_kind"),("width_cm","room_w"),("depth_cm","room_d"),
                       ("budget_kzt","room_budget"),("color","room_color"),("style","room_style")]:
        if source in parsed:
            if source in {"width_cm", "depth_cm"} and not 100 <= parsed[source] <= 2000:
                st.warning("Бөлме өлшемі 100–2000 см аралығында болуы керек; қолмен түзетіңіз.")
            elif source == "budget_kzt" and parsed[source] < 1000:
                st.warning("Бюджет кемінде 1000 ₸ болуы керек; қолмен түзетіңіз.")
            else:
                st.session_state[key] = parsed[source]
    parsed_kind = parsed.get("room_type",st.session_state.get("room_kind","bedroom"))
    for category,count in parsed.get("quantities",{}).items():
        if category in set(ROOMS[parsed_kind][0]+ROOMS[parsed_kind][1]):
            if 1<=count<=6:
                st.session_state[f"quantity_{parsed_kind}_{category}"] = count
            else:
                st.warning("Бір категориядан 1–6 дана таңдауға болады; санды қолмен түзетіңіз.")
    st.info("Төмендегі параметрлерді тексеріңіз. Есік пен терезені бөлек белгілеңіз.")

a,b,c = st.columns(3)
kind = a.selectbox("Бөлме түрі",list(ROOMS),key="room_kind",format_func=lambda value: {"bedroom":"Жатын бөлме","living_room":"Қонақ бөлме","office":"Жұмыс бөлмесі","kitchen":"Асүй","dining_room":"Асхана"}[value])
width = b.number_input("Бөлме ені, см",min_value=100.,max_value=2000.,value=None if "room_w" in st.session_state else 400.,step=10.,key="room_w")
depth = c.number_input("Бөлме ұзындығы, см",min_value=100.,max_value=2000.,value=None if "room_d" in st.session_state else 400.,step=10.,key="room_d")
use_budget = st.checkbox("Бюджет шектеуін қолдану",value=False,key="use_budget")
a,b,c = st.columns(3)
budget_value = a.number_input("Барлық жиһазға бюджет, ₸",min_value=1000.,value=None if "room_budget" in st.session_state else 500000.,step=10000.,key="room_budget",disabled=not use_budget)
budget = budget_value if use_budget else None
color = b.selectbox("Жиһаз түсі",["", "белый","зеленый","серый","бежевый","черный"],key="room_color")
style = c.selectbox("Интерьер стилі",["", "minimalist","scandinavian","loft","classic","modern"],key="room_style")
clearance = st.number_input("Жиһаз алдында бос орын, см",min_value=0.,max_value=150.,value=60.,step=10.)
st.caption("Бос орын — прототиптің бапталатын ережесі. Ол құрылыс нормасы емес; тұтас жүру жолы мен төсектің екі бүйірі бөлек тексерілмейді.")
with st.expander("Есік / терезе алдындағы бос аймақтар"):
    st.write("Төменгі сол бұрыш — (0, 0). Есік ашылатын және бос қалатын аймақтарды тіктөртбұрышпен белгілеңіз.")
    zones = st.data_editor(pd.DataFrame(columns=["x_cm","y_cm","width_cm","depth_cm"]),num_rows="dynamic",key="blocked_zones")
blocked = []
try:
    for _,z in zones.dropna(how="all").iterrows():
        vals = [float(z[k]) for k in ("x_cm","y_cm","width_cm","depth_cm")]
        x,y,w,d = vals
        if not all(pd.notna(v) and abs(v)<1e6 for v in vals) or min(x,y)<0 or min(w,d)<=0 or x+w>width or y+d>depth:
            raise ValueError("Бос аймақ координаталарын тексеріңіз.")
        blocked.append(tuple(vals))
except (ValueError,TypeError):
    st.error("Есік/терезе аймағы қате: барлық төрт мәнді толтырыңыз, аймақ бөлме ішінде болсын.")
    st.stop()
if not blocked:
    st.warning("Алдын ала схема: есік пен терезе орны көрсетілмеген.")

policy_label = st.radio("Қажетті категория табылмаса",["Үлгілік жиһазбен толықтыру","Толық жиынтықты талап ету"])
missing_policy = {"Үлгілік жиһазбен толықтыру":"placeholder","Толық жиынтықты талап ету":"strict"}[policy_label]
if missing_policy == "placeholder":
    st.caption("Каталогтан сәйкес жиһаз табылмаса, стандартты өлшемдегі үлгі автоматты қойылады. Оның бағасы белгісіз.")

quantity_names = {"bed":"Төсек","wardrobe":"Шкаф","sofa":"Диван","desk":"Жұмыс үстелі","chair":"Орындық",
                  "dresser":"Комод","nightstand":"Тумба","coffee_table":"Журнальдық үстел",
                  "tv_stand":"ТВ тумбасы","armchair":"Кресло","bookcase":"Кітап шкафы",
                  "kitchen_cabinets":"Асүй жиһазы","dining_table":"Асхана үстелі"}
quantities = {}
with st.expander("Жиһаз категориялары және саны",expanded=True):
    st.caption("Қосымша жиһаз үшін 0 — қоспау. Саны көрсетілген категория толық беріледі; қажет болса үлгімен толықтырылады.")
    columns = st.columns(3)
    for index,category in enumerate(ROOMS[kind][0]+ROOMS[kind][1]):
        mandatory = category in ROOMS[kind][0]
        default = 1 if mandatory or category in set(catalog.category) else 0
        quantity_key = f"quantity_{kind}_{category}"
        quantities[category] = columns[index%3].number_input(quantity_names.get(category,category)+" · дана",
            min_value=1 if mandatory else 0,max_value=6,value=None if quantity_key in st.session_state else default,step=1,key=quantity_key)

mode = st.radio("Орналастыру әдісі",["AI · бұлт (Groq)","AI · Qwen (жергілікті Ollama)","Алгоритм · AI емес","Дайын AI JSON жүктеу"])
cloud_key, cloud_model = "", "openai/gpt-oss-20b"
if "Groq" in mode:
    import os
    cloud_key = os.getenv("GROQ_API_KEY", "")
    cloud_model = os.getenv("GROQ_MODEL", cloud_model)
    try:
        cloud_key = st.secrets.get("GROQ_API_KEY",cloud_key)
        cloud_model = st.secrets.get("GROQ_MODEL",cloud_model)
    except st.errors.StreamlitSecretNotFoundError:
        pass
    if not cloud_key:
        st.info("Streamlit → Settings → Secrets: GROQ_API_KEY қосыңыз. Кілтті GitHub-қа жазбаңыз.")
upload = st.file_uploader("Экспортталған жоспар JSON",type="json") if mode.startswith("Дайын") else None
fallback = st.checkbox("AI қате берсе, алгоритммен жоспар жасау",value=True) if mode.startswith("AI") else False
request = {"room_type":kind,"width_cm":width,"depth_cm":depth,"budget_kzt":budget,"color":color,"style":style,"quantities":quantities}
fingerprint = json.dumps([catalog_key(BASE),request,blocked,clearance,query,mode,missing_policy,fallback],sort_keys=True)

if st.button("Жиһаз таңдап, схема жасау",type="primary"):
    st.session_state.pop("room_plan",None)
    try:
        if mode.startswith("Дайын") and upload is None:
            raise ValueError("Алдымен жоспар JSON файлын жүктеңіз.")
        hidden = set()
        db = memory_path(BASE)
        if db.exists():
            with sqlite3.connect(str(db)) as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hidden_products'").fetchone()
                if exists:
                    hidden = {r[0] for r in conn.execute("SELECT product_id FROM hidden_products")}
        if upload is not None:
            plan = json.load(upload)
            ids = [str(p["product_id"]) for p in plan["placements"]]
            if len(ids)!=len(set(ids)):
                raise ValueError("JSON ішінде қайталанған ID бар.")
            # Rebuild each copy from the current catalog/template, not file prices.
            lookup = {}
            for item in catalog.to_dict("records"):
                for copy in expand_item(item,quantities.get(item["category"],1) or 1):
                    lookup[copy["product_id"]] = copy
            if missing_policy == "placeholder":
                for category in PLACEHOLDERS:
                    if quantities.get(category,0)>0:
                        for copy in expand_item(placeholder_item(category,request),quantities[category]):
                            lookup[copy["product_id"]] = copy
            if any(product_id not in lookup for product_id in ids):
                raise ValueError("JSON тауарлары қазіргі каталогқа немесе жиһаз санына сәйкес емес.")
            items = [lookup[product_id] for product_id in ids]
            from collections import Counter
            actual = Counter(i["category"] for i in items)
            expected = {category:count for category,count in quantities.items() if count>0}
            if dict(actual)!=expected:
                raise ValueError("JSON жиһаз саны қазіргі параметрлерге сәйкес емес.")
            if not items:
                raise ValueError("JSON жоспары бос.")
            if budget is not None and catalog_cost(items)>budget:
                raise ValueError("Жалпы баға бюджеттен асады.")
            # Every imported item must itself pass the selection rules.
            for item in items:
                if item.get("placeholder",False):
                    continue
                if not all(pd.notna(item.get(field)) and math.isfinite(float(item[field])) and item[field]>0
                           for field in ("price_kzt","width_cm","depth_cm")):
                    raise ValueError("JSON тауар бағасы немесе өлшемі каталогта дұрыс емес.")
                if item.get("base_product_id",item["product_id"]) in hidden or str(item["available"]).casefold() not in {"true","1","1.0","да","yes"}:
                    raise ValueError("Жасырылған немесе қолжетімсіз тауар.")
                from room_engine import tags, styles
                if color and color not in tags(item["color"]):
                    raise ValueError("JSON тауар түсі сәйкес емес.")
                if style and style not in styles(item.get("style", "")):
                    raise ValueError("JSON тауар стилі сәйкес емес.")
                if tags(item.get("room_types", "")) and kind not in tags(item["room_types"]):
                    raise ValueError("JSON тауар бөлме түріне сәйкес емес.")
            placements = plan["placements"]
            errors = validate_layout(items,placements,request,blocked,clearance)
            if errors:
                raise ValueError("; ".join(errors))
            source = "JSON импорт · AI шығу тегі қолданушы файлынан, геометрия тексерілді"
        else:
            with st.spinner("Каталогты бағалау және жоспар құру..."):
                candidate_sets(catalog,request,hidden,missing_policy=missing_policy)
                texts = tuple(make_search_text(r) for _,r in catalog.iterrows())
                scores = embeddings(texts) @ e5().encode(["query: "+query],normalize_embeddings=True,convert_to_numpy=True)[0]
                score_map = dict(zip(catalog.product_id,map(float,scores)))
                sets = candidate_sets(catalog,request,hidden,score_map,missing_policy=missing_policy)
                placements, items = None, None
                used_fallback = False
                fallback_reason = ""
                geometry_errors = []
                for attempt, selected in enumerate(sets):
                    if used_fallback or not mode.startswith("AI"):
                        placements = algorithm_layout(selected,request,blocked,clearance)
                    else:
                        try:
                            placements = (cloud_layout(selected,request,cloud_key,cloud_model,blocked,clearance)
                                          if "Groq" in mode else qwen_layout(selected,request,blocked,clearance))
                        except CloudServiceError as exc:
                            if not fallback:
                                raise
                            fallback_reason = str(exc)
                            used_fallback = True
                            placements = algorithm_layout(selected,request,blocked,clearance)
                        except LayoutValidationError as exc:
                            geometry_errors.append(str(exc))
                            if fallback:
                                fallback_reason = str(exc)
                                used_fallback = True
                                placements = algorithm_layout(selected,request,blocked,clearance)
                            elif attempt >= 2 or attempt == len(sets)-1:
                                raise
                            else:
                                continue
                    if placements is not None:
                        items = selected
                        break
                if placements is None:
                    raise ValueError("Іздеу шегінде жарамды жоспар табылмады. Бос орын талабын немесе бөлме өлшемдерін тексеріңіз.")
                source = (f"AI · Groq / {cloud_model} + Python тексерісі" if "Groq" in mode else
                          "AI · Qwen2.5-3B + Python тексерісі" if mode.startswith("AI") else "Алгоритм · AI емес")
                if used_fallback:
                    st.warning(fallback_reason)
                    source = "Алгоритм · AI емес (AI жоспары жасалмады)"
        st.session_state.room_plan = {"items":items,"placements":placements,"request":request,"blocked":blocked,
                                      "clearance":clearance,"source":source,"fingerprint":fingerprint}
        with sqlite3.connect(str(memory_path(BASE,"room_memory"))) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            conn.execute("INSERT INTO plans(payload) VALUES (?)",(json.dumps(st.session_state.room_plan,ensure_ascii=False,default=str),))
    except Exception as exc:
        st.error(str(exc))
        if isinstance(exc,LayoutValidationError):
            st.info("AI жауабы келді, бірақ жиһаздардың бос орындары сәйкес емес. «AI қате берсе, алгоритммен жоспар жасау» қосқышын қосыңыз немесе алгоритм әдісін таңдаңыз.")
        elif isinstance(exc,CloudServiceError):
            st.info("Groq сервисіне қолжетімділікті тексеріңіз. Алгоритм әдісі API қажет етпейді.")
        elif mode.startswith("AI") and "Groq" not in mode:
            st.info("Ноутбукта Ollama іске қосылып, ollama pull qwen2.5:3b орындалуы керек. Бұлттағы localhost ноутбугыңызға қосылмайды.")

with st.expander("Сақталған соңғы жоспарды жадтан оқу"):
    if st.button("SQLite-дан қалпына келтіру"):
        db = memory_path(BASE,"room_memory")
        if db.exists():
            with sqlite3.connect(str(db)) as conn:
                row = conn.execute("SELECT payload FROM plans ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                restored = json.loads(row[0])
                st.json(restored)
                st.caption("Бұл — бұрынғы жоспардың жазбасы. Қазіргі каталог пен параметрлерге қайта тексеру үшін JSON арқылы жүктеңіз.")
        else:
            st.info("Сақталған жоспар жоқ.")

plan = st.session_state.get("room_plan")
if plan and plan["fingerprint"] != fingerprint:
    st.info("Параметрлер өзгерді. Жоспарды қайта жасаңыз.")
elif plan:
    st.success(plan["source"])
    present_categories = {i["category"] for i in plan["items"]}
    omitted = set(ROOMS[kind][0])-present_categories
    if omitted:
        st.warning("Ішінара жоспар: каталогтан сәйкес жиһаз табылмады — "+", ".join(sorted(omitted)))
    fig = draw_layout(plan["items"],plan["placements"],request,blocked,clearance)
    if st.toggle("Схеманы толық енде көрсету",value=False):
        st.pyplot(fig,width="stretch")
        right = st.container()
    else:
        left,right = st.columns([4,2],gap="large")
        left.pyplot(fig,width="stretch")
    total = catalog_cost(plan["items"])
    placeholders = [i for i in plan["items"] if i.get("placeholder",False)]
    right.metric("Каталог жиһазының бағасы" if placeholders else "Жалпы баға",f"{total:,.0f} ₸")
    if budget is not None:
        right.write(f"Каталог жиһазынан кейінгі бюджет: {budget-total:,.0f} ₸")
    else:
        right.caption("Бюджет көрсетілмеген: баға шектеуі қолданылмады.")
    if placeholders:
        right.warning("Үлгілік жиһаз бағасы белгісіз. Толық жиынтықтың бюджетке сыятыны расталмаған.")
    for number,item in enumerate(plan["items"],1):
        with right.container(border=True):
            st.write(f"**{number}. {item['name']}** · {item['product_id']}")
            if item.get("base_product_id") != item["product_id"]:
                st.caption(f"Тауар: {item.get('base_product_id')} · дана №{item.get('instance_number')}")
            if item.get("placeholder",False):
                st.info(f"ҮЛГІЛІК ЖИҺАЗ · {item['width_cm']} × {item['depth_cm']} см · баға белгісіз")
                continue
            image = find_product_image(BASE,item)
            if image:
                st.image(str(image),width=140)
            else:
                missing_image()
            if item.get("data_notes"):
                st.caption(item["data_notes"])
            st.write(f"{float(item['price_kzt']):,.0f} ₸ · {item['width_cm']} × {item['depth_cm']} см")
            if item.get("product_url"):
                st.link_button(source_link_label(item["product_url"]),item["product_url"])
    buffer = io.BytesIO()
    fig.savefig(buffer,format="png",dpi=160)
    st.download_button("Схеманы PNG жүктеу",buffer.getvalue(),"room_plan.png","image/png")
    exported = {"request":request,"placements":plan["placements"],"source":plan["source"]}
    st.download_button("Жоспар JSON",json.dumps(exported,ensure_ascii=False,indent=2),"room_plan.json","application/json")
