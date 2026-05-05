import pandas as pd
import streamlit as st
import uuid
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta
from streamlit_gsheets import GSheetsConnection

#----------   Configuration Constants   ----------

Amount_per_cycle = 14.00  # Importo base per 1 quadrimestre
Currency = "€"
PAYMENT_METHODS = ["Contanti", "Satispay", "Bonifico", "PayPal"]
CICLI_SCELTA = {
    "1 Quadrimestre (14€)": 1,
    "2 Quadrimestri (28€)": 2,
    "1 Anno Intero (42€)": 3
}

#------ Page Setup ----------

st.set_page_config( page_title="Spotify Manager", page_icon = "🎧", layout="wide" )

# --- SISTEMA DI LOGIN PERSONALIZZATO ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.info("🔒 Inserisci la password per accedere al Manager")
    pwd = st.text_input("Password", type="password")
    if st.button("Entra"):
        if pwd == st.secrets["app_password"]:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("❌ Password errata!")
    st.stop() # Ferma l'app qui se non sei loggato!
# ---------------------------------------

st.title("🎧 Spotify Family Manager")

#------ Database Connection  Gsheets ----------
conn = st.connection("gsheets", type=GSheetsConnection)

#------ Backend Functions    ----------

def calcola_saldo(due_date_str):
    """Calcola il saldo scalare in base a quanto tempo manca alla scadenza"""
    try:
        due_date = datetime.strptime(str(due_date_str), "%Y-%m-%d").date()
        oggi = datetime.now().date()
        delta_days = (due_date - oggi).days
        
        if delta_days < 0:
            # È in ritardo: saldo negativo
            mesi_ritardo = abs(delta_days) / 30.416
            cicli_ritardo = math.ceil(mesi_ritardo / 4)
            if cicli_ritardo == 0: 
                cicli_ritardo = 1 # Se è scaduto anche da un giorno, è -14
            return -(cicli_ritardo * 14)
        else:
            # È in anticipo o in pari: saldo scalare
            mesi_anticipo = delta_days / 30.416
            # La formula abbassa il saldo di 14€ esatti a metà quadrimestre (2 mesi prima)
            saldo = math.floor((mesi_anticipo + 2) / 4) * 14
            return saldo
    except:
        return 0

def get_data():
    """Download updated data from Google Sheets"""
    try:
        df_users = conn.read(worksheet="users", ttl=0)
        df_payments = conn.read(worksheet="payments", ttl=0)

        df_users = df_users.dropna(how="all")
        df_payments = df_payments.dropna(how="all")

        if not df_users.empty:
            df_users["user_id"] = df_users["user_id"].astype(str)
        if not df_payments.empty:
            df_payments["user_id"] = df_payments["user_id"].astype(str)
            df_payments["payment_id"] = df_payments["payment_id"].astype(str)
            
            if "payment_method" not in df_payments.columns:
                df_payments["payment_method"] = ""

        if not df_users.empty and not df_payments.empty:
            mappa_nomi = dict(zip(df_users['user_id'], df_users['name']))
            df_payments['nome_utente'] = df_payments['user_id'].map(mappa_nomi)
            
            cols = df_payments.columns.tolist()
            if 'nome_utente' in cols:
                cols.insert(2, cols.pop(cols.index('nome_utente')))
                df_payments = df_payments[cols]

        return df_users, df_payments
    except Exception as e:
        st.error(f"Error loading data from Google Sheets: {e}")
        st.stop()
    
