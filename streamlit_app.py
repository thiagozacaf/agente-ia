# --- VERSÃO FINAL E ESTÁVEL ---
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
st.title("🤖 Agente de Análise Jurídica")
st.write("Uma ferramenta para acelerar a análise de viabilidade jurídica de projetos em municípios.")

# --- CAIXA DE FERRAMENTAS DO AGENTE ---

# Usamos @st.cache_resource para não reinstalar o navegador a cada ação
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

def baixar_e_ler_pdf(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        pdf = pypdf.PdfReader(io.BytesIO(response.content))
        return "".join(page.extract_text() for page in pdf.pages)
    except Exception as e:
        st.error(f"Falha ao ler PDF: {e}")
        return None

def extrair_texto_com_selenium(url):
    driver = setup_selenium_driver()
    try:
        driver.get(url)
        time.sleep(5)
        if "cloudflare" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
            st.warning(f"URL bloqueada por CAPTCHA: {url}")
            return None
        return driver.find_element(By.TAG_NAME, 'body').text
    except Exception as e:
        st.error(f"Falha ao usar Selenium na URL {url}: {e}")
        return None
    # Não fechamos o driver aqui por causa do cache

def processar_url(url):
    with st.spinner(f"Processando URL: {url}..."):
        if url.lower().endswith('.pdf'):
            return baixar_e_ler_pdf(url)
        else:
            return extrair_texto_com_selenium(url)

# --- INTERFACE E LÓGICA DO STREAMLIT COM MEMÓRIA (st.session_state) ---

if 'etapa' not in st.session_state:
    st.session_state.etapa = 'inicio'

with st.sidebar:
    st.header("🔑 Configuração")
    st.session_state.gemini_key = st.text_input("Sua Chave de API do Gemini", type="password", value=st.secrets.get("GEMINI_API_KEY", ""))
    st.session_state.search_key = st.text_input("Sua Chave de API de Busca", type="password", value=st.secrets.get("SEARCH_API_KEY", ""))
    st.session_state.search_id = st.text_input("Seu ID do Mecanismo de Busca", type="password", value=st.secrets.get("SEARCH_ENGINE_ID", ""))

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Defina sua Pesquisa")
    cidade_input = st.text_input("Município e UF", placeholder="Ex: Araçatuba - SP")
    pergunta = st.text_area("Pergunta / Tema do Projeto", placeholder="Ex: Competências para fomento à inovação")

    if st.button("🚀 Iniciar Pesquisa", disabled=(not all([st.session_state.gemini_key, st.session_state.search_key, st.session_state.search_id]))):
        if cidade_input and pergunta:
            st.session_state.cidade_input = cidade_input
            st.session_state.pergunta = pergunta
            st.session_state.etapa = 'buscando'
            st.rerun()
        else:
            st.warning("Por favor, preencha o município e a pergunta.")

if st.session_state.etapa == 'buscando':
    with st.spinner("Pesquisando documentos..."):
        try:
            servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key)
            query = f'lei orgânica município de {st.session_state.cidade_input.split("-")[0].strip()}'
            resultado = servico_busca.cse().list(q=query, cx=st.session_state.search_id, num=5).execute()
            if 'items' in resultado:
                st.session_state.links_encontrados = resultado['items']
                st.session_state.etapa = 'selecionando'
            else:
                st.error("Nenhum documento encontrado na busca.")
                st.session_state.etapa = 'inicio'
        except Exception as e:
            st.error(f"Erro na busca do Google: {e}")
            st.session_state.etapa = 'inicio'
    st.rerun()

if st.session_state.etapa in ['selecionando', 'analisando', 'concluido']:
    with col1:
        st.subheader("2. Supervisão Humana")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        links_escolhidos_key = st.multiselect("Encontrei estes links. Selecione um ou mais para analisar:", options=opcoes.keys(), key="multiselect_key")
        
        if st.button("✅ Processar Fontes Selecionadas", disabled=(st.session_state.etapa != 'selecionando')):
            if links_escolhidos_key:
                st.session_state.urls_escolhidas_keys = links_escolhidos_key
                st.session_state.etapa = 'analisando'
                st.rerun()
            else:
                st.warning("Por favor, selecione pelo menos um link para continuar.")

if st.session_state.etapa == 'analisando':
    with col2:
        st.subheader("3. Resultados da Análise")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        urls_para_processar = [opcoes[key] for key in st.session_state.urls_escolhidas_keys]
        
        textos = [texto for url in urls_para_processar if (texto := processar_url(url))]
        
        if textos:
            contexto = "\n\n--- INÍCIO DE NOVO DOCUMENTO ---\n\n".join(textos)
            st.success(f"Dossiê montado com {len(textos)} documento(s).")
            
            with st.spinner("🧠 O Consultor Sênior está analisando o dossiê..."):
                genai.configure(api_key=st.session_state.gemini_key)
                modelo_ia = genai.GenerativeModel('gemini-2.5-pro')
                prompt = f"""Você é um consultor jurídico-governamental... **Pergunta:** {st.session_state.pergunta} **Dossiê:** {contexto}"""
                response = modelo_ia.generate_content(prompt)
                st.session_state.analise_final = response.text
                st.session_state.etapa = 'concluido'
                st.rerun()
        else:
            st.error("Não foi possível extrair texto dos links selecionados.")
            st.session_state.etapa = 'inicio'

if st.session_state.etapa == 'concluido':
    with col2:
        st.subheader("3. Resultados da Análise")
        st.markdown(st.session_state.analise_final)
    with col1: # Exibe o botão de nova análise na coluna original
        if st.button("Nova Análise"):
            keys_to_keep = ['gemini_key', 'search_key', 'search_id']
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]
            st.rerun()
