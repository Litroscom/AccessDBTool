# AccessDBTool v5

Base di lavoro creata a partire da `AccessDBTool_v4.0`.

Obiettivi iniziali richiesti:

- Collegare ogni gruppo di condizioni a un database specifico.
- Gestire piu gruppi di condizioni e database contemporaneamente.

Ipotesi iniziale usata per la preparazione:

- La v5 nasce come ramo di lavoro separato dalla v4.
- Gli artefatti generati (`build`, `dist`, `__pycache__`, `app.log`) non sono stati copiati.
- I file JSON correnti sono stati copiati come base dati di partenza.

Temi da chiarire prima dell'implementazione:

- Se un "gruppo" deve puntare a un solo database fisso o a una lista di database compatibili.
- Se i gruppi devono poter essere eseguiti in parallelo oppure basta una gestione multi-sessione nella UI.
- Se il path del database va salvato assoluto, relativo, o tramite alias/connessione nominata.
- Se il monitor deve diventare multi-database oppure restare limitato a un contesto attivo per volta.
