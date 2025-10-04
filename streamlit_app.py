# --- VERSÃO 8.1 - RESILIENTE COM FALLBACK MANUAL ---
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
st.title("🤖 Agente de Viabilidade de Projetos v8.1")

# --- CAIXA DE FERRAMENTAS DO AGENTE ---
@st.cache_resource
def setup_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless"); chrome_options.add_argument("--no-sandbox"); chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = "/usr/bin/chromium"
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def baixar_e_ler_pdf(url):
    try:
        response = requests.get(url, timeout=30); response.raise_for_status()
        pdf = pypdf.PdfReader(io.BytesIO(response.content)); return "".join(page.extract_text() for page in pdf.pages)
    except Exception as e:
        st.warning(f"Falha ao ler PDF: {url}. Erro: {e}"); return None

def extrair_texto_com_selenium(url):
    driver = setup_selenium_driver()
    try:
        driver.get(url); time.sleep(5)
        if "cloudflare" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
            st.warning(f"URL bloqueada por CAPTCHA: {url}"); return None
        return driver.find_element(By.TAG_NAME, 'body').text
    except Exception as e:
        st.warning(f"Falha ao usar Selenium na URL {url}: {e}"); return None

def processar_url(url):
    with st.spinner(f"Processando URL: {url}..."):
        if url.lower().endswith('.pdf'): return baixar_e_ler_pdf(url)
        else: return extrair_texto_com_selenium(url)

# --- INTERFACE E LÓGICA PRINCIPAL ---
if 'etapa' not in st.session_state: st.session_state.etapa = 'inicio'

with st.sidebar:
    st.header("🔑 Configuração")
    st.session_state.gemini_key = st.text_input("Sua Chave de API do Gemini", type="password", value=st.secrets.get("GEMINI_API_KEY", ""))
    st.session_state.search_key = st.text_input("Sua Chave de API de Busca", type="password", value=st.secrets.get("SEARCH_API_KEY", ""))
    st.session_state.search_id = st.text_input("Seu ID do Mecanismo de Busca", type="password", value=st.secrets.get("SEARCH_ENGINE_ID", ""))

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Defina sua Pesquisa")
    cidade_input = st.text_input("Município e UF", placeholder="Ex: Araçatuba - SP")
    pergunta = st.text_area("Pergunta / Tema do Projeto", placeholder="Ex: Competências para fomento à inovação e tecnologia")

    if st.button("🚀 Iniciar Análise", disabled=(not all([st.session_state.gemini_key, st.session_state.search_key, st.session_state.search_id]))):
        if cidade_input and pergunta:
            st.session_state.cidade_input = cidade_input; st.session_state.pergunta = pergunta
            st.session_state.etapa = 'buscando_leis'; st.rerun()

if st.session_state.etapa == 'buscando_leis':
    # ... (lógica de busca, sem mudanças) ...
    try:
        servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key)
        query = f'lei orgânica município de {st.session_state.cidade_input.split("-")[0].strip()}'
        resultado = servico_busca.cse().list(q=query, cx=st.session_state.search_id, num=5).execute()
        if 'items' in resultado:
            st.session_state.links_encontrados = resultado['items']; st.session_state.etapa = 'selecionando_leis'
        else:
            st.error("Nenhuma legislação municipal encontrada."); st.session_state.etapa = 'inicio'
    except Exception as e:
        st.error(f"Erro na busca: {e}"); st.session_state.etapa = 'inicio'
    st.rerun()

if st.session_state.etapa in ['selecionando_leis', 'analisando_leis', 'fallback_manual', 'buscando_fomento', 'concluido']:
    with col1:
        st.subheader("2. Supervisão Humana")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        links_escolhidos_key = st.multiselect("Selecione a(s) fonte(s) municipal(is) mais relevante(s):", options=opcoes.keys(), key="multiselect_key")
        
        if st.button("✅ Analisar Fontes Selecionadas", disabled=(st.session_state.etapa != 'selecionando_leis')):
            if links_escolhidos_key:
                st.session_state.urls_escolhidas_keys = links_escolhidos_key; st.session_state.etapa = 'analisando_leis'; st.rerun()

if st.session_state.etapa == 'analisando_leis':
    with col2:
        st.subheader("3. Processando Documentos")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        urls_para_processar = [opcoes[key] for key in st.session_state.urls_escolhidas_keys]
        
        # --- LÓGICA CORRIGIDA PARA TENTAR TODOS OS LINKS ---
        textos = []
        for url in urls_para_processar:
            texto = processar_url(url)
            if texto:
                textos.append(texto)
        
        if textos:
            st.session_state.contexto = "\n\n--- INÍCIO DE NOVO DOCUMENTO ---\n\n".join(textos)
            st.session_state.etapa = 'buscando_fomento' # Pula direto para a próxima etapa de análise
            st.rerun()
        else:
            # --- LÓGICA DO "PLANO B" ---
            st.warning("A extração automática de todos os links selecionados falhou.")
            st.session_state.etapa = 'fallback_manual'
            st.rerun()

if st.session_state.etapa == 'fallback_manual':
    with col2:
        st.subheader("3. Plano B: Extração Manual")
        st.info("A extração automática falhou (provavelmente por um CAPTCHA). Por favor, siga os passos:")
        st.markdown("1. Abra o(s) link(s) desejado(s) em uma nova aba.\n2. Copie o texto da lei.\n3. Cole o texto na caixa abaixo.")
        texto_manual = st.text_area("Cole o conteúdo do(s) documento(s) aqui:", height=250)
        
        if st.button("✅ Analisar Texto Manual"):
            if texto_manual:
                st.session_state.contexto = texto_manual
                st.session_state.etapa = 'buscando_fomento'
                st.rerun()
            else:
                st.warning("A caixa de texto está vazia.")

if st.session_state.etapa in ['buscando_fomento', 'concluido']:
    # Etapa de Análise (agora separada)
    if 'analise_final' not in st.session_state:
        with st.spinner("🧠 Consultor Sênior analisando o dossiê..."):
            genai.configure(api_key=st.session_state.gemini_key)
            modelo_ia = genai.GenerativeModel('gemini-2.5-pro')
            prompt_analise = f"""... (seu prompt completo da v8.0 aqui) ..."""
            response = modelo_ia.generate_content(prompt_analise)
            st.session_state.analise_final = response.text
    
    # Etapa de Busca por Fomento
    if 'fomento_final' not in st.session_state:
         with st.spinner("Consultor buscando por fontes de financiamento..."):
            # ... (lógica de busca por fomento da v8.0 aqui) ...
            st.session_state.fomento_final = "Busca por fomento ainda não implementada nesta versão." # Placeholder

    st.session_state.etapa = 'concluido'
    
if st.session_state.etapa == 'concluido':
    with col2:
        st.subheader("Análise Jurídica")
        st.text_area("Resultado (para copiar)", st.session_state.analise_final, height=300)
        st.markdown("---")
        st.subheader("Prospecção de Recursos (Beta)")
        st.markdown(st.session_state.fomento_final)

    with col1:
        if st.button("Nova Análise"):
            # ... (lógica para limpar a sessão) ...
            st.rerun()
