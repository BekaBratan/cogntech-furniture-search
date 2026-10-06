"""Catalog selection and validated, centimetre-based room layouts."""
import json
import math
import re
import urllib.request
from itertools import product

import pandas as pd

ROOMS = {
    "bedroom": (["bed", "wardrobe"], ["nightstand", "dresser"]),
    "living_room": (["sofa"], ["wardrobe", "dresser", "coffee_table", "tv_stand", "armchair", "bookcase", "dining_table"]),
    "office": (["desk", "chair"], ["bookcase", "dresser"]),
    "kitchen": (["kitchen_cabinets"], ["dining_table", "chair"]),
    "dining_room": (["dining_table"], ["chair", "dresser"]),
}
STYLE_PATTERNS = {
    "minimalist": r"минимал\w*|minimal\w*",
    "scandinavian": r"скандинав\w*|scandinav\w*",
    "loft": r"лофт\w*|loft",
    "classic": r"классик\w*|классичес\w*|classic\w*",
    "modern": r"заманауи|современн\w*|modern",
}
COLORS = {
    "белый": r"\b(?:ақ|бел\w*|white)\b",
    "зеленый": r"\b(?:жасыл|зел[её]н\w*|green)\b",
    "серый": r"\b(?:сұр|сер\w*|grey|gray)\b",
    "бежевый": r"\b(?:беж\w*|beige)\b",
    "черный": r"\b(?:қара|ч[её]рн\w*|black)\b",
}

# Prototype defaults, not manufacturer specifications or dimensions of a sale item.
PLACEHOLDERS = {
    "bed": ("Үлгілік төсек",160,210,100),
    "wardrobe": ("Үлгілік шкаф",120,60,200),
    "sofa": ("Үлгілік диван",220,90,85),
    "desk": ("Үлгілік үстел",120,60,75),
    "chair": ("Үлгілік орындық",50,50,90),
    "nightstand": ("Үлгілік тумба",50,40,50),
    "dresser": ("Үлгілік комод",80,40,80),
    "bookcase": ("Үлгілік кітап шкафы",80,30,180),
    "coffee_table": ("Үлгілік журнальдық үстел",100,60,45),
    "tv_stand": ("Үлгілік ТВ тумбасы",140,40,50),
    "armchair": ("Үлгілік кресло",80,80,90),
    "kitchen_cabinets": ("Үлгілік асүй жиһазы",180,60,85),
    "dining_table": ("Үлгілік асхана үстелі",120,80,75),
}


def placeholder_item(category, request):
    name,w,d,h = PLACEHOLDERS[category]
    return {"product_id":"PLACEHOLDER_"+category.upper(),"name":name,"category":category,
            "width_cm":w,"depth_cm":d,"height_cm":h,"price_kzt":None,"placeholder":True,
            "color":request.get("color") or "анықталмаған","style":request.get("style") or "",
            "available":False,"product_url":None,"score":0.0,"room_types":request["room_type"]}


def expand_item(item, count=1):
    if isinstance(count,bool) or not isinstance(count,int) or not 1 <= count <= 6:
        raise ValueError("Жиһаз саны 1–6 аралығындағы бүтін сан болуы керек.")
    base = str(item["product_id"])
    copies = []
    for number in range(1,count+1):
        copy = dict(item)
        copy["base_product_id"] = base
        copy["product_id"] = base if count==1 else f"{base}__{number}"
        copy["instance_number"] = number
        copies.append(copy)
    return copies


def catalog_cost(items):
    return sum(float(item["price_kzt"]) for item in items if not item.get("placeholder",False))


