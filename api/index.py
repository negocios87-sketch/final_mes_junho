"""
Painel de Atingimento — Elite, Sniper, Olympus
Deploy: Vercel Pro
Cache: GitHub repo negocios87-sketch/gerente_comercial pasta cache/
"""

from flask import Flask, jsonify, request as freq
import requests as req
import pandas as pd
import unicodedata
import calendar
import math
import os
import time
import json
import base64
from datetime import date, datetime, timedelta
from io import StringIO

app = Flask(__name__)

API_KEY  = os.environ.get("PIPE_API_KEY", "")
BASE_V1  = "https://boardacademy.pipedrive.com/api/v1"
BASE_V2  = "https://boardacademy.pipedrive.com/api/v2"

FILTER_DEALS      = int(os.environ.get("FILTER_DEALS",      "74674"))
FILTER_DEALS_RV   = int(os.environ.get("FILTER_DEALS_RV",   "1431880"))
FILTER_ACTIVITIES = int(os.environ.get("FILTER_ACTIVITIES", "1310451"))

CF_QUALIFICADOR  = "a6f13cc27c8d041f3af4091283ce0d4fe0913875"

URL_COLAB    = os.environ.get("URL_COLAB",    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=1782440078&single=true&output=csv")
URL_METAS    = os.environ.get("URL_METAS",    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=0&single=true&output=csv")
URL_FERIADOS = os.environ.get("URL_FERIADOS", "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvwO3Ag2f2cbkVgR1pJZp6fANQcbualGKlAG50fmOljuEGKZ1gJBbSAjRdO3SomXUEVQOWnTvlfHRd/pub?gid=1010928978&single=true&output=csv")

DENISE_NORM        = "denise mussolin"
FUNIL_SQUAD_MAP    = {"elite": "Elite", "sniper": "Sniper", "olympus": "Olympus", "mgm": "Olympus", "navigator": "Olympus"}
TIMES_ALVO         = {"elite", "sniper", "olympus", "mgm"}
META_REUNIOES_FIXA = 250
DATA_CORTE_REU     = "2026-06-22"

CACHE_TTL_FINANCEIRO = 600   # 10 minutos
CACHE_TTL_REUNIOES   = 300   # 5 minutos

# ── GITHUB CACHE ─────────────────────────────────────────────
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = "negocios87-sketch/gerente_comercial"
GITHUB_BRANCH = "main"

CACHE_PATH_FIN = "cache/painel_financeiro.json"
CACHE_PATH_REU = "cache/painel_reunioes.json"

def github_read(path):
    """Lê arquivo do GitHub. Retorna (conteudo_dict, sha) ou (None, None)."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        resp = req.get(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, timeout=10)
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    except Exception as e:
        print(f"github_read erro {path}: {e}")
        return None, None

def github_write(path, payload, sha=None, ttl=600):
    """Salva arquivo no GitHub com timestamp."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        content = json.dumps({"_ts": time.time(), "_ttl": ttl, "payload": payload}, ensure_ascii=False)
        body = {
            "message": f"cache {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": GITHUB_BRANCH,
        }
        if sha:
            body["sha"] = sha
        resp = req.put(url, json=body, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, timeout=15)
        resp.raise_for_status()
        return resp.json().get("content", {}).get("sha")
    except Exception as e:
        print(f"github_write erro {path}: {e}")
        return sha

def cache_get(path, ttl):
    """Retorna (payload, sha, expirado)."""
    data, sha = github_read(path)
    if not data:
        return None, None, True
    expirado = time.time() - data.get("_ts", 0) > ttl
    return data.get("payload"), sha, expirado

# ── CACHE EM MEMÓRIA ─────────────────────────────────────────
_mem = {}
MEM_TTL = 300

def mem_get(key):
    item = _mem.get(key)
    if item and time.time() - item['t'] < MEM_TTL:
        return item['v']
    return None

def mem_set(key, val):
    _mem[key] = {'v': val, 't': time.time()}

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
    cached = mem_get('feriados')
    if cached is not None: return cached
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
        mem_set('feriados', feriados)
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
    cached = mem_get('users')
    if cached: return cached
    resp = req.get(f"{BASE_V1}/users", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    result = {u["id"]: u["name"] for u in (resp.json().get("data") or [])}
    mem_set('users', result)
    return result

def buscar_pipelines():
    cached = mem_get('pipelines')
    if cached: return cached
    resp = req.get(f"{BASE_V1}/pipelines", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    result = {p["id"]: norm(p["name"]) for p in (resp.json().get("data") or [])}
    mem_set('pipelines', result)
    return result

def buscar_qual_ids():
    cached = mem_get('qual_ids')
    if cached: return cached
    resp = req.get(f"{BASE_V1}/dealFields", params={"api_token": API_KEY}, timeout=15)
    resp.raise_for_status()
    for field in (resp.json().get("data") or []):
        if field.get("key") == CF_QUALIFICADOR:
            result = {norm(opt.get("label", "")): str(opt.get("id")) for opt in (field.get("options") or [])}
            mem_set('qual_ids', result)
            return result
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
        time.sleep(0.3)
    return todos

def buscar_deals_rv(mes, ano):
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
        time.sleep(0.8)
    return deal_ids_validos, mapa_owner

def buscar_activities_corte(mes, ano):
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
            due = str(act.get("due_date", "") or "")[:10]
            if due[:7] == mes_str and due >= DATA_CORTE_REU:
                todos.append(act)
        cursor = data.get("additional_data", {}).get("next_cursor")
        if not cursor or not lote: break
        time.sleep(0.3)
    return todos

# ── CÁLCULO FINANCEIRO ────────────────────────────────────────

def calcular_financeiro(mes=None, ano=None):
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
    pipes      = buscar_pipelines()
    deals      = buscar_deals_mes(mes, ano)

    du_sheet = next((m["dias_uteis"] for m in metas if m["dias_uteis"] > 0), 0)
    du_total = du_sheet if du_sheet > 0 else du_calc

    sub_col  = next((c for c in colab_df.columns if norm(c) == "subarea"), None)
    nome_col = next((c for c in colab_df.columns if norm(c) == "nome"), "Nome")
    nome_to_subarea = {}
    for _, row in colab_df.iterrows():
        nn  = norm(str(row.get(nome_col, "")))
        sub = str(row.get(sub_col, "")).strip() if sub_col else ""
        nome_to_subarea[nn] = sub

    uid_to_nome_norm = {uid: norm(name) for uid, name in users_pipe.items()}

    closer_real = {}
    for deal in deals:
        owner_nn = norm(get_owner_name(deal))
        if not owner_nn:
            oid = get_owner_id(deal)
            owner_nn = uid_to_nome_norm.get(oid, "")
        if not owner_nn: continue
        valor = float(cf(deal, "7e0e43c2734751f77be292a72527f638a850ad50") or 0)
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

    closers_metas = [m for m in metas if m["meta_reu"] == 0 and m["meta_fin"] > 0
                     and norm(nome_to_subarea.get(m["nome_norm"], "")) in TIMES_ALVO]

    fin_meta = sum(m["meta_fin"] for m in closers_metas)
    fin_real = sum(closer_real.get(m["nome_norm"], {"valor": 0})["valor"] for m in closers_metas)
    fin_qtd  = sum(closer_real.get(m["nome_norm"], {"qtd": 0})["qtd"] for m in closers_metas)

    for k, ri in closer_real.items():
        if not k.startswith("__denise__"): continue
        if norm(ri["denise_squad"]) in TIMES_ALVO or ri["denise_squad"] == "Olympus":
            fin_real += ri["valor"]
            fin_qtd  += ri["qtd"]

    return limpar_nans({
        "periodo": {
            "mes": mes, "ano": ano,
            "du_total": du_total,
            "du_passados": du_pass,
            "du_restantes": du_rest,
            "atualizado_em": (datetime.now() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M"),
        },
        "financeiro": {
            "meta":      arred(fin_meta),
            "realizado": arred(fin_real),
            "pct":       arred(safe_div(fin_real, fin_meta) * 100),
            "qtd":       fin_qtd,
        },
    })

# ── CÁLCULO REUNIÕES ─────────────────────────────────────────

def calcular_reunioes(mes=None, ano=None):
    hoje = date.today()
    mes  = mes or hoje.month
    ano  = ano or hoje.year

    colab_df   = buscar_colaboradores(mes=mes, ano=ano)
    metas      = buscar_metas(ano, mes)
    users_pipe = buscar_users_pipe()
    activities = buscar_activities_corte(mes, ano)
    deal_ids_validos, mapa_deal_owner = buscar_deals_rv(mes, ano)

    sub_col  = next((c for c in colab_df.columns if norm(c) == "subarea"), None)
    nome_col = next((c for c in colab_df.columns if norm(c) == "nome"), "Nome")
    nome_to_subarea = {}
    for _, row in colab_df.iterrows():
        nn  = norm(str(row.get(nome_col, "")))
        sub = str(row.get(sub_col, "")).strip() if sub_col else ""
        nome_to_subarea[nn] = sub

    nome_norm_to_uid = {norm(name): uid for uid, name in users_pipe.items()}

    acts_by_owner = {}
    for act in activities:
        oid = str(act.get("owner_id", ""))
        acts_by_owner.setdefault(oid, []).append(act)

    def act_valida(act):
        if not (act.get("done") is True or act.get("status") == "done"): return False
        deal_id    = act.get("deal_id")
        act_owner  = str(act.get("owner_id", ""))
        deal_owner = str(mapa_deal_owner.get(deal_id, "")) if deal_id else ""
        if act_owner and deal_owner and act_owner == deal_owner: return False
        if deal_id and deal_id not in deal_ids_validos: return False
        return True

    sdrs_metas = [m for m in metas if m["meta_reu"] > 0 and m["meta_fin"] > 0
                  and norm(nome_to_subarea.get(m["nome_norm"], "")) in TIMES_ALVO]

    reu_real = 0
    for m in sdrs_metas:
        nn      = m["nome_norm"]
        uid     = nome_norm_to_uid.get(nn)
        uid_str = str(uid) if uid else ""
        acts    = acts_by_owner.get(uid_str, [])
        reu_real += len([a for a in acts if act_valida(a)])

    return limpar_nans({
        "atualizado_em": (datetime.now() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M"),
        "reunioes": {
            "meta":      META_REUNIOES_FIXA,
            "validadas": reu_real,
            "pct":       arred(safe_div(reu_real, META_REUNIOES_FIXA) * 100),
            "data_corte": DATA_CORTE_REU,
        },
    })

# ── ROTAS ─────────────────────────────────────────────────────

@app.route("/api/financeiro")
def api_financeiro():
    try:
        mes = freq.args.get("mes", type=int)
        ano = freq.args.get("ano", type=int)
        if not mes and not ano:
            payload, sha, expirado = cache_get(CACHE_PATH_FIN, CACHE_TTL_FINANCEIRO)
            if payload and not expirado:
                return jsonify(payload)
            result = calcular_financeiro()
            github_write(CACHE_PATH_FIN, result, sha, CACHE_TTL_FINANCEIRO)
            return jsonify(result)
        return jsonify(calcular_financeiro(mes=mes, ano=ano))
    except Exception as e:
        import traceback
        return jsonify({"erro": str(e), "trace": traceback.format_exc()}), 500

@app.route("/api/reunioes")
def api_reunioes():
    try:
        mes = freq.args.get("mes", type=int)
        ano = freq.args.get("ano", type=int)
        if not mes and not ano:
            payload, sha, expirado = cache_get(CACHE_PATH_REU, CACHE_TTL_REUNIOES)
            if payload and not expirado:
                return jsonify(payload)
            result = calcular_reunioes()
            github_write(CACHE_PATH_REU, result, sha, CACHE_TTL_REUNIOES)
            return jsonify(result)
        return jsonify(calcular_reunioes(mes=mes, ano=ano))
    except Exception as e:
        import traceback
        return jsonify({"erro": str(e), "trace": traceback.format_exc()}), 500

@app.route("/api/cache/limpar", methods=["POST"])
def limpar_cache():
    try:
        for path in [CACHE_PATH_FIN, CACHE_PATH_REU]:
            _, sha = github_read(path)
            if sha:
                content = json.dumps({"_ts": 0, "payload": None}, ensure_ascii=False)
                req.put(
                    f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
                    json={
                        "message": "limpar cache",
                        "content": base64.b64encode(content.encode()).decode(),
                        "branch": GITHUB_BRANCH,
                        "sha": sha,
                    },
                    headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
                    timeout=15
                )
        _mem.clear()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/api/debug/metas")
def debug_metas():
    hoje = date.today()
    mes = freq.args.get("mes", type=int) or hoje.month
    ano = freq.args.get("ano", type=int) or hoje.year
    metas = buscar_metas(ano, mes)
    colab_df = buscar_colaboradores(mes=mes, ano=ano)
    sub_col  = next((c for c in colab_df.columns if norm(c) == "subarea"), None)
    nome_col = next((c for c in colab_df.columns if norm(c) == "nome"), "Nome")
    nome_to_sub = {norm(str(row.get(nome_col,""))): str(row.get(sub_col,"")).strip() for _, row in colab_df.iterrows()} if sub_col else {}
    closers_alvo = [m for m in metas if m["meta_reu"] == 0 and m["meta_fin"] > 0
                    and norm(nome_to_sub.get(m["nome_norm"], "")) in TIMES_ALVO]
    return jsonify({
        "mes": mes, "ano": ano,
        "closers_filtrados": [{"nome": m["nome"], "subarea": nome_to_sub.get(m["nome_norm"], "?"), "meta_fin": m["meta_fin"]} for m in closers_alvo],
        "total_filtrado": sum(m["meta_fin"] for m in closers_alvo),
    })

@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory("../public", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