def create_user(name):
    """Create a new user entry"""
    df_users, df_payments = get_data()
    user_id = str(uuid.uuid4())[:8]
    
    new_user = pd.DataFrame([{
        "user_id": user_id,
        "name": name,
        "active": True,
        "created_at": datetime.now().strftime("%Y-%m-%d")
    }])

    new_payment = pd.DataFrame([{
        "payment_id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "nome_utente": name,
        "amount": Amount_per_cycle,
        "due_date": datetime.now().strftime("%Y-%m-%d"), 
        "status": "PENDING",
        "paid_date": None,
        "payment_method": "" 
    }])

    updated_users = pd.concat([df_users, new_user], ignore_index=True)
    conn.update(worksheet="users", data=updated_users)
    updated_payments = pd.concat([df_payments, new_payment], ignore_index=True)
    conn.update(worksheet="payments", data=updated_payments)
    st.cache_data.clear()

def process_payment(payment_id, method, cicli_pagati):
    """Close the current payment and create the future one based on cycles paid."""
    df_users, df_payments = get_data()
    
    idx_list = df_payments.index[df_payments['payment_id'] == payment_id].tolist()
    if not idx_list: return
    row_idx = idx_list[0]
    current_row = df_payments.iloc[row_idx]

    # Segna il pagamento attuale come pagato
    df_payments.at[row_idx, "status"] = "PAID"
    df_payments.at[row_idx, "paid_date"] = datetime.now().strftime("%Y-%m-%d")
    df_payments.at[row_idx, "payment_method"] = method
    df_payments.at[row_idx, "amount"] = cicli_pagati * Amount_per_cycle # Registra il vero incasso!

    try:
        current_due = datetime.strptime(str(current_row["due_date"]), "%Y-%m-%d")
    except:
        current_due = datetime.now()
    
    # Sposta la data in avanti in base a QUANTI quadrimestri ha pagato
    mesi_da_aggiungere = 4 * cicli_pagati
    next_due = current_due + relativedelta(months=+mesi_da_aggiungere)
    nome = current_row["nome_utente"] if "nome_utente" in current_row else "Sconosciuto"

    # Crea la nuova scadenza futura
    new_payment = pd.DataFrame([{
        "payment_id": str(uuid.uuid4())[:8],
        "user_id": current_row["user_id"],
        "nome_utente": nome,
        "amount": Amount_per_cycle, # La rata base resta fissa a 14 per il futuro
        "due_date": next_due.strftime("%Y-%m-%d"),
        "status": "PENDING",
        "paid_date": None,
        "payment_method": "" 
    }])

    updated_payments = pd.concat([df_payments, new_payment], ignore_index=True)
    conn.update(worksheet="payments", data=updated_payments)
    st.cache_data.clear()

#------ Frontend Interface    ----------

with st.sidebar:
    st.header("Management")
    with st.form("new_user_form", clear_on_submit=True):
        name_input = st.text_input("New Participant")
        submitted = st.form_submit_button("Add User")
        if submitted and name_input:
            with st.spinner("Creating user..."):
                create_user(name_input)
            st.success("User created!")
            st.rerun()

try:    
    df_users, df_payments = get_data()
except:
    st.stop()

