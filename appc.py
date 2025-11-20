import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np
import io
import requests

st.set_page_config(page_title="Pianificazione Produzione", layout="wide")

st.title("📅 Pianificazione Produzione - Gantt Interattivo")

st.sidebar.header("⚙️ Impostazioni")

# --- Caricamento ID Google Drive dai secrets ---
try:
    gdrive_file_id_default = st.secrets.get("GDRIVE_FILE_ID", "")
except:
    gdrive_file_id_default = ""

# --- Opzioni di caricamento file ---
caricamento_tipo = st.sidebar.radio(
    "Modalità caricamento dati:",
    ["☁️ Google Drive (auto-aggiornamento)", "📤 Carica file manualmente"]
)

file_data = None

if caricamento_tipo == "☁️ Google Drive (auto-aggiornamento)":
    st.sidebar.markdown("### Configurazione Google Drive")
    
    if gdrive_file_id_default:
        st.sidebar.success("✅ ID Google Drive configurato!")
        usa_id_salvato = st.sidebar.checkbox("Usa ID salvato", value=True)
    else:
        usa_id_salvato = False
        st.sidebar.info("💡 Configura l'ID nei Secrets per non doverlo inserire ogni volta")
    
    if usa_id_salvato and gdrive_file_id_default:
        gdrive_file_id = gdrive_file_id_default
        st.sidebar.text_input(
            "ID file Google Drive (salvato):",
            value=gdrive_file_id[:20] + "..." if len(gdrive_file_id) > 20 else gdrive_file_id,
            disabled=True
        )
    else:
        st.sidebar.markdown("""
        **Come ottenere il link:**
        1. Apri il file Excel in Google Drive
        2. Clicca "Condividi" → "Chiunque abbia il link"
        3. Copia l'ID del file dall'URL
        
        Esempio URL: `https://drive.google.com/file/d/ABC123XYZ/view`
        
        L'ID è: `ABC123XYZ`
        """)
        
        gdrive_file_id = st.sidebar.text_input(
            "ID file Google Drive:",
            value=gdrive_file_id_default,
            placeholder="Incolla qui l'ID del file"
        )
    
    auto_refresh = st.sidebar.checkbox("🔄 Auto-aggiornamento ogni 5 minuti", value=False)
    
    if auto_refresh:
        st.sidebar.info("La pagina si aggiornerà automaticamente")
        st_autorefresh = st.sidebar.empty()
        st_autorefresh.markdown(
            '<meta http-equiv="refresh" content="300">',
            unsafe_allow_html=True
        )
    
    if gdrive_file_id:
        try:
            with st.spinner("⏳ Caricamento da Google Drive..."):
                download_url = f"https://drive.google.com/uc?export=download&id={gdrive_file_id}"
                response = requests.get(download_url)
                
                if response.status_code == 200:
                    file_data = io.BytesIO(response.content)
                    st.sidebar.success("✅ File caricato da Google Drive")
                    st.sidebar.caption(f"Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                else:
                    st.sidebar.error("❌ Errore nel caricamento. Verifica che il file sia condiviso pubblicamente.")
        except Exception as e:
            st.sidebar.error(f"❌ Errore: {str(e)}")

else:
    file_path = st.sidebar.file_uploader("Carica file Excel", type=["xlsx"])
    if file_path:
        file_data = file_path

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
    return 10

if file_data:
    df = pd.read_excel(file_data)

    # --- Gestione colonne Dipendenza e Priorità ---
    if "Dipendenza" not in df.columns:
        df["Dipendenza"] = ""
    df["Dipendenza"] = df["Dipendenza"].fillna("").astype(str)
    
    if "Priorità" not in df.columns:
        df["Priorità"] = 5
    df["Priorità"] = pd.to_numeric(df["Priorità"], errors="coerce").fillna(5)

    # --- Conversione colonne tempo ---
    for col in ["Tempo unitario (h)", "Setup (h)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["Quantità"] = pd.to_numeric(df["Quantità"], errors="coerce").fillna(1)
    df["Data richiesta"] = pd.to_datetime(df["Data richiesta"], errors="coerce")

    # --- Aggiunta colonna per ordinamento operazioni ---
    df["_ordine_operazione"] = df["Operazione"].apply(get_ordine_operazione)

    # --- Ordinamento del DataFrame ---
    df = df.sort_values(
        by=["Priorità", "Codice pezzo", "_ordine_operazione"],
        ascending=[True, True, True]
    ).reset_index(drop=True)

    st.subheader("📋 Dati di produzione ordinati")
    st.caption("Le operazioni sono ordinate per: Priorità → Codice pezzo → Tipo operazione (tornitura → fresatura/foratura)")
    
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
    st.info("📂 Seleziona una modalità di caricamento nella barra laterale")
    
    if not gdrive_file_id_default and caricamento_tipo == "☁️ Google Drive (auto-aggiornamento)":
        st.warning("⚠️ ID Google Drive non configurato. Segui le istruzioni qui sotto:")
        
        st.markdown("""
        ## 🔧 Come configurare l'ID Google Drive permanentemente
        
        ### Su Streamlit Cloud:
        1. Vai sulla tua app su [share.streamlit.io](https://share.streamlit.io)
        2. Clicca sui **tre puntini** ⋮ accanto alla tua app
        3. Seleziona **"Settings"**
        4. Vai sulla sezione **"Secrets"**
        5. Incolla questo codice (sostituisci con il TUO ID):
        
        ```toml
        GDRIVE_FILE_ID = "il-tuo-id-google-drive-qui"
        ```
        
        6. Clicca **"Save"**
        7. L'app si riavvierà automaticamente
        
        ### In locale (sul tuo PC):
        1. Crea una cartella `.streamlit` nella stessa cartella di `app.py`
        2. Dentro `.streamlit`, crea un file chiamato `secrets.toml`
        3. Scrivi dentro:
        
        ```toml
        GDRIVE_FILE_ID = "il-tuo-id-google-drive-qui"
        ```
        
        4. Salva e riavvia l'app
        """)
    
    st.markdown("""
    ---
    
    Il file Excel deve contenere queste colonne:
    - **Commessa**
    - **Codice pezzo**
    - **Operazione**
    - **Macchina**
    - **Quantità**
    - **Tempo unitario (h)**
    - **Setup (h)**
    - **Data richiesta**
    - **Dipendenza** (opzionale)
    - **Priorità** (opzionale, 1=massima urgenza)
    """)
