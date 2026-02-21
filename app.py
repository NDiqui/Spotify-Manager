import pandas as pd
import streamlit as st
import uuid
from datetime import datetime
from dateutil.relativedelta import relativedelta
from streamlit_gsheets import GSheetsConnection

#----------   Configuration Constants   ----------

Amount_per_cycle = 14.00  # Import for each cycle
Currency = "€"  # Currency symbol
PAYMENT_METHODS = ["Contanti", "Satispay", "Bonifico", "PayPal"]

#------ Page Setup ----------

st.set_page_config( page_title="Spotify Manager", page_icon = "🎧", layout="wide" )
st.title("🎧 Spotify Family Manager")

#------ Database Connection  Gsheets ----------
conn = st.connection("gsheets", type=GSheetsConnection)

#------ Backend Functions    ----------

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

        # --- LA MAGIA PER GOOGLE SHEETS ---
        # Questo blocco prende i nomi reali e li stampa FISICAMENTE nel foglio dei pagamenti
        if not df_users.empty and not df_payments.empty:
            # Crea un dizionario che associa l'ID al Nome
            mappa_nomi = dict(zip(df_users['user_id'], df_users['name']))
            # Crea la nuova colonna 'nome_utente' nel foglio pagamenti
            df_payments['nome_utente'] = df_payments['user_id'].map(mappa_nomi)
            
            # Riordina le colonne per far apparire il nome subito all'inizio nel foglio Google
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
        "nome_utente": name, # Salva il nome fisicamente
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

def process_payment(payment_id, method):
    """Close the current payment, save the method, and create the future one."""
    df_users, df_payments = get_data()
    
    idx_list = df_payments.index[df_payments['payment_id'] == payment_id].tolist()
    if not idx_list:
        st.error("Errore: Pagamento non trovato.")
        return
    row_idx = idx_list[0]
    
    current_row = df_payments.iloc[row_idx]

    df_payments.at[row_idx, "status"] = "PAID"
    df_payments.at[row_idx, "paid_date"] = datetime.now().strftime("%Y-%m-%d")
    df_payments.at[row_idx, "payment_method"] = method
    
    try:
        current_due = datetime.strptime(str(current_row["due_date"]), "%Y-%m-%d")
    except:
        current_due = datetime.now()
    
    next_due = current_due + relativedelta(months=+4)

    # Recupera il nome dell'utente
    nome = current_row["nome_utente"] if "nome_utente" in current_row else "Sconosciuto"

    new_payment = pd.DataFrame([{
        "payment_id": str(uuid.uuid4())[:8],
        "user_id": current_row["user_id"],
        "nome_utente": nome, # Salva il nome anche nel futuro pagamento
        "amount": current_row["amount"],
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
            with st.spinner("Creating user and transactions..."):
                create_user(name_input)
            st.success("User created successfully!")
            st.rerun()

try:    
    df_users, df_payments = get_data()
except:
    st.stop()

if not df_payments.empty and not df_users.empty:
    full_df = pd.merge(df_payments, df_users[['user_id', 'active']], on="user_id", how="left")
    full_df = full_df[full_df['active'] == True]
    full_df = full_df.sort_values(by="due_date")

    # --- INIZIO DASHBOARD RIASSUNTIVA MOBILE ---
    st.markdown("### 📊 Stato Attuale")
    
    pending_status = full_df[full_df['status'] == 'PENDING']
    da_pagare = []
    in_regola = []
    
    oggi = datetime.now().date()
    for _, row in pending_status.iterrows():
        try:
            scadenza = datetime.strptime(str(row['due_date']), "%Y-%m-%d").date()
            if scadenza <= oggi:
                da_pagare.append(row['nome_utente'])
            else:
                in_regola.append(row['nome_utente'])
        except:
            da_pagare.append(row['nome_utente'])
    
    col_red, col_green = st.columns(2)
    with col_red:
        testo_rossi = "\n".join([f"• {nome}" for nome in da_pagare]) if da_pagare else "Nessuno 🎉"
        st.error(f"🔴 **IN RITARDO**\n\n{testo_rossi}")
        
    with col_green:
        testo_verdi = "\n".join([f"• {nome}" for nome in in_regola]) if in_regola else "Nessuno"
        st.success(f"🟢 **IN REGOLA**\n\n{testo_verdi}")
        
    st.divider()
    # --- FINE DASHBOARD RIASSUNTIVA MOBILE ---

    tab1, tab2 = st.tabs(["🔴 Da Incassare", "🟢 Storico Pagamenti"])
    
    with tab1:
        pending = full_df[full_df['status'] == 'PENDING']
        
        if pending.empty:
            st.info("Tutto pagato! Nessun credito in sospeso.")
        
        for i, row in pending.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 3, 2])
                
                c1.markdown(f"### {row['nome_utente']}")
                
                try:
                    due_date_obj = datetime.strptime(str(row['due_date']), "%Y-%m-%d").date()
                    if due_date_obj < datetime.now().date():
                        c2.markdown(f"Scadenza:\n### :red[{row['due_date']}] ⚠️")
                    else:
                        c2.markdown(f"Scadenza:\n### {row['due_date']}")
                except:
                    c2.markdown(f"### {row['due_date']}")
                
                c3.markdown(f"Importo: **{Currency} {row['amount']}**")
                
                selected_method = c4.selectbox(
                    "Metodo", 
                    PAYMENT_METHODS, 
                    key=f"method_{row['payment_id']}",
                    label_visibility="collapsed"
                )
                
                if c5.button("💰 Incassa", key=f"pay_{row['payment_id']}", use_container_width=True):
                    with st.spinner("Registrazione pagamento..."):
                        process_payment(row['payment_id'], selected_method)
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
                "amount": "Importo",
                "due_date": "Scadenza Rata",
                "paid_date": "Data Pagamento",
                "payment_method": "Tramite"
            }
        )
else:
    st.info("👋 Database vuoto. Usa la barra laterale a sinistra per aggiungere il primo amico!")


# --- LEGENDA SCADENZE IN BASSO ---
st.divider()
st.markdown("### 📅 Calendario Scadenze Quadrimestrali")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("#### ❄️ 1° Quadrimestre \n## **12/01** \n*(12 Gennaio)*")

with col2:
    st.info("#### 🌸 2° Quadrimestre \n## **12/05** \n*(12 Maggio)*")

with col3:
    st.info("#### 🍂 3° Quadrimestre \n## **12/09** \n*(12 Settembre)*")
