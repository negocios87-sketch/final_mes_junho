"""
Painel de Atingimento — Elite, Sniper, Olympus
Deploy: Vercel (serverless)
"""

from flask import Flask, jsonify
import requests as req
import pandas as pd
import unicodedata
import calendar
import math
import os
from datetime import date, datetime, timedelta
from io import StringIO

app = Flask(__name__)

API_KEY  = os.environ.get("PIPE_API_KEY", "")
BASE_V1  = "https://boardacademy.pipedrive.com/api/v1"
BASE_V2  = "https://boardacademy.pipedrive.com/api/v2"

FILTER_DEALS      = int(os.environ.get("FILTER_DEALS",      "74674"))
FILTER_DEALS_RV   = int(os.environ.get("FILTER_DEALS_RV",   "1431880"))
FILTER_ACTIVITIES = int(os.environ.get("FILTER_ACTIVITIES", "1310451"))

CF_MULTIPLICADOR = "7e0e43c2734751f77be292a72527f638a850ad50"
CF_QUALIFICADOR  = "a6f13cc27c8d041f3af4091283ce0d4fe0913875"

URL_COLAB    = os.environ.get("URL_COLAB",    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=1782440078&single=true&output=csv")
URL_METAS    = os.environ.get("URL_METAS",    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=0&single=true&output=csv")
URL_FERIADOS = os.environ.get("URL_FERIADOS", "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=1010928978&single=true&output=csv")

DENISE_NORM     = "denise mussolin"
FUNIL_SQUAD_MAP = {"elite": "Elite", "sniper": "Sniper", "olympus": "Olympus", "mgm": "Olympus", "navigator": "Olympus"}
TIMES_ALVO      = {"elite", "sniper", "olympus", "mgm"}
EXCLUIR_REU     = {"matheus paz"}

# ── HELPERS ──────────────────────────────────────────────────

def norm(s):
    if not s: return ""
    s = str(s).strip().lower()
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()

def arred(v):
    try:
        f = float(v)
        return 0.0 if math.isnan(f) or math.isinf(f) else round(f, 2)
    except: return 0.0

def safe_div(a, b):
    try: return float(a) / float(b) if b else 0.0
    except: return 0.0

def cf(deal, key):
    val = deal.get(key)
    if val is None: return None
    if isinstance(val, dict): return val.get("value") or val.get("label")
    return val

def get_owner_name(deal):
    uid = deal.get("user_id")
    if isinstance(uid, dict): return uid.get("name", "")
    return ""

def get_owner_id(deal):
    uid = deal.get("user_id")
    if isinstance(uid, dict): return uid.get("id")
    return uid

def limpar_nans(obj):
    if isinstance(obj, dict): return {k: limpar_nans(v) for k, v in obj.items()}
    if isinstance(obj, list): return [limpar_nans(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
    return obj

def du_mes_total(ano, mes, feriados=set()):
    return sum(1 for d in range(1, calendar.monthrange(ano, mes)[1] + 1)
               if date(ano, mes, d).weekday() < 5 and date(ano, mes, d) not in feriados)

def du_passados(ano, mes, feriados=set()):
    hoje = date.today()
    return max(sum(1 for d in range(1, min(hoje.day, calendar.monthrange(ano, mes)[1]) + 1)
                   if date(ano, mes, d).weekday() < 5 and date(ano, mes, d) not in feriados), 1)

def du_restantes(ano, mes, feriados=set()):
    hoje = date.today()
    ultimo = calendar.monthrange(ano, mes)[1]
    return sum(1 for d in range(hoje.day + 1, ultimo + 1)
               if date(ano, mes, d).weekday() < 5 and date(ano, mes, d) not in feriados)

# ── SHEETS ───────────────────────────────────────────────────

def ler_sheet(url):
    resp = req.get(url, timeout=15)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))

def buscar_colaboradores(mes=None, ano=None):
    df = ler_sheet(URL_COLAB)
    df.columns = [c.strip() for c in df.columns]
    mes_col = next((c for c in df.columns if "mes" in norm(c) and "ref" in norm(c)), None)
    ano_col = next((c for c in df.columns if "ano" in norm(c) and "ref" in norm(c)), None)
    if mes_col and ano_col and mes and ano:
        def to_int(v):
            try: return int(float(str(v)))
            except: return 0
        mask = (df[mes_col].apply(to_int) == mes) & (df[ano_col].apply(to_int) == ano)
        filtered = df[mask].copy()
        if not filtered.empty:
            df = filtered
    status_col = next((c for c in df.columns if "status" in norm(c)), None)
    if status_col:
        df = df[df[status_col].apply(lambda x: norm(str(x)) == "ativo")]
    return df

def buscar_feriados():
    try:
        df = ler_sheet(URL_FERIADOS)
        feriados = set()
        for _, row in df.iterrows():
            val = str(row.iloc[0]).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    feriados.add(datetime.strptime(val, fmt).date())
                    break
                except: continue
        return feriados
    except: return set()

def buscar_metas(ano, mes):
    df = ler_sheet(URL_METAS)
    df.columns = [c.strip() for c in df.columns]

    def to_num(v):
        try:
            if v is None: return 0.0
            if isinstance(v, float) and math.isnan(v): return 0.0
            return float(str(v).replace("R$","").replace(".","").replace(",",".").strip() or "0")
        except: return 0.0

    col_ano  = next((c for c in df.columns if norm(c) == "ano"), None)
    col_mes  = next((c for c in df.columns if norm(c) == "mes"), None)
    col_nome = next((c for c in df.columns if norm(c) == "nome"), None)
    col_reu  = next((c for c in df.columns if "reuni" in norm(c) and "meta" in norm(c)), None)
    col_fin  = next((c for c in df.columns if "financ" in norm(c)), None)
    col_du   = next((c for c in df.columns if "util" in norm(c)), None)

    rows = []
    for _, row in df.iterrows():
        try:
            a = int(float(str(row[col_ano]))) if col_ano else 0
            m = int(float(str(row[col_mes]))) if col_mes else 0
        except: continue
        if a != ano or m != mes: continue
        nome_raw = str(row[col_nome]).strip() if col_nome else ""
        meta_reu = to_num(row[col_reu]) if col_reu else 0.0
        meta_fin = to_num(row[col_fin]) if col_fin else 0.0
        dias_ut  = 0
        if col_du:
            try: dias_ut = int(float(str(row[col_du] or 0)))
            except: pass
        rows.append({
            "nome": nome_raw, "nome_norm": norm(nome_raw),
            "meta_reu": meta_reu, "meta_fin": meta_fin, "dias_uteis": dias_ut,
        })
    return rows

# ── PIPEDRIVE ────────────────────────────────────────────────

def buscar_users_pipe():
    resp = req.get(f"{BASE_V1}/users", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    return {u["id"]: u["name"] for u in (resp.json().get("data") or [])}

def buscar_pipelines():
    resp = req.get(f"{BASE_V1}/pipelines", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    return {p["id"]: norm(p["name"]) for p in (resp.json().get("data") or [])}

def buscar_qual_ids():
    resp = req.get(f"{BASE_V1}/dealFields", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    for field in (resp.json().get("data") or []):
        if field.get("key") == CF_QUALIFICADOR:
            return {norm(opt.get("label", "")): str(opt.get("id")) for opt in (field.get("options") or [])}
    return {}

def won_time_br(deal):
    wt = deal.get("won_time", "")
    if not wt: return ""
    try:
        dt = datetime.fromisoformat(str(wt).replace("Z", "+00:00"))
        return (dt - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    except: return str(wt)

def buscar_deals_mes(mes, ano):
    todos, start = [], 0
    mes_str = f"{ano}-{mes:02d}"
    while True:
        resp = req.get(f"{BASE_V1}/deals", params={
            "filter_id": FILTER_DEALS, "status": "won",
            "sort": "won_time DESC", "limit": 500,
            "start": start, "api_token": API_KEY,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        lote = data.get("data") or []
        found_older = False
        for deal in lote:
            wt_br = won_time_br(deal)[:7]
            if wt_br == mes_str: todos.append(deal)
            elif wt_br < mes_str: found_older = True
        mais = data.get("additional_data", {}).get("pagination", {}).get("more_items_in_collection", False)
        if not mais or not lote or found_older: break
        start += 500
    return todos

def buscar_deals_rv_mes(mes, ano):
    deal_ids_validos = set()
    mapa_owner = {}
    start = 0
    while True:
        resp = req.get(f"{BASE_V1}/deals", params={
            "filter_id": FILTER_DEALS_RV, "status": "all_not_deleted",
            "limit": 500, "start": start, "api_token": API_KEY,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        lote = data.get("data") or []
        for d in lote:
            did = d["id"]
            uid = d.get("user_id")
            deal_ids_validos.add(did)
            mapa_owner[did] = uid.get("id") if isinstance(uid, dict) else uid
        mais = data.get("additional_data", {}).get("pagination", {}).get("more_items_in_collection", False)
        if not mais or not lote: break
        start += 500
    return deal_ids_validos, mapa_owner

def buscar_activities_mes(mes, ano):
    todos, cursor = [], None
    mes_str = f"{ano}-{mes:02d}"
    while True:
        params = {"filter_id": FILTER_ACTIVITIES, "limit": 200}
        if cursor: params["cursor"] = cursor
        resp = req.get(f"{BASE_V2}/activities", params=params,
                       headers={"x-api-token": API_KEY}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        lote = data.get("data") or []
        for act in lote:
            if str(act.get("due_date", ""))[:7] == mes_str:
                todos.append(act)
        cursor = data.get("additional_data", {}).get("next_cursor")
        if not cursor or not lote: break
    return todos

# ── CÁLCULO PRINCIPAL ─────────────────────────────────────────

def calcular(mes=None, ano=None):
    hoje = date.today()
    mes  = mes or hoje.month
    ano  = ano or hoje.year

    feriados = buscar_feriados()
    du_calc  = du_mes_total(ano, mes, feriados)

    if (ano < hoje.year) or (ano == hoje.year and mes < hoje.month):
        du_pass = du_calc
        du_rest = 0
    else:
        du_pass = du_passados(ano, mes, feriados)
        du_rest = du_restantes(ano, mes, feriados)

    colab_df   = buscar_colaboradores(mes=mes, ano=ano)
    metas      = buscar_metas(ano, mes)
    users_pipe = buscar_users_pipe()
    qual_ids   = buscar_qual_ids()
    deals      = buscar_deals_mes(mes, ano)
    activities = buscar_activities_mes(mes, ano)
    pipes      = buscar_pipelines()
    deal_ids_validos, mapa_deal_owner = buscar_deals_rv_mes(mes, ano)

    du_sheet = next((m["dias_uteis"] for m in metas if m["dias_uteis"] > 0), 0)
    du_total = du_sheet if du_sheet > 0 else du_calc

    sub_col   = next((c for c in colab_df.columns if norm(c) == "subarea"), None)
    nome_col  = next((c for c in colab_df.columns if norm(c) == "nome"), "Nome")
    cargo_col = next((c for c in colab_df.columns if norm(c) == "cargo"), None)

    nome_to_subarea = {}
    nome_to_cargo   = {}
    for _, row in colab_df.iterrows():
        nn  = norm(str(row.get(nome_col, "")))
        sub = str(row.get(sub_col, "")).strip() if sub_col else ""
        cg  = str(row.get(cargo_col, "")).strip() if cargo_col else ""
        nome_to_subarea[nn] = sub
        nome_to_cargo[nn]   = cg

    nome_norm_to_uid = {norm(name): uid for uid, name in users_pipe.items()}
    uid_to_nome_norm = {uid: norm(name) for uid, name in users_pipe.items()}

    excluir_uids = {str(uid) for uid, name in users_pipe.items()
                    if norm(name) in EXCLUIR_REU}

    # ── Realizado financeiro por closer (valor BRUTO) ──
    closer_real = {}
    for deal in deals:
        owner_nn = norm(get_owner_name(deal))
        if not owner_nn:
            oid = get_owner_id(deal)
            owner_nn = uid_to_nome_norm.get(oid, "")
        if not owner_nn: continue

        valor = float(deal.get("value") or 0)

        # Denise: distribui por funil
        if owner_nn == DENISE_NORM:
            pipe_id   = deal.get("pipeline_id")
            pipe_norm = pipes.get(pipe_id, "")
            squad_key = FUNIL_SQUAD_MAP.get(pipe_norm)
            if squad_key:
                k = f"__denise__{squad_key.lower()}"
                if k not in closer_real:
                    closer_real[k] = {"valor": 0, "qtd": 0, "denise_squad": squad_key}
                closer_real[k]["valor"] += valor
                closer_real[k]["qtd"]   += 1
                continue

        if owner_nn not in closer_real:
            closer_real[owner_nn] = {"valor": 0, "qtd": 0}
        closer_real[owner_nn]["valor"] += valor
        closer_real[owner_nn]["qtd"]   += 1

    # ── Atividades agrupadas por owner ──
    acts_by_owner    = {}
    acts_by_deal_own = {}
    for d in deals:
        did = d["id"]
        uid = d.get("user_id")
        oid = uid.get("id") if isinstance(uid, dict) else uid
        if oid:
            mapa_deal_owner.setdefault(did, oid)

    for act in activities:
        oid = str(act.get("owner_id", ""))
        acts_by_owner.setdefault(oid, []).append(act)
        deal_id = act.get("deal_id")
        if deal_id:
            deal_own = str(mapa_deal_owner.get(deal_id, ""))
            if deal_own:
                acts_by_deal_own.setdefault(deal_own, []).append(act)

    def act_valida_sdr(act):
        if not (act.get("done") is True or act.get("status") == "done"): return False
        deal_id    = act.get("deal_id")
        act_owner  = str(act.get("owner_id", ""))
        deal_owner = str(mapa_deal_owner.get(deal_id, "")) if deal_id else ""
        if act_owner and deal_owner and act_owner == deal_owner: return False
        if deal_id and deal_id not in deal_ids_validos: return False
        return True

    # ── Filtra metas pelos times alvo ──
    closers_metas = [m for m in metas if m["meta_reu"] == 0 and m["meta_fin"] > 0
                     and norm(nome_to_subarea.get(m["nome_norm"], "")) in TIMES_ALVO]
    sdrs_metas    = [m for m in metas if m["meta_reu"] > 0 and m["meta_fin"] > 0
                     and norm(nome_to_subarea.get(m["nome_norm"], "")) in TIMES_ALVO]

    # ── Monta squads ──
    squads = {}

    def get_squad(sub_norm):
        display = {"mgm": "Olympus"}.get(sub_norm, sub_norm.capitalize())
        if display not in squads:
            squads[display] = {"nome": display, "closers": [], "sdrs": []}
        return squads[display]

    # Closers
    for m in closers_metas:
        nn  = m["nome_norm"]
        sub = norm(nome_to_subarea.get(nn, ""))
        if sub not in TIMES_ALVO: continue

        ri    = closer_real.get(nn, {"valor": 0, "qtd": 0})
        meta  = m["meta_fin"]
        real  = ri["valor"]
        qtd   = ri["qtd"]
        mtd   = safe_div(meta, du_total) * du_pass
        pct   = arred(safe_div(real, meta) * 100)
        pct_mtd = arred(safe_div(real, mtd) * 100) if mtd else 0

        get_squad(sub)["closers"].append({
            "nome": m["nome"],
            "meta": arred(meta),
            "realizado": arred(real),
            "qtd_ganhos": qtd,
            "ticket_medio": arred(safe_div(real, qtd)) if qtd else 0,
            "pct_atingido": pct,
            "mtd": arred(mtd),
            "pct_mtd": pct_mtd,
            "deficit_meta": arred(meta - real),
            "meta_dia": arred(safe_div(meta - real, du_rest)) if du_rest else 0,
        })

    # Injeta Denise nos squads dela
    for k, ri in closer_real.items():
        if not k.startswith("__denise__"): continue
        squad_display = ri["denise_squad"]
        sub_norm      = norm(squad_display)
        if sub_norm not in TIMES_ALVO and sub_norm != "olympus": continue
        meta  = 0
        real  = ri["valor"]
        qtd   = ri["qtd"]
        mtd   = 0
        squads.setdefault(squad_display, {"nome": squad_display, "closers": [], "sdrs": []})
        squads[squad_display]["closers"].append({
            "nome": "Denise Mussolin*",
            "meta": 0, "realizado": arred(real),
            "qtd_ganhos": qtd,
            "ticket_medio": arred(safe_div(real, qtd)) if qtd else 0,
            "pct_atingido": 0, "mtd": 0, "pct_mtd": 0,
            "deficit_meta": 0, "meta_dia": 0,
            "is_head": True,
        })

    # SDRs
    for m in sdrs_metas:
        nn  = m["nome_norm"]
        sub = norm(nome_to_subarea.get(nn, ""))
        if sub not in TIMES_ALVO: continue

        meta_reu = m["meta_reu"]
        uid      = nome_norm_to_uid.get(nn)
        uid_str  = str(uid) if uid else ""

        acts_sdr  = acts_by_owner.get(uid_str, [])
        validadas = len([a for a in acts_sdr if act_valida_sdr(a)])
        deveria   = arred(safe_div(meta_reu, du_total) * du_pass)
        pct_reu   = arred(safe_div(validadas, meta_reu) * 100)

        qual_id   = qual_ids.get(nn)
        deals_sdr = [d for d in deals if str(cf(d, CF_QUALIFICADOR)) == str(qual_id)] if qual_id else []
        qtd_ganhos  = len(deals_sdr)
        valor_ganho = sum(float(d.get("value") or 0) for d in deals_sdr)

        get_squad(sub)["sdrs"].append({
            "nome": m["nome"],
            "meta_reuniao": arred(meta_reu),
            "validadas": validadas,
            "deveria_estar": deveria,
            "faltam_mtd": arred(deveria - validadas),
            "faltam_meta": arred(meta_reu - validadas),
            "pct_reu": pct_reu,
            "qtd_ganhos": qtd_ganhos,
            "valor_ganho": arred(valor_ganho),
        })

    # ── Totais por squad ──
    result_squads = []
    ORDER = ["Sniper", "Elite", "Olympus"]
    for nome_sq in ORDER:
        sq = squads.get(nome_sq)
        if not sq: continue

        closers = sq["closers"]
        sdrs    = sq["sdrs"]

        # Exclui Denise* do total financeiro (ela não tem meta)
        closers_com_meta = [c for c in closers if c.get("meta", 0) > 0]

        t_meta     = sum(c["meta"]      for c in closers_com_meta)
        t_real     = sum(c["realizado"] for c in closers_com_meta)
        # Soma Denise separado no realizado
        t_real    += sum(c["realizado"] for c in closers if c.get("is_head"))
        t_qtd      = sum(c["qtd_ganhos"] for c in closers)
        t_mtd      = arred(safe_div(t_meta, du_total) * du_pass)
        t_pct      = arred(safe_div(t_real, t_meta) * 100)
        t_pct_mtd  = arred(safe_div(t_real, t_mtd) * 100) if t_mtd else 0

        t_meta_reu = sum(s["meta_reuniao"]  for s in sdrs)
        t_val      = sum(s["validadas"]      for s in sdrs)
        t_dev      = arred(sum(s["deveria_estar"] for s in sdrs))
        t_pct_reu  = arred(safe_div(t_val, t_meta_reu) * 100)

        result_squads.append({
            "nome": nome_sq,
            "financeiro": {
                "meta":       arred(t_meta),
                "realizado":  arred(t_real),
                "pct":        t_pct,
                "mtd":        t_mtd,
                "pct_mtd":    t_pct_mtd,
                "deficit":    arred(t_meta - t_real),
                "meta_dia":   arred(safe_div(t_meta - t_real, du_rest)) if du_rest else 0,
                "qtd_ganhos": t_qtd,
                "ticket_medio": arred(safe_div(t_real, t_qtd)) if t_qtd else 0,
                "closers": closers,
            },
            "reunioes": {
                "meta":         arred(t_meta_reu),
                "validadas":    t_val,
                "deveria":      t_dev,
                "faltam_meta":  arred(t_meta_reu - t_val),
                "faltam_mtd":   arred(t_dev - t_val),
                "pct":          t_pct_reu,
                "sdrs": sdrs,
            },
        })

    # ── Consolidado total ──
    total_fin_meta  = sum(s["financeiro"]["meta"]      for s in result_squads)
    total_fin_real  = sum(s["financeiro"]["realizado"]  for s in result_squads)
    total_reu_meta  = sum(s["reunioes"]["meta"]         for s in result_squads)
    total_reu_val   = sum(s["reunioes"]["validadas"]    for s in result_squads)

    return limpar_nans({
        "periodo": {
            "mes": mes, "ano": ano,
            "du_total": du_total,
            "du_passados": du_pass,
            "du_restantes": du_rest,
            "atualizado_em": (datetime.now() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M"),
        },
        "squads": result_squads,
        "total": {
            "financeiro": {
                "meta": arred(total_fin_meta),
                "realizado": arred(total_fin_real),
                "pct": arred(safe_div(total_fin_real, total_fin_meta) * 100),
            },
            "reunioes": {
                "meta": arred(total_reu_meta),
                "validadas": total_reu_val,
                "pct": arred(safe_div(total_reu_val, total_reu_meta) * 100),
            },
        },
    })

# ── ROTA ─────────────────────────────────────────────────────

@app.route("/api/dados")
def api_dados():
    try:
        from flask import request as freq
        mes = freq.args.get("mes", type=int)
        ano = freq.args.get("ano", type=int)
        return jsonify(calcular(mes=mes, ano=ano))
    except Exception as e:
        import traceback
        return jsonify({"erro": str(e), "trace": traceback.format_exc()}), 500

@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory("../public", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