if not df_payments.empty and not df_users.empty:
    full_df = pd.merge(df_payments, df_users[['user_id', 'active']], on="user_id", how="left")
    full_df = full_df[full_df['active'] == True]
    full_df = full_df.sort_values(by="due_date")

    # --- DASHBOARD RIASSUNTIVA PORTAFOGLIO ---
    st.markdown("### 📊 Portafoglio Saldi")
    
    pending_status = full_df[full_df['status'] == 'PENDING']
    da_pagare = []
    in_regola = []
    
    for _, row in pending_status.iterrows():
        saldo = calcola_saldo(row['due_date'])
        nome = row['nome_utente']
        
        if saldo < 0:
            da_pagare.append(f"• {nome}: **{saldo}€**")
        elif saldo == 0:
            in_regola.append(f"• {nome}: **0€** ⚠️ *(in scadenza)*")
        else:
            in_regola.append(f"• {nome}: **+{saldo}€**")
    
    col_red, col_green = st.columns(2)
    with col_red:
        testo_rossi = "\n".join(da_pagare) if da_pagare else "Nessuno 🎉"
        st.error(f"🔴 **IN RITARDO (Sotto Zero)**\n\n{testo_rossi}")
        
    with col_green:
        testo_verdi = "\n".join(in_regola) if in_regola else "Nessuno"
        st.success(f"🟢 **IN REGOLA**\n\n{testo_verdi}")
        
    st.divider()
    # -----------------------------------------

    tab1, tab2 = st.tabs(["💳 Gestione Incassi", "🟢 Storico Pagamenti"])
    
    with tab1:
        pending = full_df[full_df['status'] == 'PENDING']
        
        if pending.empty:
            st.info("Tutto perfetto! Nessuna azione richiesta.")
        
        for i, row in pending.iterrows():
            with st.container(border=True):
                # Sistemazione layout per accogliere due tendine
                c1, c2, c3, c4, c5 = st.columns([3, 2, 3, 2, 2])
                
                # NOME E SALDO
                saldo_attuale = calcola_saldo(row['due_date'])
                colore_saldo = "red" if saldo_attuale < 0 else ("orange" if saldo_attuale == 0 else "green")
                segno = "+" if saldo_attuale > 0 else ""
                
                c1.markdown(f"### {row['nome_utente']}")
                c1.markdown(f"Saldo: **:{colore_saldo}[{segno}{saldo_attuale} €]**")
                
                # SCADENZA
                try:
                    due_date_obj = datetime.strptime(str(row['due_date']), "%Y-%m-%d").date()
                    if due_date_obj < datetime.now().date():
                        c2.markdown(f"Coperto fino al:\n### :red[{row['due_date']}]")
                    else:
                        c2.markdown(f"Coperto fino al:\n### {row['due_date']}")
                except:
                    c2.markdown(f"### {row['due_date']}")
                
                # TENDINA IMPORTI (Quanti mesi paga?)
                c3.markdown("Incasso:")
                selected_amount_label = c3.selectbox(
                    "Mesi", 
                    list(CICLI_SCELTA.keys()), 
                    key=f"amount_{row['payment_id']}",
                    label_visibility="collapsed"
                )
                cicli_da_incassare = CICLI_SCELTA[selected_amount_label]
                
                # TENDINA METODO
                c4.markdown("Tramite:")
                selected_method = c4.selectbox(
                    "Metodo", 
                    PAYMENT_METHODS, 
                    key=f"method_{row['payment_id']}",
                    label_visibility="collapsed"
                )
                
                # BOTTONE
                c5.markdown("<br>", unsafe_allow_html=True) # Spaziatura
                if c5.button("💰 Salva", key=f"pay_{row['payment_id']}", use_container_width=True):
                    with st.spinner("Registrazione in corso..."):
                        process_payment(row['payment_id'], selected_method, cicli_da_incassare)
                    st.balloons()
                    st.rerun()

    with tab2:
        paid = full_df[full_df['status'] == 'PAID'].sort_values(by="paid_date", ascending=False)
        
        if "payment_method" not in paid.columns:
            paid["payment_method"] = ""
            
        st.dataframe(
            paid[['nome_utente', 'amount', 'due_date', 'paid_date', 'payment_method']],
            hide_index=True,
            use_container_width=True,
            column_config={
                "nome_utente": "Nome",
                "amount": "Incassato (€)",
                "due_date": "Scadenza Relativa",
                "paid_date": "Data Pagamento",
                "payment_method": "Tramite"
            }
        )
else:
    st.info("👋 Database vuoto. Usa la barra laterale a sinistra per aggiungere il primo amico!")

st.divider()
st.markdown("### 📅 Calendario Scadenze Quadrimestrali")
col1, col2, col3 = st.columns(3)
with col1: st.info("#### ❄️ 1° Quadrimestre \n## **12/01**")
with col2: st.info("#### 🌸 2° Quadrimestre \n## **12/05**")
with col3: st.info("#### 🍂 3° Quadrimestre \n## **12/09**")
