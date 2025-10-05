# --- VERSÃO 9.0 - ANÁLISE EM ETAPAS PARA EVITAR ALUCINAÇÕES ---
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
st.title("🤖 Agente de Viabilidade de Projetos v9.0")

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

def pesquisar_documento(servico_busca, search_id, query):
    try:
        resultado = servico_busca.cse().list(q=query, cx=search_id, num=1).execute()
        if 'items' in resultado: return resultado['items'][0]['link']
        return None
    except Exception: return None

# --- NOVA FUNÇÃO DE ANÁLISE EM ETAPAS ---
def analisar_em_etapas(modelo_ia, dossie, pergunta):
    resumos = {}
    st.write("Iniciando análise em etapas para maior precisão...")
    
    # Etapa 1: Resumir cada documento individualmente
    for esfera, texto in dossie.items():
        if texto and len(texto) > 100:
            with st.spinner(f"Etapa 1: Pré-analisando e resumindo o documento da esfera {esfera}..."):
                prompt_resumo = f"""
                Com base na pergunta '{pergunta}', extraia e resuma os artigos, seções ou pontos mais relevantes APENAS do seguinte documento. Seja conciso e direto. Se nada for relevante, apenas responda 'Nenhuma informação relevante encontrada neste documento.'.
                DOCUMENTO:
                {texto[:50000]} # Limita o tamanho por segurança e custo
                """
                try:
                    response = modelo_ia.generate_content(prompt_resumo)
                    resumos[esfera] = response.text
                    st.success(f"Documento da esfera {esfera} resumido.")
                except Exception as e:
                    st.warning(f"Não foi possível resumir o documento da esfera {esfera}. Erro: {e}")
                    resumos[esfera] = "Falha ao processar este documento."
    
    # Etapa 2: Sintetizar os resumos em uma análise final
    with st.spinner("Etapa 2: Consolidando os resumos na análise final..."):
        contexto_final = f"""
        RESUMOS DAS LEIS RELEVANTES:
        - Federal: {resumos.get('federal', 'N/A')}
        - Estadual: {resumos.get('estadual', 'N/A')}
        - Municipal: {resumos.get('municipal', 'N/A')}
        """
        
        prompt_final = f"""
        Você é um analista de viabilidade de projetos. Com base nos resumos das leis fornecidos e na pergunta do usuário, escreva uma análise consolidada.
        REGRAS:
        1.  Sua resposta deve ter DUAS SEÇÕES: "1. Análise Jurídica Direta" (baseada nos resumos) e "2. Sugestões Estratégicas" (baseada na análise e seu conhecimento geral).
        2.  Seja direto e prático, sem saudações ou despedidas.
        3.  Cite as fontes sempre que possível. Se um resumo indicar 'Nenhuma informação relevante', mencione isso na sua análise.

        RESUMOS DAS LEIS:
        {contexto_final}

        PERGUNTA ORIGINAL:
        {pergunta}

        ANÁLISE FINAL:
        """
        try:
            response_final = modelo_ia.generate_content(prompt_final)
            st.success("Análise final gerada!")
            return response_final.text
        except Exception as e:
            st.error(f"Ocorreu um erro na análise final: {e}")
            return "Falha ao gerar a análise consolidada."

# --- INTERFACE E LÓGICA PRINCIPAL ---
if 'etapa' not in st.session_state: st.session_state.etapa = 'inicio'

with st.sidebar:
    st.header("🔑 Configuração"); st.session_state.gemini_key = st.text_input("Sua Chave de API do Gemini", type="password", value=st.secrets.get("GEMINI_API_KEY", "")); st.session_state.search_key = st.text_input("Sua Chave de API de Busca", type="password", value=st.secrets.get("SEARCH_API_KEY", "")); st.session_state.search_id = st.text_input("Seu ID do Mecanismo de Busca", type="password", value=st.secrets.get("SEARCH_ENGINE_ID", ""))

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Defina sua Pesquisa"); cidade_input = st.text_input("Município e UF", placeholder="Ex: Araçatuba - SP"); pergunta = st.text_area("Pergunta / Tema do Projeto", placeholder="Ex: Competências para fomento à inovação")
    if st.button("🚀 Iniciar Pesquisa", disabled=(not all([st.session_state.gemini_key, st.session_state.search_key, st.session_state.search_id]))):
        if cidade_input and pergunta:
            st.session_state.cidade_input = cidade_input; st.session_state.pergunta = pergunta; st.session_state.etapa = 'buscando_leis'; st.rerun()

if st.session_state.etapa == 'buscando_leis':
    try:
        servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key)
        with st.spinner("Pesquisando legislação municipal..."):
            query = f'lei orgânica município de {st.session_state.cidade_input.split("-")[0].strip()}'
            resultado = servico_busca.cse().list(q=query, cx=st.session_state.search_id, num=5).execute()
            if 'items' in resultado:
                st.session_state.links_encontrados = resultado['items']; st.session_state.etapa = 'selecionando_leis'
            else:
                st.error("Nenhuma legislação municipal encontrada."); st.session_state.etapa = 'inicio'
    except Exception as e:
        st.error(f"Erro na busca: {e}"); st.session_state.etapa = 'inicio'
    st.rerun()

