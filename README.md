F1 Telemetry - IoT project

---

Stato attuale del progetto:

Il progetto implementa una pipeline IoT completa per la simulazione e visualizzazione della telemetria di vetture di Formula 1.

Attualmente sono state implementate e integrate le seguenti componenti:

- simulazione della produzione dei dati telemetrici tramite un producer Python
- trasmissione dei dati tramite protocollo MQTT
- broker MQTT (Mosquitto) per la gestione del flusso publish/subscribe
- ingestione e parsing dei dati con Telegraf
- persistenza dei dati su InfluxDB (time-series-database)
- visualizzazione real-time della posizione delle vetture su mappa tramite Web Client

La parte relativa alle dashboard Grafana è in fase di reintegrazione.


---

Architettura della pipeline:

    Producer (Python)
            ↓ MQTT
    Mosquitto (Broker)
            ↓       ↘
    Telegraf        Track Web Client (real-time map via WebSocket)
            ↓
    InfluxDB

            
             

---

Setup del sistema:

1.  Avvia tutti i servizi:

        $docker-compose up -d

Questo comando avvia:
- Mosquitto         (broker MQTT)
- Telegraf          (ingestione dati)
- InfluxDB          (storage)
- Track Web Client  (server web per la mappa)
    
2.  Avvia il producer:

        $docker-compose run --rm producer
    
    È possibile configurare la velocità di replay dei dati:

        $docker-compose run --rm -e REPLAY_SPEEDUP=5 producer


3.  Visualizzazione della mappa:

    La mappa è accessibile all'indirizzo:

        http://localhost:8080

    Il servizio è eseguito all'interno di un container Docker (nginx).
    Funzionalità principali:

    - visualizzazione della posizione delle vetture in tempo reale
    - tracciamento della traiettoria
    - gestione simultanea di più piloti (di default 2)

---


Flusso dei dati:

1.  Il producer legge dati telemetrici storici (API OpenF1 o cache locale)
2.  Simula un flusso real-time tramite replay temporale
3.  Pubblica i dati su MQTT in formato JSON
4.  Mosquitto inoltra i messaggi ai subscriber
5.  Telegraf consuma e scrive i dati su InfluxDB
6.  Il Track Client si sottoscrive direttamente a MQTT e aggiorna la visualizzazione


---


Gestione della cache:

I dati vengono:

- scaricati dall'API alla prima esecuzione
- salvati localmente nella directory producer/cache
- riutilizzati nelle esecuzioni successive

Questo evita chiamate ripetute all'API.


---


Limitazioni attuali:

- i dati non sono live ma simulati tramite replay
- il volume e la frequenza dei dati sono inferiori rispetto ad un sistema reale
- non è simulata la latenza di rete o la perdita di pacchetti
- le dashboard Grafana non sono ancora integrate


---


Prossimi sviluppi:

-   reintegrazione delle dashboard Grafana
-   selezione dinamica di:
    - anno
    - circuito
    - sessione
    - piloti
-   calcolo e display grafico di metriche derivate (tempi sul giro, settori, etc)
-   containerizzazione completa di tutti i servizi