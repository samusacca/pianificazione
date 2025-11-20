import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np
import io

st.set_page_config(page_title="Pianificazione Produzione", layout="wide")

st.title("📅 Pianificazione Produzione - Gantt Interattivo")

st.sidebar.header("⚙️ Impostazioni")
file_path = st.sidebar.file_uploader("Carica file Excel con i dati di produzione", type=["xlsx"])

# --- Parametri orari ---
ORE_GIORNALIERE = 9
INIZIO_GIORNO = time(8, 0)
FINE_GIORNO = (datetime.combine(datetime.today(), INIZIO_GIORNO) + timedelta(hours=ORE_GIORNALIERE)).time()

# --- Gruppi macchine che non possono lavorare insieme ---
gruppi_macchine = [
    {"nome": "GruppoGornatiPontiggia", "macchine": ["Gornati", "Pontiggia"]},
]

# --- Priorità operazioni per ordinamento ---
ORDINE_OPERAZIONI = {
    "tornitura": 1,
    "fresatura": 2,
    "foratura": 2,
}

def prossima_data_lavoro(dt):
    """Restituisce la prossima data utile saltando i weekend."""
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt

def aggiungi_ore_lavoro(start_time, ore):
    """Aggiunge ore lavorative rispettando orario e weekend."""
    current = start_time
    ore_restanti = ore
    while ore_restanti > 0:
        current = prossima_data_lavoro(current)
        fine_giorno = datetime.combine(current.date(), FINE_GIORNO)
        tempo_disponibile = (fine_giorno - current).total_seconds() / 3600

        if ore_restanti <= tempo_disponibile:
            current += timedelta(hours=ore_restanti)
            ore_restanti = 0
        else:
            ore_restanti -= tempo_disponibile
            current = datetime.combine(current.date() + timedelta(days=1), INIZIO_GIORNO)
    return current

def get_ordine_operazione(operazione):
    """Restituisce l'ordine di priorità dell'operazione (1=prima, valori più alti=dopo)."""
    if pd.isna(operazione):
        return 999
    operazione_lower = str(operazione).lower().strip()
    for key, value in ORDINE_OPERAZIONI.items():
        if key in operazione_lower:
            return value
    return 10  # Operazioni non specificate vengono dopo tornitura ma prima delle sconosciute

