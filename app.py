import pandas as pd
import streamlit as st
import uuid
from datetime import datetime
from dateutil.relativedelta import relativedelta
from streamlit_gsheets import GSheetsConnection

#----------   Configuration Constants   ----------

Amount_per_cycle = 14.00  # Import for each cycle
Currency = "€"  # Currency symbol
PAYMENT_METHODS = ["Contanti", "Satispay", "Bonifico", "PayPal"] # I 4 metodi di pagamento

#------ Page Setup ----------

st.set_page_config( page_title="Spotify Manager", page_icon = "🎧", layout="wide" ) # Ho messo "wide" per dare più spazio alle colonne
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
            
            # Controllo di sicurezza: se la colonna del metodo non esiste ancora nel foglio, la crea
            if "payment_method" not in df_payments.columns:
                df_payments["payment_method"] = ""

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
        "amount": Amount_per_cycle,
        "due_date": datetime.now().strftime("%Y-%m-%d"), 
        "status": "PENDING",
        "paid_date": None,
        "payment_method": "" # Inizializza il campo vuoto
    }])

    updated_users = pd.concat([df_users, new_user], ignore_index=True)
    conn.update(worksheet="users", data=updated_users)

    updated_payments = pd.concat([df_payments, new_payment], ignore_index=True)
    conn.update(worksheet="payments", data=updated_payments)

    st.cache_data.clear()

def process_payment(payment_id, method):
    """Close the current payment, save the method, and create the future one."""
    _, df_payments = get_data()
    
    idx_list = df_payments.index[df_payments['payment_id'] == payment_id].tolist()
    if not idx_list:
        st.error("Errore: Pagamento non trovato.")
        return
    row_idx = idx_list[0]
    
    current_row = df_payments.iloc[row_idx]

    # 1. Update status, date AND PAYMENT METHOD
    df_payments.at[row_idx, "status"] = "PAID"
    df_payments.at[row_idx, "paid_date"] = datetime.now().strftime("%Y-%m-%d")
    df_payments.at[row_idx, "payment_method"] = method
    
    # 2. Calculate the next due date (+4 months)
    try:
        current_due = datetime.strptime(str(current_row["due_date"]), "%Y-%m-%d")
    except:
        current_due = datetime.now()
    
    next_due = current_due + relativedelta(months=+4)

    # 3. Create the new row for the future
    new_payment = pd.DataFrame([{
        "payment_id": str(uuid.uuid4())[:8],
        "user_id": current_row["user_id"],
        "amount": current_row["amount"],
        "due_date": next_due.strftime("%Y-%m-%d"),
        "status": "PENDING",
        "paid_date": None,
        "payment_method": "" # Il futuro pagamento per ora non ha metodo
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
    full_df = pd.merge(df_payments, df_users, on="user_id", how="left")
    full_df = full_df[full_df['active'] == True]
    full_df = full_df.sort_values(by="due_date")

    tab1, tab2 = st.tabs(["🔴 Da Incassare", "🟢 Storico Pagamenti"])
    
    with tab1:
        pending = full_df[full_df['status'] == 'PENDING']
        
        if pending.empty:
            st.info("Tutto pagato! Nessun credito in sospeso.")
        
        for i, row in pending.iterrows():
            with st.container(border=True):
                # ORA ABBIAMO 5 COLONNE per far spazio alla tendina del metodo di pagamento                    
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 3, 2])
                
                c1.markdown(f"### {row['name']}")
                
                try:
                    due_date_obj = datetime.strptime(str(row['due_date']), "%Y-%m-%d").date()
                    if due_date_obj < datetime.now().date():
                        # Mando a capo la data (\n) e uso ### per farla grande e rossa
                        c2.markdown(f"Scadenza:\n### :red[{row['due_date']}] ⚠️")
                    else:
                        # Mando a capo la data (\n) e uso ### per farla grande
                        c2.markdown(f"Scadenza:\n### {row['due_date']}")
                except:
                    c2.markdown(f"### {row['due_date']}")
                
                c3.markdown(f"Importo: **{Currency} {row['amount']}**")
                
                # LA NUOVA TENDINA PER IL METODO DI PAGAMENTO
                selected_method = c4.selectbox(
                    "Metodo", 
                    PAYMENT_METHODS, 
                    key=f"method_{row['payment_id']}",
                    label_visibility="collapsed" # Nasconde la scritta "Metodo" per questioni di design
                )
                
                # IL BOTTONE (che ora invia anche il metodo scelto)
                if c5.button("💰 Incassa", key=f"pay_{row['payment_id']}", use_container_width=True):
                    with st.spinner("Registrazione pagamento..."):
                        process_payment(row['payment_id'], selected_method)
                    st.balloons()
                    st.rerun()

    with tab2:
        paid = full_df[full_df['status'] == 'PAID'].sort_values(by="paid_date", ascending=False)
        
        # Gestiamo il caso in cui ci siano pagamenti vecchi senza metodo
        if "payment_method" not in paid.columns:
            paid["payment_method"] = ""
            
        st.dataframe(
            paid[['name', 'amount', 'due_date', 'paid_date', 'payment_method']],
            hide_index=True,
            use_container_width=True,
            column_config={
                "name": "Nome",
                "amount": "Importo",
                "due_date": "Scadenza Rata",
                "paid_date": "Data Pagamento",
                "payment_method": "Tramite" # Nuova colonna nello storico!
            }
        )
else:
    st.info("👋 Database vuoto. Usa la barra laterale a sinistra per aggiungere il primo amico!")


# --- LEGENDA SCADENZE IN BASSO ---
st.divider()
st.markdown("#### 📅 Calendario Scadenze Quadrimestrali")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("❄️ **1° Quadrimestre** \nScadenza: **12/01** (12 Gennaio)")

with col2:
    st.info("🌸 **2° Quadrimestre** \nScadenza: **12/05** (12 Maggio)")

with col3:
    st.info("🍂 **3° Quadrimestre** \nScadenza: **12/09** (12 Settembre)")