if st.session_state.etapa in ['selecionando_leis', 'analisando_leis', 'fallback_manual', 'analise_pos_manual', 'concluido']:
    with col1:
        st.subheader("2. Supervisão Humana (Nível Municipal)"); opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}
        links_escolhidos_key = st.multiselect("Selecione a(s) fonte(s) municipal(is):", options=opcoes.keys())
        if st.button("✅ Analisar Fontes", disabled=(st.session_state.etapa != 'selecionando_leis')):
            if links_escolhidos_key:
                st.session_state.urls_escolhidas_keys = links_escolhidos_key; st.session_state.etapa = 'analisando_leis'; st.rerun()

if st.session_state.etapa == 'analisando_leis':
    with col2:
        st.subheader("3. Processando Dossiê..."); servico_busca = build("customsearch", "v1", developerKey=st.session_state.search_key); cidade, estado = [x.strip().upper() for x in st.session_state.cidade_input.split('-')]
        dossie = {'federal': None, 'estadual': None, 'municipal': None}; fontes = {'federal': 'N/A', 'estadual': 'N/A', 'municipal': 'N/A'}
        opcoes = {f"[{i+1}] {item['title']}": item['link'] for i, item in enumerate(st.session_state.links_encontrados)}; urls_municipais = [opcoes[key] for key in st.session_state.urls_escolhidas_keys]
        textos_municipais = [texto for url in urls_municipais if (texto := processar_url(url))]
        if textos_municipais:
            dossie['municipal'] = "\n".join(textos_municipais); fontes['municipal'] = ", ".join(urls_municipais)
        if not dossie['municipal']:
            st.warning("Extração automática municipal falhou."); st.session_state.etapa = 'fallback_manual'; st.rerun()
        with st.spinner(f"Buscando a Constituição do Estado de {estado} e a Constituição Federal..."):
            url_ce = pesquisar_documento(servico_busca, st.session_state.search_id, f'constituição do estado de {estado}'); 
            if url_ce: dossie['estadual'] = processar_url(url_ce); fontes['estadual'] = url_ce
            url_cf = pesquisar_documento(servico_busca, st.session_state.search_id, 'Constituição Federal do Brasil 1988 planalto'); 
            if url_cf: dossie['federal'] = processar_url(url_cf); fontes['federal'] = url_cf
        
        st.session_state.fontes = fontes
        st.session_state.etapa = 'concluindo_analise' # Novo estado para chamar a função de análise
        st.session_state.dossie = dossie
        st.rerun()

if st.session_state.etapa == 'fallback_manual':
    with col2:
        st.subheader("3. Plano B: Extração Manual"); st.info("A extração automática falhou. Por favor, siga os passos:"); st.markdown("1. Abra o(s) link(s) desejado(s) em uma nova aba.\n2. Copie o texto da lei.\n3. Cole o texto na caixa abaixo.")
        texto_manual = st.text_area("Cole o conteúdo do(s) documento(s) municipais aqui:", height=300)
        if st.button("✅ Usar Texto Manual e Continuar Análise"):
            if texto_manual:
                st.session_state.dossie = {'municipal': texto_manual}; st.session_state.fontes = {'municipal': 'Texto colado manualmente'}
                st.session_state.etapa = 'analisando_leis'; st.rerun() # Volta para a etapa de análise para buscar estadual/federal

if st.session_state.etapa == 'concluindo_analise':
    with col2:
        st.subheader("Análise Jurídica Consolidada")
        modelo_ia = genai.GenerativeModel('gemini-2.5-pro')
        st.session_state.analise_final = analisar_em_etapas(modelo_ia, st.session_state.dossie, st.session_state.pergunta)
        st.session_state.etapa = 'exibir_resultado'
        st.rerun()

if st.session_state.etapa == 'exibir_resultado':
    with col2:
        st.subheader("Análise Jurídica Consolidada"); st.info("Dica: Clique na caixa abaixo, pressione Ctrl+A para selecionar tudo e Ctrl+C para copiar.")
        st.text_area("Resultado:", st.session_state.analise_final, height=400)
        with st.expander("Fontes Utilizadas na Análise"):
            st.write(f"**Federal:** {st.session_state.fontes.get('federal', 'N/A')}"); st.write(f"**Estadual:** {st.session_state.fontes.get('estadual', 'N/A')}"); st.write(f"**Municipal:** {st.session_state.fontes.get('municipal', 'N/A')}")
    with col1:
        if st.button("Nova Análise"):
            keys_to_keep = ['gemini_key', 'search_key', 'search_id']; 
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep: del st.session_state[key]
            st.rerun()