if file_path:
    df = pd.read_excel(file_path)

    # --- Gestione colonne Dipendenza e Priorità ---
    if "Dipendenza" not in df.columns:
        df["Dipendenza"] = ""
    df["Dipendenza"] = df["Dipendenza"].fillna("").astype(str)
    
    if "Priorità" not in df.columns:
        df["Priorità"] = 5  # Priorità media di default
    df["Priorità"] = pd.to_numeric(df["Priorità"], errors="coerce").fillna(5)

    # --- Conversione colonne tempo ---
    for col in ["Tempo unitario (h)", "Setup (h)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["Quantità"] = pd.to_numeric(df["Quantità"], errors="coerce").fillna(1)
    df["Data richiesta"] = pd.to_datetime(df["Data richiesta"], errors="coerce")

    # --- Aggiunta colonna per ordinamento operazioni ---
    df["_ordine_operazione"] = df["Operazione"].apply(get_ordine_operazione)

    # --- Ordinamento del DataFrame ---
    # Prima per priorità (più bassa = più urgente), poi per codice pezzo, poi per tipo operazione
    df = df.sort_values(
        by=["Priorità", "Codice pezzo", "_ordine_operazione"],
        ascending=[True, True, True]
    ).reset_index(drop=True)

    st.subheader("📋 Dati di produzione ordinati")
    st.caption("Le operazioni sono ordinate per: Priorità → Codice pezzo → Tipo operazione (tornitura → fresatura/foratura)")
    
    # Mostra il dataframe senza la colonna temporanea di ordinamento
    df_display = df.drop(columns=["_ordine_operazione"])
    st.dataframe(df_display)

    st.subheader("📊 Generazione automatica del Gantt")

    pianificazione = []
    disponibilita = {}

    # Inizializza disponibilità macchine
    for macchina in df["Macchina"].unique():
        disponibilita[macchina] = datetime.combine(datetime.today(), INIZIO_GIORNO)

    for _, row in df.iterrows():
        codice = row["Codice pezzo"]
        macchina = row["Macchina"]
        tempo = row["Tempo unitario (h)"] * row["Quantità"] + row["Setup (h)"]
        dip = row["Dipendenza"].strip()
        priorita = row["Priorità"]

        # Gestione gruppi (Gornati-Pontiggia)
        gruppo_macchina = next((g for g in gruppi_macchine if macchina in g["macchine"]), None)
        if gruppo_macchina:
            disponibilita_macchina = min(disponibilita[m] for m in gruppo_macchina["macchine"])
        else:
            disponibilita_macchina = disponibilita[macchina]

        start_time = prossima_data_lavoro(disponibilita_macchina)

        # Gestione dipendenze
        if dip:
            task_dip = next((t for t in pianificazione if t["Codice pezzo"] == dip), None)
            if task_dip:
                start_time = max(start_time, task_dip["Fine"])

        end_time = aggiungi_ore_lavoro(start_time, tempo)

        # Aggiorna disponibilità
        if gruppo_macchina:
            for m in gruppo_macchina["macchine"]:
                disponibilita[m] = end_time
        else:
            disponibilita[macchina] = end_time

        pianificazione.append({
            "Commessa": row["Commessa"],
            "Codice pezzo": codice,
            "Operazione": row["Operazione"],
            "Macchina": macchina,
            "Priorità": priorita,
            "Inizio": start_time,
            "Fine": end_time
        })

    gantt_df = pd.DataFrame(pianificazione)

    st.subheader("📈 Gantt interattivo")
    st.caption("Puoi modificare manualmente le date nelle celle qui sotto, poi aggiornare il grafico.")

    # Permette di editare le date
    gantt_df_edit = st.data_editor(
        gantt_df,
        column_config={
            "Inizio": st.column_config.DatetimeColumn("Inizio"),
            "Fine": st.column_config.DatetimeColumn("Fine"),
            "Priorità": st.column_config.NumberColumn("Priorità", help="1=massima urgenza, valori più alti=meno urgente"),
        },
        num_rows="dynamic",
        use_container_width=True
    )

    # Disegno Gantt aggiornato
    fig = px.timeline(
        gantt_df_edit,
        x_start="Inizio",
        x_end="Fine",
        y="Macchina",
        color="Codice pezzo",
        text="Codice pezzo",
        hover_data=["Commessa", "Operazione", "Priorità"],
        title="📆 Gantt di Produzione (Aggiornato)"
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_traces(textposition='inside', textfont_size=10)
    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="Macchina",
        hovermode="closest",
        height=700,
        xaxis=dict(showgrid=True, tickformat="%d-%m %H:%M"),
    )

    # Evidenzia weekend
    min_date = gantt_df_edit["Inizio"].min().date()
    max_date = gantt_df_edit["Fine"].max().date()
    giorno = min_date
    while giorno <= max_date:
        if giorno.weekday() >= 5:
            fig.add_vrect(
                x0=giorno,
                x1=giorno + timedelta(days=1),
                fillcolor="lightgray",
                opacity=0.3,
                line_width=0,
            )
        giorno += timedelta(days=1)

    st.plotly_chart(fig, use_container_width=True)

    # --- Statistiche di riepilogo ---
    st.subheader("📊 Statistiche di pianificazione")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Operazioni totali", len(gantt_df_edit))
    with col2:
        durata_totale = (gantt_df_edit["Fine"].max() - gantt_df_edit["Inizio"].min()).days
        st.metric("Durata pianificazione (giorni)", durata_totale)
    with col3:
        st.metric("Macchine coinvolte", gantt_df_edit["Macchina"].nunique())

    # Esportazione Excel aggiornata
    output = io.BytesIO()
    gantt_df_edit.to_excel(output, index=False, engine="openpyxl")
    st.download_button(
        label="💾 Scarica pianificazione aggiornata (Excel)",
        data=output.getvalue(),
        file_name="pianificazione_aggiornata.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("📂 Carica un file Excel per visualizzare il Gantt.")
    st.markdown("""
    Il file deve contenere almeno queste colonne:
    - **Commessa**
    - **Codice pezzo**
    - **Operazione**
    - **Macchina**
    - **Quantità**
    - **Tempo unitario (h)**
    - **Setup (h)**
    - **Data richiesta**
    - **Dipendenza** (può essere vuota)
    - **Priorità** (opzionale, valore numerico: 1=massima urgenza, valori più alti=meno urgente)
    
    ### Note sull'ordinamento:
    - Le operazioni vengono ordinate prima per **priorità** (valori più bassi = più urgenti)
    - A parità di priorità, per **codice pezzo**
    - Per lo stesso codice pezzo: **tornitura** → **fresatura/foratura** → altre operazioni
    """)