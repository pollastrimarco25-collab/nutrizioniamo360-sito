#!/usr/bin/env python3
"""
Rassegna scientifica settimanale di NutrizioniaMO 360.

1. Cerca su PubMed (API E-utilities di NCBI) gli studi recenti per ogni tema della configurazione.
2. Chiede a Claude di scegliere i più rilevanti per professionisti sanitari.
3. Chiede a Claude una sintesi neutra in italiano basata SOLO sull'abstract.
4. Aggiunge il numero della settimana in sito/rassegna.json.

I dati bibliografici (titolo originale, rivista, data, DOI, link) arrivano sempre da PubMed,
mai dall'AI. I numeri delle sintesi che non compaiono nell'abstract vengono segnalati
nella richiesta di revisione.

Uso:
  python3 strumenti/rassegna.py               esecuzione completa
  python3 strumenti/rassegna.py --solo-pubmed  prova: mostra solo i candidati trovati su PubMed

Variabili d'ambiente: ANTHROPIC_API_KEY (obbligatoria per l'esecuzione completa),
NCBI_API_KEY e NCBI_EMAIL (consigliate), PR_BODY (percorso dove scrivere il testo della revisione).
Solo libreria standard di Python 3.9+.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(RADICE, "strumenti", "rassegna_config.json")
DATI = os.path.join(RADICE, "sito", "rassegna.json")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = "nutrizioniamo360-rassegna"


# ---------------------------------------------------------------- PubMed

def ncbi(endpoint, params):
    params = dict(params, tool=TOOL)
    if os.environ.get("NCBI_EMAIL"):
        params["email"] = os.environ["NCBI_EMAIL"]
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    # sempre POST: le ricerche lunghe in GET superano i limiti di NCBI e danno errore 500
    dati = urllib.parse.urlencode(params).encode()
    url = EUTILS + endpoint
    for tentativo in range(4):
        try:
            req = urllib.request.Request(url, data=dati, headers={
                "Content-Type": "application/x-www-form-urlencoded", "User-Agent": TOOL})
            with urllib.request.urlopen(req, timeout=60) as r:
                testo = r.read()
            time.sleep(0.4)  # sotto il limite di NCBI (3 richieste/s senza chiave)
            return testo
        except urllib.error.HTTPError as e:
            corpo = e.read()[:300].decode("utf-8", "replace").replace("\n", " ")
            print(f"  NCBI {endpoint}: HTTP {e.code} (tentativo {tentativo + 1}) {corpo}", file=sys.stderr)
            if 400 <= e.code < 500 and e.code != 429:
                break  # richiesta sbagliata: inutile riprovare
        except Exception as e:  # rete instabile: riprova
            print(f"  NCBI {endpoint}: {e} (tentativo {tentativo + 1})", file=sys.stderr)
        time.sleep(3 * (tentativo + 1))
    raise RuntimeError(f"NCBI {endpoint} non risponde")


DIAGNOSI = "--solo-pubmed" in sys.argv


def cerca(query, giorni, quanti):
    oggi = dt.date.today()
    r = json.loads(ncbi("esearch.fcgi", {
        "db": "pubmed", "term": query, "retmode": "json", "retmax": quanti,
        "sort": "relevance", "datetype": "edat",
        "mindate": (oggi - dt.timedelta(days=giorni)).strftime("%Y/%m/%d"),
        "maxdate": oggi.strftime("%Y/%m/%d"),
    }))["esearchresult"]
    if DIAGNOSI:  # nella prova mostra come PubMed ha interpretato la ricerca
        for chiave in ("errorlist", "warninglist"):
            v = {k: x for k, x in (r.get(chiave) or {}).items() if x}
            if v:
                print(f"    {chiave}: {json.dumps(v, ensure_ascii=False)[:400]}")
        if r.get("querytranslation"):
            print(f'    interpretata come: {r["querytranslation"][:300]}')
    return r.get("idlist", []), int(r.get("count", 0))


FILTRO_SEMPLICE = ('("randomized controlled trial"[pt] OR "meta-analysis"[pt] OR "systematic review"[pt] '
                   'OR randomized[tiab] OR "meta-analysis"[tiab] OR "systematic review"[tiab])')


def testo_di(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


MESI = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def data_pubblicazione(art):
    # preferisce la data di pubblicazione elettronica, poi quella del fascicolo
    ad = art.find("Article/ArticleDate")
    if ad is not None and ad.findtext("Year"):
        return f'{ad.findtext("Year")}-{int(ad.findtext("Month") or 1):02d}-{int(ad.findtext("Day") or 1):02d}'
    pd = art.find("Article/Journal/JournalIssue/PubDate")
    if pd is None:
        return ""
    anno = pd.findtext("Year") or (pd.findtext("MedlineDate") or "")[:4]
    mese = (pd.findtext("Month") or "").strip()
    if mese[:3].lower() in MESI:
        return f"{anno}-{MESI[mese[:3].lower()]:02d}"
    if mese.isdigit():
        return f"{anno}-{int(mese):02d}"
    return anno


def scarica(pmids):
    articoli = {}
    for i in range(0, len(pmids), 150):
        xml = ncbi("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids[i:i + 150]),
                                   "retmode": "xml"})
        for pa in ET.fromstring(xml).findall("PubmedArticle"):
            mc = pa.find("MedlineCitation")
            pmid = mc.findtext("PMID")
            art = mc.find("Article")
            parti = []
            for at in art.findall("Abstract/AbstractText"):
                etichetta = at.get("Label")
                t = testo_di(at)
                if t:
                    parti.append(f"{etichetta}: {t}" if etichetta else t)
            doi = ""
            for e in art.findall("ELocationID"):
                if e.get("EIdType") == "doi":
                    doi = (e.text or "").strip()
            if not doi:
                for e in pa.findall("PubmedData/ArticleIdList/ArticleId"):
                    if e.get("IdType") == "doi":
                        doi = (e.text or "").strip()
            articoli[pmid] = {
                "pmid": pmid,
                "titolo": testo_di(art.find("ArticleTitle")),
                "abstract": "\n".join(parti),
                "rivista": art.findtext("Journal/Title") or "",
                "rivista_abbr": art.findtext("Journal/ISOAbbreviation") or mc.findtext("MedlineJournalInfo/MedlineTA") or "",
                "data": data_pubblicazione(mc),
                "tipi": [testo_di(t) for t in art.findall("PublicationTypeList/PublicationType")],
                "doi": doi,
            }
    return articoli


def candidati(cfg, gia_usciti):
    trovati = {}
    for tema in cfg["temi"]:
        q = f'({tema["query"]}) AND {cfg["filtro_comune"]}'
        try:
            ids, totale = cerca(q, cfg["giorni_finestra"], cfg["candidati_per_tema"])
        except RuntimeError:
            # PubMed a volte non regge le ricerche complesse: riprova con un filtro più semplice
            print(f'- {tema["nome"]}: ricerca completa non riuscita, riprovo con un filtro semplificato')
            try:
                ids, totale = cerca(f'({tema["query"]}) AND {FILTRO_SEMPLICE}', cfg["giorni_finestra"], cfg["candidati_per_tema"])
            except RuntimeError as e:
                print(f'- {tema["nome"]}: ricerca non riuscita ({e}), tema saltato questa settimana')
                continue
        print(f'- {tema["nome"]}: {totale} risultati, presi i primi {len(ids)}')
        for pmid in ids:
            if pmid not in gia_usciti:
                trovati.setdefault(pmid, []).append(tema["nome"])
    if not trovati:
        return {}
    articoli = scarica(list(trovati))
    for pmid, a in articoli.items():
        a["temi"] = trovati.get(pmid, [])
    # senza abstract non si può fare una sintesi onesta
    return {p: a for p, a in articoli.items() if len(a["abstract"]) > 300}


# ---------------------------------------------------------------- Claude

def claude(cfg, sistema, messaggio, max_tokens):
    chiave = os.environ.get("ANTHROPIC_API_KEY")
    if not chiave:
        sys.exit("Manca ANTHROPIC_API_KEY.")
    corpo = json.dumps({
        "model": cfg["modello"], "max_tokens": max_tokens, "system": sistema,
        "messages": [{"role": "user", "content": messaggio}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=corpo, headers={
        "x-api-key": chiave, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    for tentativo in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                risposta = json.loads(r.read())
            u = risposta.get("usage", {})
            print(f'  Claude: {u.get("input_tokens")} token letti, {u.get("output_tokens")} scritti')
            return "".join(b.get("text", "") for b in risposta["content"] if b.get("type") == "text")
        except Exception as e:
            print(f"  Claude: {e} (tentativo {tentativo + 1})", file=sys.stderr)
            time.sleep(10 * (tentativo + 1))
    raise RuntimeError("L'API di Claude non risponde")


def estrai_json(testo):
    testo = re.sub(r"^```(?:json)?|```$", "", testo.strip(), flags=re.M)
    inizio = min([i for i in (testo.find("{"), testo.find("[")) if i >= 0], default=-1)
    fine = max(testo.rfind("}"), testo.rfind("]"))
    return json.loads(testo[inizio:fine + 1])


SISTEMA_SELEZIONE = """Sei il comitato di redazione di NutrizioniaMO 360, associazione scientifica di Modena che fa formazione per professionisti sanitari (biologi nutrizionisti, medici, dietisti) su nutrizione, microbiota, sport, longevità e prevenzione.
Ogni settimana scegli dalla letteratura recente gli studi più utili per un professionista. Criteri, in ordine:
1. solidità del disegno: meta-analisi e revisioni sistematiche di RCT, RCT ben dimensionati, grandi coorti prospettiche, linee guida e position stand;
2. rilevanza pratica per chi lavora con pazienti o sportivi;
3. qualità della rivista (le riviste preferite sono un segnale, non un requisito);
4. varietà: al massimo {max_per_tema} studi per tema, coprendo più temi possibile.
Escludi: studi pilota o con campioni molto piccoli, studi solo su animali o in vitro, protocolli, riviste predatorie, studi sponsorizzati con conclusioni promozionali, articoli il cui abstract non permette di capire i risultati.
Se i candidati validi sono meno di {n}, scegline meno: meglio 3 studi solidi che 5 deboli.
Rispondi SOLO con JSON: {{"scelti": [{{"pmid": "...", "tema": "<uno dei temi indicati>", "motivo": "<una frase>"}}]}}"""

SISTEMA_SINTESI = """Scrivi sintesi in italiano di studi scientifici per professionisti sanitari, per la rassegna settimanale di NutrizioniaMO 360.
Regole tassative:
- Usa SOLO le informazioni dell'abstract fornito. Non aggiungere nulla da conoscenze esterne.
- Riporta numeri, unità, effetti, intervalli di confidenza e valori p esattamente come nell'abstract, senza arrotondare o ricalcolare.
- Se un'informazione non c'è nell'abstract, scrivi "non riportato nell'abstract".
- Per studi osservazionali usa linguaggio di associazione ("è associato a"), mai causale.
- Non dare raccomandazioni cliniche, dosaggi o indicazioni ai pazienti: non è il tuo compito.
- Registro tecnico e asciutto, adatto a un professionista. Niente enfasi o aggettivi promozionali.
Rispondi SOLO con JSON: {"articoli": [ {
  "pmid": "...",
  "titolo_it": "traduzione fedele e chiara del titolo",
  "tipo_studio": "es. Meta-analisi di 18 RCT; RCT in doppio cieco; coorte prospettica",
  "popolazione": "chi e quanti",
  "obiettivo": "una frase",
  "risultati": ["2-4 punti, con i numeri dell'abstract"],
  "limiti": "limiti dichiarati o evidenti dal disegno; se nessuno è indicato scrivi 'non riportati nell'abstract'",
  "perche_selezionato": "una frase neutra su perché interessa a un professionista, senza raccomandazioni"
} ]}"""


def scheda_candidato(a, max_abstract=1800):
    ab = a["abstract"]
    if len(ab) > max_abstract:
        ab = ab[:max_abstract] + " […]"
    return (f'PMID {a["pmid"]} | temi: {", ".join(a["temi"])} | rivista: {a["rivista_abbr"] or a["rivista"]} | '
            f'tipo: {", ".join(a["tipi"])}\nTitolo: {a["titolo"]}\nAbstract: {ab}')


def numeri(testo):
    """Numeri del testo, normalizzati: virgola decimale -> punto, zeri finali tolti (0,50 = 0.5).
    Le migliaia scritte con separatore (1,234 / 1.234 / 1 234) vengono riunite."""
    testo = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", testo)
    trovati = set()
    for n in re.findall(r"\d+(?:[.,]\d+)?", testo):
        trovati.add(n.replace(",", "").replace(".", ""))  # lettura come migliaia
        n = n.replace(",", ".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        trovati.add(n)
    return trovati


def controlla_numeri(sintesi, abstract):
    """Numeri della sintesi che non compaiono nell'abstract: da far verificare a chi rivede."""
    presenti = numeri(abstract)
    testo = " ".join([sintesi.get("tipo_studio", ""), sintesi.get("popolazione", ""),
                      " ".join(sintesi.get("risultati", []))])
    dubbi = []
    for n in re.findall(r"\d+(?:[.,]\d+)?", re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", testo)):
        if not numeri(n) & presenti:
            dubbi.append(n)
    return sorted(set(dubbi))


# ---------------------------------------------------------------- principale

def lunedi_corrente():
    oggi = dt.datetime.now(ZoneInfo("Europe/Rome")).date()
    return oggi - dt.timedelta(days=oggi.weekday())


def main():
    solo_pubmed = "--solo-pubmed" in sys.argv
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    archivio = json.load(open(DATI, encoding="utf-8")) if os.path.exists(DATI) else {"numeri": []}
    settimana = lunedi_corrente().isoformat()
    gia_usciti = {a["pmid"] for n in archivio["numeri"] if n["settimana"] != settimana for a in n["articoli"]}

    print(f"Rassegna della settimana del {settimana}: ricerca su PubMed")
    cand = candidati(cfg, gia_usciti)
    print(f"Candidati con abstract utilizzabile: {len(cand)}")
    if solo_pubmed:
        for a in cand.values():
            print(f'  {a["pmid"]} | {a["rivista_abbr"]} | {a["data"]} | {", ".join(a["temi"])} | {a["titolo"][:110]}')
        return
    if not cand:
        print("Nessun candidato: questa settimana niente rassegna.")
        return

    # 1. selezione
    n = cfg["articoli_per_settimana"]
    elenco = "\n\n".join(scheda_candidato(a) for a in cand.values())
    msg = (f"Temi: {', '.join(t['nome'] for t in cfg['temi'])}\n"
           f"Riviste preferite: {', '.join(cfg['riviste_preferite'])}\n"
           f"Scegli fino a {n} studi tra questi {len(cand)} candidati:\n\n{elenco}")
    scelti = estrai_json(claude(cfg, SISTEMA_SELEZIONE.format(n=n, max_per_tema=cfg["max_per_tema"]), msg, 2000))["scelti"]
    scelti = [s for s in scelti if str(s.get("pmid")) in cand][:n]  # solo PMID realmente trovati su PubMed
    if not scelti:
        print("Claude non ha selezionato studi validi: niente rassegna questa settimana.")
        return
    print("Selezionati: " + ", ".join(str(s["pmid"]) for s in scelti))

    # 2. sintesi
    testi = "\n\n---\n\n".join(scheda_candidato(cand[str(s["pmid"])], max_abstract=6000) for s in scelti)
    sintesi = estrai_json(claude(cfg, SISTEMA_SINTESI, testi, 6000))["articoli"]
    per_pmid = {str(s["pmid"]): s for s in sintesi}

    articoli, avvisi = [], []
    for s in scelti:
        pmid = str(s["pmid"])
        a, x = cand[pmid], per_pmid.get(pmid)
        if not x:
            avvisi.append(f"PMID {pmid}: sintesi mancante, articolo escluso.")
            continue
        dubbi = controlla_numeri(x, a["abstract"])
        if dubbi:
            avvisi.append(f'PMID {pmid} ("{x.get("titolo_it", "")[:60]}…"): numeri non trovati nell\'abstract: {", ".join(dubbi)}')
        articoli.append({
            # dati bibliografici: da PubMed
            "pmid": pmid,
            "titolo_originale": a["titolo"],
            "rivista": a["rivista"],
            "rivista_abbr": a["rivista_abbr"],
            "data": a["data"],
            "doi": a["doi"],
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            # testi: da Claude, da rivedere
            "tema": s.get("tema") or (a["temi"][0] if a["temi"] else ""),
            "titolo_it": x.get("titolo_it", ""),
            "tipo_studio": x.get("tipo_studio", ""),
            "popolazione": x.get("popolazione", ""),
            "obiettivo": x.get("obiettivo", ""),
            "risultati": x.get("risultati", []),
            "limiti": x.get("limiti", ""),
            "perche_selezionato": x.get("perche_selezionato", ""),
            # facoltativo: commento firmato da chi rivede (se vuoto non compare sul sito)
            "nota_redazione": "",
        })

    numero = {"settimana": settimana, "articoli": articoli}
    archivio["numeri"] = [num for num in archivio["numeri"] if num["settimana"] != settimana]
    archivio["numeri"].insert(0, numero)
    archivio["aggiornato"] = dt.datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="minutes")
    with open(DATI, "w", encoding="utf-8") as f:
        json.dump(archivio, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Scritti {len(articoli)} articoli in sito/rassegna.json")

    if os.environ.get("PR_BODY"):
        righe = [f"## Rassegna scientifica della settimana del {settimana}", "",
                 "Controlla l'**anteprima del sito** (link nel commento di Netlify qui sotto). "
                 "Se va bene, clicca **Merge pull request**: la rassegna va online. "
                 "Se va corretta, rispondi qui con le correzioni o modifica `sito/rassegna.json`.", "",
                 "### Studi selezionati"]
        for a in articoli:
            righe.append(f'- **{a["titolo_it"]}** — {a["rivista_abbr"] or a["rivista"]}, {a["data"]} · {a["tipo_studio"]} · [PubMed]({a["link"]})')
        righe += ["", "### Da verificare"]
        righe += [f"- {v}" for v in avvisi] or ["- Nessun numero sospetto: tutti i valori delle sintesi compaiono negli abstract."]
        righe += ["", "_Sintesi preparate da Claude a partire dagli abstract di PubMed. Prima di pubblicare, confrontale con l'abstract originale._"]
        with open(os.environ["PR_BODY"], "w", encoding="utf-8") as f:
            f.write("\n".join(righe) + "\n")


if __name__ == "__main__":
    main()
