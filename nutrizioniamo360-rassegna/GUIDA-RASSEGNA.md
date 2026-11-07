# Rassegna scientifica settimanale · NutrizioniaMO 360

Ogni lunedì mattina un programma cerca su PubMed gli studi recenti sui temi dell'associazione. Claude sceglie i migliori (fino a 5) e ne scrive una sintesi in italiano basata solo sull'abstract. La bozza **non va online da sola**: arriva a Chiara come richiesta di revisione, con l'anteprima del sito. Va online solo quando lei la approva.

## Cosa c'è in questa cartella

| Percorso | Cosa contiene |
|---|---|
| `sito/` | Il sito completo, con la nuova pagina **Rassegna** nel menu. È l'unica cartella che Netlify pubblica. |
| `sito/rassegna.json` | I numeri della rassegna (all'inizio è vuoto). Lo aggiorna il programma. |
| `strumenti/rassegna.py` | Il programma settimanale. |
| `strumenti/rassegna_config.json` | Temi, ricerche PubMed, numero di studi, riviste preferite, modello di Claude. |
| `.github/workflows/rassegna.yml` | L'automazione che fa partire il programma ogni lunedì (circa alle 6:15 d'inverno e alle 7:15 d'estate) e apre la richiesta di revisione. |
| `netlify.toml` | Dice a Netlify di pubblicare solo la cartella `sito`. |

---

## Configurazione iniziale (da fare una volta, circa 30 minuti)

### 1. Metti il sito su GitHub
1. Crea un account su github.com, se non ce l'hai.
2. In alto a destra clicca **+ → New repository**. Come nome usa `nutrizioniamo360-sito`, scegli **Private** e clicca **Create repository**.
3. Nella pagina del repository vuoto clicca **uploading an existing file**. Trascina **tutto il contenuto** di questa cartella: `sito`, `strumenti`, `.github`, `netlify.toml` e questa guida. Poi clicca **Commit changes**.
4. Controlla che esista il file `.github/workflows/rassegna.yml`, perché alcuni sistemi nascondono le cartelle che iniziano con il punto. Se manca, crealo con **Add file → Create new file**: scrivi il percorso `.github/workflows/rassegna.yml` e incolla il contenuto del file.

### 2. Collega Netlify a GitHub
- **Se il sito è già su Netlify** (caricato con lo zip): apri il sito su Netlify, vai su **Site configuration → Build & deploy → Continuous deployment → Link repository**, scegli GitHub e poi `nutrizioniamo360-sito`. Il dominio resta lo stesso.
- **Se non è ancora su Netlify**: clicca **Add new site → Import an existing project → GitHub → nutrizioniamo360-sito**.

In entrambi i casi Netlify legge `netlify.toml` e pubblica la cartella `sito`, quindi non devi impostare altro. Le anteprime delle richieste di revisione (*Deploy Previews*) sono attive di default.

> Da qui in poi il sito non si aggiorna più trascinando lo zip su Netlify. Ogni modifica passa da GitHub, e Netlify ripubblica da solo.

### 3. Prepara le chiavi
- **Chiave API di Claude**: entra su platform.claude.com e vai su **API keys → Create key**. In **Billing** carica un piccolo credito. Ti consiglio di impostare anche un limite di spesa mensile, per esempio 5 $.
- **Chiave NCBI** (gratuita, consigliata): accedi su ncbi.nlm.nih.gov, poi **Account settings → API Key Management → Create an API Key**.

### 4. Inserisci chiavi e impostazioni in GitHub
Nel repository vai su **Settings → Secrets and variables → Actions**.

Scheda **Secrets** → **New repository secret**:
- `ANTHROPIC_API_KEY` = la chiave di Claude
- `NCBI_API_KEY` = la chiave NCBI

Scheda **Variables** → **New repository variable**:
- `NCBI_EMAIL` = `nutrizioniamo360@gmail.com` (NCBI la usa solo per contattarvi in caso di problemi)
- `REVISORE` = il nome utente GitHub di Chiara

### 5. Dai i permessi all'automazione
**Settings → Actions → General → Workflow permissions**: seleziona **Read and write permissions** e spunta **Allow GitHub Actions to create and approve pull requests**. Poi clicca **Save**.

### 6. Aggiungi Chiara
Chiara crea un account GitHub gratuito. Tu la inviti da **Settings → Collaborators → Add people**. Da quel momento le arriva un'email ogni volta che c'è una rassegna da approvare.

---

## Prima prova

1. Vai su **Actions → Rassegna scientifica → Run workflow**, spunta **Solo prova PubMed** e clicca **Run workflow**. Questa prova non usa Claude e non costa nulla.
2. Apri l'esecuzione e leggi il risultato. Per ogni tema vedi quanti studi ha trovato PubMed negli ultimi 14 giorni, e poi l'elenco dei candidati.
   - Se un tema trova **0 risultati** o candidati fuori tema, va corretta la sua ricerca in `strumenti/rassegna_config.json`. Mandami il risultato e la sistemo io.
3. Quando l'elenco convince, rilancia **Run workflow** senza spunta. In un paio di minuti si apre la prima richiesta di revisione, esattamente come succederà ogni lunedì.

---

## Ogni lunedì: cosa fa Chiara (circa 10 minuti)

1. Riceve l'email *"review requested"* e la apre.
2. Nella pagina trova l'elenco degli studi scelti e la sezione **Da verificare**. Lì il programma segnala i numeri delle sintesi che non trova nell'abstract.
3. Clicca il link **Deploy Preview** di Netlify (nei commenti) e va alla pagina **Rassegna**. Vede la pagina esattamente come andrà online.
4. Per ogni studio confronta la sintesi con l'abstract, usando il link "Leggi l'abstract su PubMed".
5. A questo punto:
   - **va tutto bene**: clicca **Merge pull request → Confirm merge**. In un minuto la rassegna è online;
   - **c'è da correggere**: scrive le correzioni come commento nella richiesta, oppure modifica direttamente `sito/rassegna.json` (scheda **Files changed**, poi i tre puntini e **Edit file**);
   - **vuole aggiungere un commento firmato**: compila il campo `"nota_redazione"` dello studio. Sul sito compare come "Il commento di NutrizioniaMO". Se resta vuoto, non compare;
   - **non vuole pubblicare questa settimana**: clicca **Close pull request**.

Se la richiesta di una settimana resta aperta, il lunedì dopo ne arriva una nuova. Quella vecchia può essere chiusa.

---

## Come è fatto

- **Ricerca**: per ogni tema una query PubMed limitata agli ultimi 14 giorni e a studi su esseri umani con abstract. I disegni ammessi sono meta-analisi, revisioni sistematiche, RCT, coorti prospettiche, linee guida e position stand. Il filtro è per data di inserimento in PubMed, così non si perdono gli articoli appena usciti e non ancora indicizzati. Gli studi già usciti in un numero precedente vengono scartati.
- **Fonte di riserva**: dai server di GitHub PubMed spesso non risponde. In quel caso il programma usa da solo Europe PMC, che contiene gli stessi articoli con lo stesso PMID e restituisce anche gli abstract. Nel registro dell'esecuzione la riga "Fonte di questa settimana" dice quale è stata usata.
- **Selezione**: Claude sceglie privilegiando disegno solido, rilevanza pratica e qualità della rivista, con al massimo 2 studi per tema. Esclude studi pilota, studi su animali e riviste predatorie. Se non trova almeno 5 studi validi, ne pubblica meno.
- **Sintesi**: solo dall'abstract, con i numeri riportati tali e quali e linguaggio di associazione per gli studi osservazionali. Niente raccomandazioni cliniche.
- **Dati bibliografici** (titolo originale, rivista, data, DOI, link): presi sempre da PubMed, mai scritti dall'AI. Se Claude indica uno studio che non è tra quelli trovati, viene scartato.
- **Controllo dei numeri**: ogni numero delle sintesi viene cercato nell'abstract. Quelli che non compaiono finiscono in "Da verificare".

## Modifiche comuni (in `strumenti/rassegna_config.json`)
- `articoli_per_settimana`: quanti studi per numero (oggi 5)
- `max_per_tema`: massimo di studi per tema (oggi 2)
- `giorni_finestra`: quanti giorni indietro cercare (oggi 14)
- `temi`: aggiungere, togliere o rinominare temi e ricerche
- `riviste_preferite`: riviste da privilegiare
- `modello`: il modello di Claude (oggi Sonnet 5.5)

## Costi
- **Claude**: circa 0,15-0,25 $ a settimana, cioè circa 1 $ al mese.
- **GitHub Actions**: gratis. Ogni esecuzione dura 1-2 minuti, contro i 2.000 minuti al mese gratuiti dei repository privati.
- **PubMed e Netlify**: gratis.