def parse_room_request(text):
    s = text.casefold().replace("\u00a0", " ")
    out = {}
    for kind, pattern in [("bedroom", r"спаль\w*|спальн\w*|жатын|bedroom"),
                          ("living_room", r"гостин\w*|қонақ|living"),
                          ("office", r"кабинет\w*|офис\w*|office"),
                          ("kitchen", r"кухн\w*|асүй|ас\s+үй|kitchen"),
                          ("dining_room", r"столов\w*|асхана|dining")]:
        if re.search(pattern, s):
            out["room_type"] = kind
            break
    dims = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:на|на\s+|[xх×*])\s*(\d+(?:[.,]\d+)?)\s*(?:метр\w*|м\b)", s)
    if dims:
        out["width_cm"], out["depth_cm"] = [float(v.replace(",", "."))*100 for v in dims.groups()]
    budget = re.search(r"бюджет\w*\s*(?:примерно|шамамен|около|до)?\s*[:=]?\s*(\d+(?:[ ]\d{3})*(?:[.,]\d+)?)\s*(тыс\.?|мың|[kк])?", s)
    if budget:
        out["budget_kzt"] = float(budget[1].replace(" ", "").replace(",", ".")) * (1000 if budget[2] else 1)
    for name, pattern in STYLE_PATTERNS.items():
        if re.search(pattern, s):
            out["style"] = name
            break
    for name, pattern in COLORS.items():
        if re.search(pattern, s):
            out["color"] = name
            break
    quantity_patterns = {
        "chair": r"(?:стул\w*|орындық\w*|chair\w*)",
        "desk": r"(?:письменн\w*\s+стол\w*|жұмыс\s+үстел\w*|desk\w*)",
        "dining_table": r"(?:обеденн\w*\s+стол\w*|асхана\s+үстел\w*)",
        "wardrobe": r"(?:шкаф\w*|wardrobe\w*)",
        "bed": r"(?:кроват\w*|төсек\w*|bed\w*)",
        "sofa": r"(?:диван\w*|sofa\w*)",
        "dresser": r"(?:комод\w*|dresser\w*)",
        "nightstand": r"(?:прикроватн\w*\s+тумб\w*|nightstand\w*)",
        "armchair": r"(?:кресл\w*|armchair\w*)",
    }
    quantities = {}
    for category,pattern in quantity_patterns.items():
        match = re.search(r"\b(\d+)\s*(?:дана\s*)?"+pattern,s)
        if match:
            quantities[category] = int(match[1])
    if quantities:
        out["quantities"] = quantities
    return out


def tags(value):
    if pd.isna(value):
        return set()
    return {s.strip().casefold() for s in re.split(r"[;,]", str(value)) if s.strip()}


def styles(value):
    values = tags(value)
    normalized = set()
    for value in values:
        for name, pattern in STYLE_PATTERNS.items():
            if value == name or re.fullmatch(pattern, value):
                normalized.add(name)
    return normalized


