import streamlit as st
import requests
import pandas as pd

# --- CONFIGURAÇÃO DE SEGURANÇA ---
# No Streamlit Cloud, vais configurar isto em Settings > Secrets
try:
    DB_HOST = st.secrets["DATABRICKS_HOST"].rstrip("/")
    DB_TOKEN = st.secrets["DATABRICKS_TOKEN"]
    HEADERS = {"Authorization": f"Bearer {DB_TOKEN}"}
except Exception:
    st.error("❌ Erro: Segredos (Host/Token) não configurados no Streamlit!")
    st.stop()

# --- FUNÇÕES DE LÓGICA (ANTIGA API) ---

def get_job_by_name(job_name):
    """Procura o Job ID mais recente pelo nome, lidando com paginação."""
    page_token = None
    while True:
        url = f"{DB_HOST}/api/2.1/jobs/list"
        params = {"limit": 25, "page_token": page_token} if page_token else {"limit": 25}
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        jobs = data.get("jobs", [])
        matched = [j for j in jobs if job_name.lower() in j["settings"]["name"].lower()]
        
        if matched:
            # Ordenar por data de criação (mais recente primeiro)
            matched.sort(key=lambda x: x.get("created_time", 0), reverse=True)
            return matched[0]
        
        page_token = data.get("next_page_token")
        if not page_token: break
    return None

def trigger_job(job_id):
    """Dispara um job específico."""
    url = f"{DB_HOST}/api/2.1/jobs/run-now"
    resp = requests.post(url, headers=HEADERS, json={"job_id": job_id})
    resp.raise_for_status()
    return resp.json()

def get_run_logs(run_id):
    """Obtém detalhes e logs (output) de um Run específico."""
    # 1. Obter Status/Metadados
    url_details = f"{DB_HOST}/api/2.1/jobs/runs/get"
    details = requests.get(url_details, headers=HEADERS, params={"run_id": run_id}).json()
    
    # 2. Obter Output (Logs)
    url_output = f"{DB_HOST}/api/2.1/jobs/runs/get-output"
    output = requests.get(url_output, headers=HEADERS, params={"run_id": run_id}).json()
    
    return {
        "state": details.get("state", {}),
        "logs": output.get("logs", "Nenhum log disponível.")
    }

def cleanup_jobs(names_to_clean):
    """Remove duplicados mantendo apenas o mais recente."""
    url_list = f"{DB_HOST}/api/2.1/jobs/list"
    all_jobs = []
    page_token = None
    
    while True:
        params = {"limit": 100, "page_token": page_token} if page_token else {"limit": 100}
        resp = requests.get(url_list, headers=HEADERS, params=params)
        data = resp.json()
        all_jobs.extend(data.get("jobs", []))
        page_token = data.get("next_page_token")
        if not page_token: break

    results = {"deleted": 0, "kept": 0}
    for name in names_to_clean:
        matched = [j for j in all_jobs if name.lower() == j["settings"]["name"].lower()]
        if len(matched) > 1:
            matched.sort(key=lambda x: x.get("created_time", 0), reverse=True)
            results["kept"] += 1
            for job in matched[1:]:
                del_url = f"{DB_HOST}/api/2.1/jobs/delete"
                requests.post(del_url, headers=HEADERS, json={"job_id": job["job_id"]})
                results["deleted"] += 1
    return results

# --- INTERFACE VISUAL (STREAMLIT) ---

st.set_page_config(page_title="Databricks Manager", page_icon="🚀", layout="wide")

st.title("🚀 Databricks Manager")
st.caption("Versão Simplificada & Segura (Single App)")

tab1, tab2, tab3 = st.tabs(["🔥 Executar Jobs", "🧹 Limpeza de Workspace", "🔍 Consultar Logs"])

with tab1:
    st.subheader("Disparar Jobs")
    names_input = st.text_area("Insere os nomes (um por linha):", placeholder="job_vendas\njob_logs")
    
    if st.button("🚀 Iniciar Execuções"):
        names = [n.strip() for n in names_input.split("\n") if n.strip()]
        if not names:
            st.warning("Escreve pelo menos um nome.")
        else:
            for name in names:
                with st.status(f"A processar: {name}...", expanded=True) as status:
                    job = get_job_by_name(name)
                    if job:
                        run = trigger_job(job["job_id"])
                        st.write(f"✅ {name} iniciado! (Run ID: {run['run_id']})")
                    else:
                        st.write(f"❌ {name} não encontrado.")
            st.success("Processamento concluído!")

with tab2:
    st.subheader("Limpar Duplicados")
    st.info("Isto manterá apenas o Job ID mais recente para cada nome listado.")
    clean_input = st.text_area("Nomes exatos para limpar:", placeholder="meu_job_duplicado")
    
    if st.button("🧹 Correr Limpeza"):
        names = [n.strip() for n in clean_input.split("\n") if n.strip()]
        if names:
            with st.spinner("A limpar workspace..."):
                res = cleanup_jobs(names)
                st.success(f"Concluído! Apagados: {res['deleted']} | Mantidos: {res['kept']}")
        else:
            st.warning("Insere nomes para limpar.")

with tab3:
    st.subheader("Consultar Logs de Execução")
    col1, col2 = st.columns([1, 3])
    
    with col1:
        run_id_input = st.text_input("Insere o Run ID:")
        btn_logs = st.button("🔍 Ver Logs")
    
    if btn_logs and run_id_input:
        try:
            with st.spinner("A carregar logs..."):
                data = get_run_logs(run_id_input)
                state = data["state"]
                
                # Mostrar Status de forma elegante
                st.info(f"**Estado:** {state.get('life_cycle_state')} | **Resultado:** {state.get('result_state', 'A decorrer...')}")
                
                # Área de Logs (Stdout)
                st.text_area("Output (Stdout):", value=data["logs"], height=400)
        except Exception as e:
            st.error(f"Erro ao procurar o Run ID {run_id_input}. Verifique se o ID está correto.")