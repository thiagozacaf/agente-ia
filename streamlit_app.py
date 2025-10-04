# --- VERSÃO 8.0 - FINAL ---
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
st.title("🤖 Agente de Viabilidade de Projetos v8.0")
st.write("Uma ferramenta de IA para acelerar a análise jurídica e a prospecção de recursos para projetos em municípios.")

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

def baixar_e_ler_pdf(url):
    try:
        response = requests.get(url, timeout=30); response.raise_for_status()
        pdf = pypdf.PdfReader(io.BytesIO(response.content)); return "".join(page.extract_text() for page in pdf.pages)
    except: return None

def extrair_texto_com_selenium(url):
    driver = setup_selenium_driver()
    try:
        driver.get(url); time.sleep(5)
        if "cloudflare" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
            st.warning(f"URL bloqueada por CAPTCHA: {url}"); return None
        return driver.find_element(By.TAG_NAME, 'body').text
    except: return None
    finally:
        if 'driver' in locals() and driver: driver.quit()

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

    if st.button("🚀 Iniciar Análise Completa", disabled=(not all([st.session_state.gemini_key, st.session_state.search_key, st.session_state.search_id]))):
        if cidade_input and pergunta:
            st.session_state.cidade_input = cidade_input; st.session_state.pergunta = pergunta
            st.session_state.etapa = 'buscando_leis'; st.rerun()
        else:
            st.warning("Por favor, preencha todos os campos.")

if st.session_state.etapa == 'buscando_leis':
    with st.spinner("Pesquisando legislação municipal..."):
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

if st.session_state.etapa in ['selecionando_leis', 'analisando_leis', 'buscando_fomento', 'concluido']:
    with col1:
        st.subheader("2. Supervisão Humana")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        links_escolhidos_key = st.multiselect("Selecione a(s) fonte(s) municipal(is) mais relevante(s):", options=opcoes.keys(), key="multiselect_key")
        
        if st.button("✅ Analisar Legislação", disabled=(st.session_state.etapa != 'selecionando_leis')):
            if links_escolhidos_key:
                st.session_state.urls_escolhidas_keys = links_escolhidos_key; st.session_state.etapa = 'analisando_leis'; st.rerun()
            else:
                st.warning("Selecione pelo menos uma fonte.")

if st.session_state.etapa == 'analisando_leis':
    with col2:
        st.subheader("3. Análise de Viabilidade Jurídica")
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        urls_para_processar = [opcoes[key] for key in st.session_state.urls_escolhidas_keys]
        textos = [texto for url in urls_para_processar if (texto := processar_url(url))]
        
        if textos:
            contexto = "\n\n--- INÍCIO DE NOVO DOCUMENTO ---\n\n".join(textos)
            st.success(f"Dossiê montado com {len(textos)} documento(s).")
            with st.spinner("🧠 Consultor Sênior analisando o dossiê..."):
                genai.configure(api_key=st.session_state.gemini_key)
                modelo_ia = genai.GenerativeModel('gemini-2.5-pro')
                prompt_analise = f"""
                Você é um analista de viabilidade de projetos. Sua tarefa é responder à pergunta do usuário de forma direta e objetiva, usando o dossiê de leis fornecido.
                REGRAS:
                1.  NÃO use formalidades como "Prezado", saudações ou despedidas. Seja direto.
                2.  Sua resposta deve ter DUAS SEÇÕES CLARAS: "1. Análise Jurídica Direta" e "2. Sugestões Estratégicas".
                3.  Na SEÇÃO 1, resuma APENAS o que está escrito nos documentos, citando a fonte (ex: Art. 30 da CF/88, se aplicável).
                4.  Na SEÇÃO 2, com base na análise e no seu conhecimento geral, sugira ações e projetos práticos para o município. Deixe claro que são sugestões.

                PERGUNTA: {st.session_state.pergunta}
                Dossiê de Leis: {contexto}
                """
                response = modelo_ia.generate_content(prompt_analise)
                st.session_state.analise_final = response.text
                st.session_state.etapa = 'buscando_fomento'
                st.rerun()
        else:
            st.error("Não foi possível extrair texto dos links selecionados."); st.session_state.etapa = 'inicio'

if st.session_state.etapa == 'buscando_fomento':
    with col2:
        st.subheader("3. Análise de Viabilidade Jurídica")
        st.text_area("Análise Gerada (para copiar)", st.session_state.analise_final, height=300)
        st.markdown("---")
        st.subheader("4. Prospecção de Recursos (Beta)")
        
        with st.spinner("Consultor buscando por fontes de financiamento..."):
            genai.configure(api_key=st.session_state.gemini_key)
            modelo_ia = genai.GenerativeModel('gemini-2.5-pro')
            prompt_keywords = f"Extraia 5 a 7 termos de busca ideais para encontrar editais e fundos de financiamento, com base no seguinte texto: {st.session_state.analise_final}"
            response_keywords = modelo_ia.generate_content(prompt_keywords)
            palavras_chave = response_keywords.text.replace("\n", " ").replace("*", "")
            
            st.write(f"**Termos usados na busca:** *{palavras_chave}*")
            
            servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key)
            fontes_fomento = ["site:finep.gov.br", "site:bndes.gov.br", "site:portal.plataformamaisbrasil.gov.br"]
            resultados_fomento = []
            for site in fontes_fomento:
                query_fomento = f"{palavras_chave} {site}"
                resultado = servico_busca.cse().list(q=query_fomento, cx=st.session_state.search_id, num=2).execute()
                if 'items' in resultado:
                    for item in resultado['items']:
                        resultados_fomento.append(f"- **[{item['title']}]({item['link']})** ({site.split(':')[1]})")
            
            st.session_state.fomento_final = "\n".join(resultados_fomento)
            st.session_state.etapa = 'concluido'
            st.rerun()

if st.session_state.etapa == 'concluido':
    with col2:
        st.subheader("3. Análise de Viabilidade Jurídica")
        st.text_area("Análise Gerada (para copiar)", st.session_state.analise_final, height=300)
        st.markdown("---")
        st.subheader("4. Prospecção de Recursos (Beta)")
        st.markdown(st.session_state.fomento_final or "Nenhuma oportunidade de fomento encontrada com os termos extraídos.")

    with col1:
        if st.button("Nova Análise"):
            keys_to_keep = ['gemini_key', 'search_key', 'search_id']
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep: del st.session_state[key]
            st.rerun()