def candidate_sets(catalog, request, hidden=(), scores=None, limit=12, missing_policy="placeholder"):
    """Bounded beam search; not a proof of global optimality."""
    if request["room_type"] not in ROOMS:
        raise ValueError("Бөлме түрі қолдау таппайды.")
    if missing_policy not in {"strict","available","placeholder"}:
        raise ValueError("Белгісіз жетіспейтін категория саясаты.")
    for key in ("width_cm", "depth_cm"):
        if not math.isfinite(float(request[key])) or request[key] <= 0:
            raise ValueError(f"Қате параметр: {key}")
    budget = request.get("budget_kzt")
    if budget is not None and (not math.isfinite(float(budget)) or budget <= 0):
        raise ValueError("Қате параметр: budget_kzt")
    df = catalog.copy()
    if not df["product_id"].is_unique:
        raise ValueError("Каталогта қайталанған product_id бар.")
    for col in ["width_cm", "depth_cm", "price_kzt"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[df[col].notna() & (df[col] > 0) & df[col].map(math.isfinite)]
    df = df[~df["product_id"].isin(hidden)]
    df = df[df["available"].astype(str).str.casefold().isin(["true", "1", "1.0", "да", "yes"])]
    df["category"] = df["category"].astype(str).str.strip().str.casefold()
    if request.get("color"):
        df = df.loc[df["color"].apply(lambda v: request["color"] in tags(v)).astype(bool)]
    if request.get("style"):
        if "style" not in df:
            df["style"] = ""
        df = df.loc[df["style"].apply(lambda v: request["style"] in styles(v)).astype(bool)]
    if "room_types" in df:
        df = df.loc[df["room_types"].apply(lambda v: not tags(v) or request["room_type"] in tags(v)).astype(bool)]
    w, d = request["width_cm"], request["depth_cm"]
    df = df[((df.width_cm <= w) & (df.depth_cm <= d)) | ((df.depth_cm <= w) & (df.width_cm <= d))]
    df["score"] = df["product_id"].map(scores or {}).fillna(0.0)
    required, optional = [list(cats) for cats in ROOMS[request["room_type"]]]
    quantities = request.get("quantities",{})
    allowed = set(required+optional)
    if set(quantities)-allowed:
        raise ValueError("Бұл бөлме түріне сәйкес емес жиһаз категориясы.")
    if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=6 for v in quantities.values()):
        raise ValueError("Жиһаз саны 0–6 аралығындағы бүтін сан болуы керек.")
    if any(quantities.get(cat,1)<1 for cat in required):
        raise ValueError("Міндетті жиһаз саны кемінде 1 болуы керек.")
    if quantities:
        required = required + [cat for cat in optional if quantities.get(cat,0)>0]
        optional = []
    if sum(quantities.get(cat,1) for cat in required+optional)>20:
        raise ValueError("Бір жоспарға ең көбі 20 жиһаз данасы.")
    groups = {cat: df[df.category == cat].sort_values(["score", "price_kzt"], ascending=[False, True]).head(8).to_dict("records") for cat in required + optional}
    missing = [cat for cat in required if not groups[cat]]
    if missing and missing_policy == "strict":
        raise ValueError("Сәйкес міндетті жиһаз жоқ: " + ", ".join(missing))
    if missing_policy == "placeholder":
        for cat in missing:
            item = placeholder_item(cat,request)
            if not ((item["width_cm"]<=w and item["depth_cm"]<=d) or (item["depth_cm"]<=w and item["width_cm"]<=d)):
                raise ValueError("Үлгілік жиһаз бөлмеге сыймайды: "+cat)
            groups[cat] = [item]
    if not any(groups.values()):
        raise ValueError("Каталогтан сәйкес жиһаз табылмады.")
    states = [([], 0.0, 0.0)]
    for cat in required + optional:
        options = groups[cat] + ([None] if cat in optional or (cat in missing and missing_policy == "available") else [])
        expanded = []
        for items, cost, score in states:
            for item in options:
                bundle = expand_item(item,quantities.get(cat,1)) if item else []
                newcost = cost + catalog_cost(bundle)
                if budget is None or newcost <= budget:
                    expanded.append((items + bundle, newcost,
                                     score + (1 + item["score"] if item else 0)))
        ranked_states = sorted(expanded, key=lambda s: (-s[2], s[1]))
        counts_at_step = sorted({len(state[0]) for state in ranked_states},reverse=True)
        states = ranked_states[:max(1,120-len(counts_at_step)+1)]
        for count in counts_at_step:
            state = next(state for state in ranked_states if len(state[0])==count)
            signature = tuple(str(i["product_id"]) for i in state[0])
            if not any(tuple(str(i["product_id"]) for i in s[0])==signature for s in states) and len(states)<120:
                states.append(state)
    states = [state for state in states if state[0]]
    if not states:
        raise ValueError("Міндетті жиһаз жиынтығына бюджет жеткіліксіз.")
    # Reserve smaller valid sets so optional furniture cannot prevent any plan.
    counts = sorted({len(state[0]) for state in states},reverse=True)
    selected_states = states[:max(1,limit-len(counts)+1)]
    signatures = {tuple(str(i["product_id"]) for i in state[0]) for state in selected_states}
    for count in counts:
        state = next(state for state in states if len(state[0])==count)
        signature = tuple(str(i["product_id"]) for i in state[0])
        if signature not in signatures and len(selected_states)<limit:
            selected_states.append(state)
            signatures.add(signature)
    return [items for items, _, _ in selected_states]


def rectangle(item, placement):
    w, d = item["width_cm"], item["depth_cm"]
    if placement["rotation_deg"] in (90, 270):
        w, d = d, w
    return placement["x_cm"], placement["y_cm"], w, d


