# --- VERSÃO 10.1 - FLUXO DE FALLBACK CORRIGIDO ---
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
st.title("🤖 Agente de Viabilidade de Projetos v10.1")

# --- CAIXA DE FERRAMENTAS DO AGENTE ---
@st.cache_resource
def setup_selenium_driver():
    chrome_options = Options(); chrome_options.add_argument("--headless"); chrome_options.add_argument("--no-sandbox"); chrome_options.add_argument("--disable-dev-shm-usage"); chrome_options.binary_location = "/usr/bin/chromium"
    service = Service(); driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def baixar_e_ler_pdf(url):
    try:
        response = requests.get(url, timeout=30); response.raise_for_status()
        pdf = pypdf.PdfReader(io.BytesIO(response.content)); return "".join(page.extract_text() for page in pdf.pages)
    except Exception as e:
        st.warning(f"Falha ao ler PDF: {url}."); return None

def extrair_texto_com_selenium(url):
    driver = setup_selenium_driver()
    try:
        driver.get(url); time.sleep(7)
        if "cloudflare" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
            st.warning(f"URL bloqueada por CAPTCHA: {url}"); return None
        return driver.find_element(By.TAG_NAME, 'body').text
    except Exception as e:
        st.warning(f"Falha ao usar Selenium: {url}."); return None
    finally:
        if 'driver' in locals() and driver: driver.quit()

def processar_url(url):
    with st.spinner(f"Processando URL: {url}..."):
        if url.lower().endswith('.pdf'): return baixar_e_ler_pdf(url)
        else: return extrair_texto_com_selenium(url)

def pesquisar_documento(servico_busca, search_id, query):
    try:
        resultado = servico_busca.cse().list(q=query, cx=search_id, num=1).execute()
        if 'items' in resultado: return resultado['items'][0]['link']
        return None
    except Exception: return None

# --- INTERFACE E LÓGICA PRINCIPAL ---
if 'etapa' not in st.session_state: st.session_state.etapa = 'inicio'

with st.sidebar:
    st.header("🔑 Configuração"); st.session_state.gemini_key = st.text_input("Sua Chave de API do Gemini", type="password", value=st.secrets.get("GEMINI_API_KEY", "")); st.session_state.search_key = st.text_input("Sua Chave de API de Busca", type="password", value=st.secrets.get("SEARCH_API_KEY", "")); st.session_state.search_id = st.text_input("Seu ID do Mecanismo de Busca", type="password", value=st.secrets.get("SEARCH_ENGINE_ID", ""))

col1, col2 = st.columns([2, 3]) # Dando mais espaço para a coluna de resultados
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

if st.session_state.etapa in ['selecionando_leis', 'fallback_manual', 'complementando_dossie', 'concluindo_analise', 'exibir_resultado']:
    with col1:
        st.subheader("2. Supervisão Humana (Nível Municipal)"); opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        links_escolhidos_key = st.multiselect("Selecione a(s) fonte(s) municipal(is):", options=opcoes.keys())
        
        if st.button("✅ Analisar Fontes", disabled=(st.session_state.etapa not in ['selecionando_leis', 'fallback_manual'])):
            if links_escolhidos_key:
                st.session_state.urls_escolhidas_keys = links_escolhidos_key
                opcoes_selecionadas = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
                urls_municipais = [opcoes_selecionadas[key] for key in links_escolhidos_key]
                
                with col2:
                    st.subheader("3. Processando Dossiê...")
                    textos_municipais = [texto for url in urls_municipais if (texto := processar_url(url))]
                
                if textos_municipais:
                    st.session_state.dossie = {'municipal': "\n".join(textos_municipais)}; st.session_state.fontes = {'municipal': ", ".join(urls_municipais)}
                    st.session_state.etapa = 'complementando_dossie'; st.rerun()
                else:
                    st.session_state.etapa = 'fallback_manual'; st.rerun()
            else:
                st.warning("Selecione pelo menos uma fonte.")

if st.session_state.etapa == 'fallback_manual':
    with col2:
        st.subheader("3. Plano B: Extração Manual"); st.warning("A extração automática falhou."); st.info("Abra o(s) link(s) em outra aba, copie o texto da lei e cole abaixo.")
        texto_manual = st.text_area("Cole o conteúdo do(s) documento(s) municipais aqui:", height=300)
        if st.button("✅ Usar Texto Manual e Continuar"):
            if texto_manual:
                st.session_state.dossie = {'municipal': texto_manual}; st.session_state.fontes = {'municipal': 'Texto colado manualmente'}
                st.session_state.etapa = 'complementando_dossie'; st.rerun()

if st.session_state.etapa == 'complementando_dossie':
    with col2:
        st.subheader("3. Processando Dossiê..."); servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key); cidade, estado = [x.strip().upper() for x in st.session_state.cidade_input.split('-')]; dossie = st.session_state.dossie; fontes = st.session_state.fontes
        with st.spinner(f"Buscando a Constituição do Estado de {estado} e a Constituição Federal..."):
            time.sleep(1); url_ce = pesquisar_documento(servico_busca, st.session_state.search_id, f'constituição do estado de {estado}'); 
            if url_ce: dossie['estadual'] = processar_url(url_ce); fontes['estadual'] = url_ce
            time.sleep(1); url_cf = pesquisar_documento(servico_busca, st.session_state.search_id, 'Constituição Federal do Brasil 1988 planalto'); 
            if url_cf: dossie['federal'] = processar_url(url_cf); fontes['federal'] = url_cf
        st.session_state.contexto = f"--- DOC FEDERAL ---\n{dossie.get('federal', 'Não encontrado.')}\n--- DOC ESTADUAL ---\n{dossie.get('estadual', 'Não encontrado.')}\n--- DOC MUNICIPAL ---\n{dossie.get('municipal', 'Não encontrado.')}"
        st.session_state.fontes = fontes; st.session_state.etapa = 'concluindo_analise'; st.rerun()

if st.session_state.etapa == 'concluindo_analise':
    with col2:
        st.subheader("Análise Jurídica Consolidada")
        with st.spinner("🧠 Analista de viabilidade processando o dossiê..."):
            genai.configure(api_key=st.session_state.gemini_key); modelo_ia = genai.GenerativeModel('gemini-2.5-pro'); prompt = f"""... (prompt completo da v10.0) ..."""; st.session_state.analise_final = modelo_ia.generate_content(prompt).text
        st.session_state.etapa = 'exibir_resultado'; st.rerun()

if st.session_state.etapa == 'exibir_resultado':
    with col2:
        st.subheader("Análise Jurídica Consolidada"); st.info("💡 Dica: Clique na caixa abaixo, pressione Ctrl+A para selecionar tudo e Ctrl+C para copiar.")
        st.text_area("Resultado:", st.session_state.analise_final, height=500)
        with st.expander("Fontes Utilizadas na Análise"):
            st.write(f"**Federal:** {st.session_state.fontes.get('federal', 'N/A')}"); st.write(f"**Estadual:** {st.session_state.fontes.get('estadual', 'N/A')}"); st.write(f"**Municipal:** {st.session_state.fontes.get('municipal', 'N/A')}")
    with col1:
        if st.button("Nova Análise"):
            keys_to_keep = ['gemini_key', 'search_key', 'search_id']; 
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep: del st.session_state[key]
            st.rerun()
