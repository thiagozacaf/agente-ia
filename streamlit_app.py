# --- VERSÃO 10.3 - MELHORIA DE INTERFACE E FEEDBACK ---
import streamlit as st
import os
import google.generativeai as genai
import pypdf
import io
import requests
from googleapiclient.discovery import build
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Agente de Análise Jurídica")
st.title("🤖 Agente de Viabilidade de Projetos v10.3")

# --- CAIXA DE FERRAMENTAS DO AGENTE ---
@st.cache_resource
def setup_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = "/usr/bin/chromium"
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def processar_url_com_status(url):
    texto = None
    status_message = f"Processando: {url}"
    try:
        if url.lower().endswith('.pdf'):
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            pdf = pypdf.PdfReader(io.BytesIO(response.content))
            texto = "".join(page.extract_text() for page in pdf.pages)
            status_message = f"✅ PDF lido com sucesso: {url}"
        else:
            driver = setup_selenium_driver()
            driver.get(url)
            time.sleep(7)
            page_source = driver.page_source.lower()
            if "cloudflare" in page_source or "captcha" in page_source:
                status_message = f"❌ URL bloqueada por CAPTCHA: {url}"
            else:
                texto = driver.find_element(By.TAG_NAME, 'body').text
                status_message = f"✅ Página web lida com sucesso: {url}"
    except Exception as e:
        status_message = f"❌ Falha no processamento: {url}. Erro: {e}"
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
    return texto, status_message

def pesquisar_documento(servico_busca, search_id, query):
    try:
        resultado = servico_busca.cse().list(q=query, cx=search_id, num=1).execute()
        if 'items' in resultado: return resultado['items'][0]['link']
        return None
    except: return None

# --- INTERFACE E LÓGICA PRINCIPAL ---
if 'etapa' not in st.session_state: st.session_state.etapa = 'inicio'

with st.sidebar:
    st.header("🔑 Configuração"); st.session_state.gemini_key = st.text_input("Sua Chave Gemini", type="password", value=st.secrets.get("GEMINI_API_KEY", "")); st.session_state.search_key = st.text_input("Sua Chave de Busca", type="password", value=st.secrets.get("SEARCH_API_KEY", "")); st.session_state.search_id = st.text_input("Seu ID de Busca", type="password", value=st.secrets.get("SEARCH_ENGINE_ID", ""))

col1, col2 = st.columns([2, 3])
with col1:
    st.subheader("1. Defina sua Pesquisa"); cidade_input = st.text_input("Município e UF", placeholder="Ex: Araçatuba - SP"); pergunta = st.text_area("Pergunta / Tema do Projeto", placeholder="Ex: Competências para fomento à inovação", height=150)
    if st.button("🚀 Iniciar Pesquisa", disabled=(not all([st.session_state.gemini_key, st.session_state.search_key, st.session_state.search_id]))):
        if cidade_input and pergunta:
            st.session_state.cidade_input = cidade_input; st.session_state.pergunta = pergunta; st.session_state.etapa = 'buscando_leis'; st.rerun()

if st.session_state.etapa == 'buscando_leis':
    try:
        servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key); query = f'lei orgânica município de {st.session_state.cidade_input.split("-")[0].strip()}'; resultado = servico_busca.cse().list(q=query, cx=st.session_state.search_id, num=5).execute()
        if 'items' in resultado: st.session_state.links_encontrados = resultado['items']; st.session_state.etapa = 'selecionando_leis'
        else: st.error("Nenhuma legislação municipal encontrada."); st.session_state.etapa = 'inicio'
    except Exception as e: st.error(f"Erro na busca: {e}"); st.session_state.etapa = 'inicio'
    st.rerun()

if st.session_state.etapa in ['selecionando_leis', 'processando_municipal', 'fallback_manual', 'complementando_dossie', 'concluindo_analise', 'exibir_resultado']:
    with col1:
        st.subheader("2. Supervisão Humana"); st.markdown("---"); st.write("Encontrei os seguintes links. Analise-os e selecione abaixo:"); 
        opcoes_numeradas = []
        for i, item in enumerate(st.session_state.links_encontrados):
            num_opcao = f"Opção [{i+1}]"; opcoes_numeradas.append(num_opcao)
            st.markdown(f"**{num_opcao}: {item['title']}**"); st.markdown(f"*{item['link']}*", unsafe_allow_html=True)
        st.markdown("---")
        links_escolhidos_num = st.multiselect("Selecione os números das fontes que deseja analisar:", options=opcoes_numeradas)
        if st.button("✅ Analisar Fontes Selecionadas", disabled=(st.session_state.etapa != 'selecionando_leis')):
            if links_escolhidos_num:
                st.session_state.urls_escolhidas_indices = [int(n.split('[')[1].split(']')[0]) - 1 for n in links_escolhidos_num]
                st.session_state.etapa = 'processando_municipal'; st.rerun()

if st.session_state.etapa == 'processando_municipal':
    with col2:
        st.subheader("3. Processando Documentos..."); urls_para_processar = [st.session_state.links_encontrados[i]['link'] for i in st.session_state.urls_escolhidas_indices]
        textos_sucesso = []; relatorio_falhas = []
        for url in urls_para_processar:
            texto, status = processar_url_com_status(url)
            if texto: textos_sucesso.append(texto)
            relatorio_falhas.append(status)
        if textos_sucesso:
            st.session_state.dossie = {'municipal': "\n".join(textos_sucesso)}; st.session_state.fontes = {'municipal': ", ".join(urls_para_processar)}; st.session_state.etapa = 'complementando_dossie'; st.rerun()
        else:
            st.session_state.relatorio_falhas = relatorio_falhas; st.session_state.etapa = 'fallback_manual'; st.rerun()

if st.session_state.etapa == 'fallback_manual':
    with col2:
        st.subheader("3. Plano B: Extração Manual"); st.error("A extração automática de todas as fontes selecionadas falhou.")
        with st.expander("Ver relatório de falhas detalhado"):
            for msg in st.session_state.relatorio_falhas: st.write(msg)
        st.info("Para continuar, abra o(s) link(s) em outra aba, copie o texto e cole abaixo.")
        texto_manual = st.text_area("Cole o conteúdo do(s) documento(s) aqui:", height=300)
        if st.button("✅ Usar Texto Manual e Continuar"):
            if texto_manual:
                st.session_state.dossie = {'municipal': texto_manual}; st.session_state.fontes = {'municipal': 'Texto colado manualmente'}; st.session_state.etapa = 'complementando_dossie'; st.rerun()

if st.session_state.etapa == 'complementando_dossie':
    # Lógica para buscar estadual/federal e consolidar o dossiê
    pass

if st.session_state.etapa == 'concluindo_analise':
    # Lógica para chamar a IA com o dossiê completo
    pass

if st.session_state.etapa == 'exibir_resultado':
    with col2:
        st.subheader("Análise Consolidada"); st.info("💡 Dica: Clique na caixa, pressione Ctrl+A e Ctrl+C para copiar.")
        st.text_area("Resultado:", st.session_state.analise_final, height=500)
        with st.expander("Fontes Utilizadas na Análise"):
            st.write(f"**Federal:** {st.session_state.fontes.get('federal', 'N/A')}"); st.write(f"**Estadual:** {st.session_state.fontes.get('estadual', 'N/A')}"); st.write(f"**Municipal:** {st.session_state.fontes.get('municipal', 'N/A')}")
    with col1:
        if st.button("Nova Análise"):
            keys_to_keep = ['gemini_key', 'search_key', 'search_id']; 
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep: del st.session_state[key]
            st.rerun()