def intersects(a, b):
    x,y,w,d = a
    X,Y,W,D = b
    return x < X+W-1e-7 and X < x+w-1e-7 and y < Y+D-1e-7 and Y < y+d-1e-7


def front_zone(rect, rotation, clearance):
    x,y,w,d = rect
    return {0: (x,y+d,w,clearance), 90: (x-clearance,y,clearance,d),
            180: (x,y-clearance,w,clearance), 270: (x+w,y,clearance,d)}[rotation]


def validate_layout(items, placements, request, blocked=(), clearance=60):
    errors, footprints, fronts = [], [], []
    expected = {str(i["product_id"]): i for i in items}
    seen = set()
    if not isinstance(placements, list):
        return ["placements must be a list"]
    W,D = request["width_cm"], request["depth_cm"]
    def inside(r):
        x,y,w,d = r
        return x >= 0 and y >= 0 and x+w <= W+1e-7 and y+d <= D+1e-7
    for p in placements:
        if not isinstance(p, dict):
            errors.append("Malformed placement")
            continue
        pid = str(p.get("product_id", ""))
        if pid not in expected or pid in seen:
            errors.append(f"Unknown or duplicate ID: {pid}")
            continue
        seen.add(pid)
        try:
            vals = [p[k] for k in ("x_cm", "y_cm", "rotation_deg")]
            if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in vals):
                raise ValueError()
            if p["rotation_deg"] not in (0,90,180,270):
                raise ValueError()
            rect = rectangle(expected[pid], p)
            front = front_zone(rect, p["rotation_deg"], clearance)
        except (KeyError, ValueError, TypeError):
            errors.append(f"Invalid coordinates/rotation: {pid}")
            continue
        if not inside(rect) or not inside(front):
            errors.append(f"Outside room or insufficient front clearance: {pid}")
        if any(intersects(rect, b) for b in blocked):
            errors.append(f"Blocked door/window zone: {pid}")
        footprints.append((pid, rect))
        fronts.append((pid, front))
    if seen != set(expected):
        errors.append("Missing furniture IDs")
    for i,(pid,rect) in enumerate(footprints):
        for oid,other in footprints[i+1:]:
            if intersects(rect,other):
                errors.append(f"Furniture overlap: {pid}/{oid}")
    for pid,front in fronts:
        for oid,rect in footprints:
            if pid != oid and intersects(front,rect):
                errors.append(f"Front clearance obstructed: {pid}/{oid}")
    return errors


def algorithm_layout(items, request, blocked=(), clearance=60):
    ordered = sorted(items, key=lambda i: -i["width_cm"]*i["depth_cm"])
    steps = [0]
    def visit(n, placed):
        if n == len(ordered):
            return placed
        if steps[0] >= 5000:
            return None
        item = ordered[n]
        for rot in (0,180,90,270):
            w,d = (item["width_cm"],item["depth_cm"]) if rot in (0,180) else (item["depth_cm"],item["width_cm"])
            xs = sorted({0, request["width_cm"]-w, *range(0,int(request["width_cm"]-w)+1,20)})
            ys = sorted({0, request["depth_cm"]-d, *range(0,int(request["depth_cm"]-d)+1,20)})
            for x,y in product(xs,ys):
                steps[0] += 1
                p = {"product_id":str(item["product_id"]),"x_cm":x,"y_cm":y,"rotation_deg":rot}
                partial_items = ordered[:n+1]
                if not validate_layout(partial_items, placed+[p], request, blocked, clearance):
                    result = visit(n+1,placed+[p])
                    if result is not None:
                        return result
                if steps[0] >= 5000:
                    return None
        return None
    return visit(0,[])


def layout_examples(room_type):
    """Validated in-context examples; adapted idea, not the official LayoutGPT implementation."""
    categories = {
        "bedroom": [("EX_BED","bed",160,210,120,0,0), ("EX_WARDROBE","wardrobe",80,45,0,355,180)],
        "living_room": [("EX_SOFA","sofa",200,90,100,0,0), ("EX_TABLE","coffee_table",100,50,150,190,0)],
        "office": [("EX_DESK","desk",120,60,0,340,180), ("EX_CHAIR","chair",50,50,35,220,0)],
        "kitchen": [("EX_KITCHEN","kitchen_cabinets",180,60,0,340,180), ("EX_TABLE","dining_table",120,80,220,160,0)],
        "dining_room": [("EX_TABLE","dining_table",120,80,140,160,0)]
    }
    examples = []
    for size in (400,500):
        items, placements = [], []
        for pid,cat,w,d,x,y,rot in categories[room_type]:
            items.append({"product_id":pid,"category":cat,"width_cm":w,"depth_cm":d})
            placements.append({"product_id":pid,"x_cm":x,"y_cm":y,"rotation_deg":rot})
        room = {"room_type":room_type,"width_cm":size,"depth_cm":size}
        if validate_layout(items,placements,room,clearance=60):
            raise ValueError("Internal layout example failed validation")
        examples.append({"input":{"room":room,"furniture":items,"front_clearance_cm":60},
                         "output":{"placements":placements}})
    return examples


class LayoutValidationError(ValueError):
    """The model responded but its geometry remained invalid."""


def qwen_layout(items, request, blocked=(), clearance=60, generator=None):
    """Local Ollama only: no paid API, no arbitrary remote endpoint."""
    brief = {"room":request,"blocked_zones_cm":list(blocked),"front_clearance_cm":clearance,
             "furniture":[{k:i[k] for k in ("product_id","category","width_cm","depth_cm")} for i in items]}
    seed = algorithm_layout(items,request,blocked,clearance)
    if seed is not None:
        brief["validated_starting_layout"] = {"placements":seed}
    instruction = ('You plan room furniture. Output JSON {"placements":[{"product_id":"ID","x_cm":0,"y_cm":0,"rotation_deg":0}]}. '
                   'Use every supplied ID exactly once. Do not invent or change furniture dimensions. Coordinates in centimetres, bottom-left origin. '
                   'Furniture must not overlap, leave blocked zones empty, stay inside room. '
                   'Rotation 0 faces +y, 90 faces -x, 180 faces -y, 270 faces +x. Reserve stated front clearance inside room. '
                   'A validated_starting_layout, when supplied, satisfies the constraints. You may return it unchanged or improve it while preserving validity. '
                   'JSON only. Request: '+json.dumps(brief,ensure_ascii=False))
    messages = [{"role":"system","content":"Plan furniture placement using the examples. Example IDs must NEVER appear in the final plan. Dimensions and coordinates are in centimetres."}]
    for example in layout_examples(request["room_type"]):
        messages.extend([{"role":"user","content":json.dumps(example["input"])},
                         {"role":"assistant","content":json.dumps(example["output"])}])
    messages.append({"role":"user","content":instruction})
    errors = []
    for _ in range(3):
        if generator is not None:
            content = generator(messages)
        else:
            body = json.dumps({"model":"qwen2.5:3b","messages":messages,"stream":False,"format":"json",
                               "options":{"temperature":0,"num_predict":1400}}).encode()
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=180) as response:
                content = json.load(response)["message"]["content"]
        try:
            placements = json.loads(content).get("placements")
            errors = validate_layout(items,placements,request,blocked,clearance)
        except (ValueError,AttributeError,TypeError) as exc:
            errors = [f"Invalid JSON: {exc}"]
        if not errors:
            return placements
        messages.extend([{"role":"assistant","content":content},
                         {"role":"user","content":"Correct these errors, return full JSON: "+"; ".join(errors)}])
    raise LayoutValidationError("AI жоспары геометрия тексерісінен өтпеді: "+"; ".join(errors))


class CloudServiceError(ValueError):
    """Cloud transport failed; a local algorithm can still build a plan."""


def cloud_layout(items, request, api_key, model="openai/gpt-oss-20b", blocked=(), clearance=60):
    """Groq Cloud transport; shares the same validation and correction loop."""
    if not api_key or not str(api_key).strip():
        raise ValueError("Streamlit Secrets ішінде GROQ_API_KEY енгізіңіз.")
    def generate(messages):
        from urllib.error import HTTPError, URLError
        payload = {"model":model, "messages":messages, "temperature":0,
                   "max_completion_tokens":2000,"response_format":{"type":"json_object"}}
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json","Accept":"application/json",
                     "User-Agent":"cogntech-furniture-search/1.0","Authorization":"Bearer "+api_key.strip()})
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                content = json.load(response)["choices"][0]["message"]["content"]
            if not isinstance(content,str):
                raise ValueError("Модель мәтіндік JSON қайтармады.")
            return content
        except HTTPError as exc:
            detail = ""
            try:
                body = exc.read(8192).decode("utf-8",errors="replace")
                try:
                    error = json.loads(body).get("error",{})
                    if isinstance(error,dict):
                        detail = str(error.get("message", ""))
                except (ValueError,AttributeError):
                    if "1010" in body:
                        detail = "Cloudflare 1010: service blocked this client."
                detail = re.sub(r"gsk_[A-Za-z0-9_-]+", "[REDACTED]",detail.replace(api_key,"[REDACTED]"))[:400]
            except Exception:
                pass
            explanation = {401:"API кілтін тексеріңіз.",403:"Аккаунт/модель рұқсатын тексеріңіз.",
                           429:"Тегін сұрау лимиті бітті. Кейінірек қайталаңыз.",
                           400:"Модель немесе JSON параметрін тексеріңіз.",404:"Модель қолжетімсіз; GROQ_MODEL мәнін өзгертіңіз."}.get(exc.code,"Модель сервисі уақытша қолжетімсіз.")
            raise CloudServiceError(f"Groq HTTP {exc.code}: {explanation}" + (" · "+detail if detail else "")) from None
        except URLError:
            raise ValueError("Модель серверіне қосылу мүмкін болмады.") from None
    return qwen_layout(items,request,blocked,clearance,generator=generate)


def draw_layout(items, placements, request, blocked=(), clearance=60):
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    fig = Figure(figsize=(10,10),dpi=150)
    ax = fig.subplots()
    fig.subplots_adjust(left=.08,right=.98,bottom=.08,top=.98)
    colors = ["#d8e8f5", "#e8dfef", "#e6edd6", "#f3e3cd"]
    lookup = {str(i["product_id"]):i for i in items}
    for n,p in enumerate(placements):
        rect = rectangle(lookup[p["product_id"]],p)
        x,y,w,d = rect
        is_placeholder = lookup[p["product_id"]].get("placeholder",False)
        ax.add_patch(Rectangle((x,y),w,d,facecolor="#f7ead5" if is_placeholder else colors[n%4],edgecolor="#34495e",hatch="//" if is_placeholder else None))
        category = lookup[p["product_id"]]["category"]
        label = {"bed":"Төсек","wardrobe":"Шкаф","sofa":"Диван","dresser":"Комод",
                 "desk":"Үстел","chair":"Орындық","dining_table":"Асхана үстелі",
                 "kitchen_cabinets":"Асүй жиһазы"}.get(category,category)
        number = next(k+1 for k,item in enumerate(items) if str(item["product_id"])==p["product_id"])
        ax.text(x+w/2,y+d/2,f'{number}. {label}\n{w:g} × {d:g} см',ha="center",va="center",fontsize=10)
        X,Y,W,D = front_zone(rect,p["rotation_deg"],clearance)
        ax.add_patch(Rectangle((X,Y),W,D,fill=False,edgecolor="#999999",linestyle=":"))
    for x,y,w,d in blocked:
        ax.add_patch(Rectangle((x,y),w,d,facecolor="#f3b8b8",alpha=.7,hatch="//"))
    ax.set(xlim=(0,request["width_cm"]),ylim=(0,request["depth_cm"]),xlabel="cm",ylabel="cm",aspect="equal")
    ax.grid(alpha=.2)
    ax.tick_params(labelsize=10)
    fig.tight_layout(pad=1)
    return fig

